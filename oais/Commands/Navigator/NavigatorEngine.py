"""Pure functional progression for the OAIS VirtualCounter.

No terminal, filesystem, or DEEP imports. A caller may register each newly
opened pole with DataManager via the optional ``on_open`` callback. The
existing linear Counter is NEVER mutated here.

Virtual logical address: [real, imaginary_layer_stack, function_ref, path_universe]
Counter's base-60 overflow universe is a separate field on VirtualCounter.
"""
from copy import deepcopy
import ast
from array import array
from functools import lru_cache
import re
import hashlib
import json
from threading import RLock
import uuid

try:
    from ...utils.virtual_counter import (
        VirtualCounter, address_to_integer, integer_to_address,
        seed_path_universe, evolve_path_universe,
    )
except ImportError:
    from utils.virtual_counter import (
        VirtualCounter, address_to_integer, integer_to_address,
        seed_path_universe, evolve_path_universe,
    )


# Every function is a position OFFSET f(k), with f(0) = 0.
# Deliberately use integer arithmetic only; no floating-point drift.
MAX_STEP = 1_000_000
MAX_LAYERS = 32
PARAM_LIMIT = 1_000_000
FUNCTION_PARAMETERS = {
    "linear_offset": {"slope": 1},
    "cubic_offset": {"scale": 1},
    "constant_offset": {},
    # A deterministic, non-injective sine-like lookup, period eight.
    "wave_offset": {"amplitude": 1},
}
_WAVE = (0, 1, 2, 1, 0, -1, -2, -1)


# The source text of a traversal rule is portable; the evaluator below is not
# Python eval. All results are exact integers, with bounded complexity.
MAX_EXPRESSION_LENGTH = 128
MAX_EXPRESSION_NODES = 64
MAX_RESULT = 10**30


# The legacy Narrative Navigator recurrence, using OAIS little-endian digits.
_NARRATIVE_SPACE = 60**6
_NARRATIVE_MASK = 2**32 - 1
_NARRATIVE_A = 0x9E3779B9
_NARRATIVE_LOCK = RLock()


def narrative_expression(key, pole=None):
    """Stable legacy-style start and portable function, seeded by a string."""
    if not isinstance(key, str) or not key:
        raise ValueError("Narrative key must be a nonempty string.")
    def digest(text):
        return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big")
    if pole is None:
        pole = digest("v1|" + key) % _NARRATIVE_SPACE
    if type(pole) is not int or not 0 <= pole < _NARRATIVE_SPACE:
        raise ValueError("Narrative pole outside base-60 space.")
    coordinate, _ = integer_to_address(pole)
    imag = digest(coordinate + "|" + key) & _NARRATIVE_MASK
    x = digest(f"{pole}|{key}") % _NARRATIVE_SPACE
    return coordinate, f"narrative_v1({pole},{imag},{x},k)"


def _narrative_constant(real):
    total = 0
    for weight in (13, 17, 19, 23, 29, 31):
        real, digit = divmod(real, 60)
        total += digit * weight
    return total & _NARRATIVE_MASK


@lru_cache(maxsize=4)
def _narrative_states(pole, imag, x):
    # Packed arrays keep even long paths bounded; cache is transient only.
    return array("Q", [pole]), array("I", [imag])


def _narrative_offset(pole, imag, x, k):
    if not (0 <= pole < _NARRATIVE_SPACE and 0 <= imag <= _NARRATIVE_MASK
            and 0 <= x < _NARRATIVE_SPACE and 0 <= k <= MAX_STEP):
        raise ValueError("Narrative parameter outside supported range.")
    with _NARRATIVE_LOCK:
        real, imaginary = _narrative_states(pole, imag, x)
        while len(real) <= k:
            previous, old_i = real[-1], imaginary[-1]
            current = (previous**2 - old_i**2 + x) % _NARRATIVE_SPACE
            new_i = ((_narrative_constant(previous) ^ _narrative_constant(current) ^ old_i)
                     * _NARRATIVE_A + 1) & _NARRATIVE_MASK
            real.append(current)
            imaginary.append(new_i)
        return real[k] - pole


def _parse_expression(expression):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError("Function expression must be 1–128 characters.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid mathematical function expression.") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_EXPRESSION_NODES:
        raise ValueError("Function expression is too complex.")
    for node in nodes:
        if isinstance(node, (ast.Expression, ast.Load, ast.BinOp, ast.UnaryOp,
                             ast.Constant, ast.Name, ast.Call, ast.Add, ast.Sub,
                             ast.Mult, ast.Pow, ast.Mod, ast.FloorDiv, ast.UAdd,
                             ast.USub)):
            continue
        raise ValueError("Unsupported mathematical function syntax.")
    return tree


def _bounded_integer(value):
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > MAX_RESULT:
        raise ValueError("Function output exceeds supported integer range.")
    return value


def _raw_expression(expression, k):
    tree = _parse_expression(expression)
    def run(node):
        if isinstance(node, ast.Expression):
            return run(node.body)
        if isinstance(node, ast.Constant):
            if type(node.value) is not int or abs(node.value) > PARAM_LIMIT:
                raise ValueError("Only bounded integer constants are allowed.")
            return node.value
        if isinstance(node, ast.Name):
            if node.id == "k":
                return k
            raise ValueError("Only progression variable 'k' is allowed.")
        if isinstance(node, ast.UnaryOp):
            v = run(node.operand)
            return _bounded_integer(-v if isinstance(node.op, ast.USub) else v)
        if isinstance(node, ast.BinOp):
            a, b = run(node.left), run(node.right)
            if isinstance(node.op, ast.Add):
                v = a + b
            elif isinstance(node.op, ast.Sub):
                v = a - b
            elif isinstance(node.op, ast.Mult):
                v = a * b
            elif isinstance(node.op, ast.Pow):
                if not 0 <= b <= 10:
                    raise ValueError("Integer powers must be between 0 and 10.")
                # Bound before exponentiation to avoid huge intermediate integers.
                if abs(a) > 1 and b > 0 and abs(a).bit_length() * b > 112:
                    raise ValueError("Function power exceeds supported range.")
                v = a ** b
            elif isinstance(node.op, ast.FloorDiv):
                if b == 0:
                    raise ValueError("Function division by zero.")
                v = a // b
            elif isinstance(node.op, ast.Mod):
                if b == 0:
                    raise ValueError("Function modulo by zero.")
                v = a % b
            else:
                raise ValueError("Unsupported operator.")
            return _bounded_integer(v)
        if isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Name) and node.func.id == "narrative_v1"
                    and len(node.args) == 4 and not node.keywords):
                # Restrict the recurrence to literal seeds and k, not nested calls.
                seeds = node.args[:3]
                if (not all(isinstance(arg, ast.Constant) and type(arg.value) is int for arg in seeds)
                        or not isinstance(node.args[3], ast.Name) or node.args[3].id != "k"):
                    raise ValueError("Use narrative_v1(pole,imaginary,X,k) with literal integer seeds.")
                return _narrative_offset(*(arg.value for arg in seeds), k)
            if not isinstance(node.func, ast.Name) or len(node.args) != 1 or node.keywords:
                raise ValueError("Only whitelisted functions are permitted.")
            value = run(node.args[0])
            if node.func.id == "abs":
                return _bounded_integer(abs(value))
            if node.func.id == "wave":
                return _WAVE[value % len(_WAVE)]
            raise ValueError("Unknown mathematical function.")
        raise ValueError("Unsupported expression node.")
    return run(tree)


def validate_expression(expression):
    """Validate syntax and semantics; translate legacy i to canonical k."""
    expression = expression.strip() if isinstance(expression, str) else expression
    if isinstance(expression, str):
        expression = re.sub(r"\bi\b", "k", expression)
    _raw_expression(expression, 0)
    _raw_expression(expression, 1)
    return expression


def function_definition(name, params=None):
    """Create a versioned expression rule, preserving legacy registry aliases."""
    if not isinstance(name, str):
        raise ValueError("Function name/expression must be text.")
    if name == "expression":
        if not isinstance(params, dict) or set(params) != {"f"}:
            raise ValueError("Expression definitions require exactly an f parameter.")
        expression = validate_expression(params["f"])
        return {"name": "expression", "version": 1,
                "params": {"f": expression}, "f": expression}
    if name not in FUNCTION_PARAMETERS:
        if params:
            raise ValueError("Custom expressions do not take registry parameters.")
        return function_definition("expression", {"f": name})
    defaults = FUNCTION_PARAMETERS[name]
    params = {} if params is None else params
    if not isinstance(params, dict):
        raise ValueError("Function parameters must be a mapping.")
    if set(params) - set(defaults):
        raise ValueError(f"Unknown parameters for {name}: {sorted(set(params)-set(defaults))}")
    normalized = dict(defaults)
    normalized.update(params)
    for key, value in normalized.items():
        if isinstance(value, bool) or not isinstance(value, int) or abs(value) > PARAM_LIMIT:
            raise ValueError(f"{key} must be an integer with magnitude at most {PARAM_LIMIT}.")
    if name == "linear_offset":
        expression = f"{normalized['slope']}*k" if normalized['slope'] != 1 else "k"
    elif name == "cubic_offset":
        expression = f"{normalized['scale']}*k**3" if normalized['scale'] != 1 else "k**3"
    elif name == "constant_offset":
        expression = "0"
    else:
        # Triangle-wave lookup expanded into a *portable math expression*;
        # a Sticky Note never needs to know the old named wave registry.
        wave = "(2-abs((k+2)%8-4))"
        expression = f"{normalized['amplitude']}*{wave}" if normalized['amplitude'] != 1 else wave
    expression = validate_expression(expression)
    return {"name": name, "version": 1, "params": normalized, "f": expression}


def expression_for_definition(definition):
    """Return the exact text needed by a portable Sticky Note function slot."""
    if not isinstance(definition, dict) or definition.get("version", 1) != 1:
        raise ValueError("Unsupported function definition.")
    spec = function_definition(definition["name"], definition.get("params", {}))
    if "f" in definition and validate_expression(definition["f"]) != spec["f"]:
        raise ValueError("Stored mathematical rule conflicts with its definition.")
    return spec["f"]


def evaluate_offset(definition, step):
    """Return g(k)-g(0): every expression begins at its own pole."""
    if isinstance(step, bool) or not isinstance(step, int) or not 0 <= step <= MAX_STEP:
        raise ValueError(f"Imaginary depth must be an integer from 0 to {MAX_STEP}.")
    expression = expression_for_definition(definition)
    return _bounded_integer(_raw_expression(expression, step) - _raw_expression(expression, 0))


class NavigatorEngine:
    """Stack-based functional navigator that drives an OAIS VirtualCounter.

    Opening a root pole creates an outward frame at k=0 (no movement).
    Each away/toward/turn/child movement consumes exactly ONE imaginary step.
    On return to k=0, that layer closes immediately; any parent resumes at
    its frozen state. A root closing leaves the virtual counter FREE at pole.

    If auto_enabled, an eligible ordinary command advances once in the active
    leg. Selecting the leg, choosing which events are eligible, and persisting
    the pole itself are handled by an external terminal adapter.
    """

    def __init__(self, virtual_counter=None, *, on_open=None, history_secret=None):
        self.virtual = virtual_counter if virtual_counter is not None else VirtualCounter()
        self.on_open = on_open  # callable(frame, entry_seed=None) at the pole
        self.history_secret = history_secret
        self.layers = []
        self.auto_enabled = False
        self.entry_seed = None
        self._lock = RLock()

    @property
    def active(self):
        return bool(self.layers)

    @staticmethod
    def _imaginary(layers):
        return [{"activation": frame["id"], "step": frame["k"],
                 "leg": frame["leg"]} for frame in layers]

    @staticmethod
    def _ref(layers):
        return layers[-1]["id"] if layers else "linear_offset"

    @staticmethod
    def _leg(layers):
        return layers[-1]["leg"] if layers else "linear"

    @staticmethod
    def _project(layers, fallback):
        if not layers:
            return fallback
        top = layers[-1]
        return top["pole_index"] + evaluate_offset(top["definition"], top["k"])

    def _signature(self):
        return self.virtual.logical_address()[:3]

    def _apply(self, proposed, operation, *, fallback):
        """One atomic conceptual movement + one path-universe evolution."""
        before = self.virtual.snapshot()
        before_signature = self._signature()
        absolute = self._project(proposed, fallback)
        real, counter_universe = integer_to_address(absolute)
        imaginary = self._imaginary(proposed)
        ref, leg = self._ref(proposed), self._leg(proposed)
        after_signature = [real, imaginary, ref]
        next_u = evolve_path_universe(
            before["path_universe"], before_signature, after_signature, operation,
            counter_universe_before=before["counter_universe"],
            counter_universe_after=counter_universe, secret=self.history_secret,
        )
        self.virtual.set_projection(real, counter_universe, imaginary=imaginary,
                                    function=ref, direction=leg, path_universe=next_u)
        self.layers = proposed
        if not proposed:
            self.auto_enabled = False
        return self.snapshot()

    def open_pole(self, name="linear_offset", params=None, *, seed=None,
                  activation_id=None):
        """Define a root function *at this pole only*. Opening does not tick."""
        with self._lock:
            if self.layers:
                raise ValueError("Already in an excursion; use 'child' during return.")
            spec = function_definition(name, params)
            state = self.virtual.snapshot()
            absolute = address_to_integer(state["coordinate"], state["counter_universe"])
            seed = uuid.uuid4().hex if seed is None else seed
            if not isinstance(seed, str) or not seed:
                raise ValueError("Root traversal seed must be a nonempty string.")
            ref = self._validate_ref(activation_id or "pi_" + uuid.uuid4().hex[:16])
            frame = {"id": ref, "definition": spec, "pole_index": absolute,
                     "pole_real": state["coordinate"],
                     "pole_counter_universe": state["counter_universe"],
                     "parent": None, "opened_at": None,
                     "k": 0, "leg": "away"}
            start_u = seed_path_universe(state["coordinate"], seed,
                                         counter_universe=state["counter_universe"],
                                         secret=self.history_secret)
            # Register before changing the navigator, to avoid live state
            # pretending a pole exists after a failed storage operation.
            if self.on_open:
                self.on_open(deepcopy(frame), entry_seed=seed)
            self.virtual.set_projection(state["coordinate"], state["counter_universe"],
                                        imaginary=self._imaginary([frame]), function=ref,
                                        direction="away", path_universe=start_u)
            self.layers = [frame]
            self.entry_seed = seed
            self.auto_enabled = True
            return self.snapshot()

    def push_function(self, name="linear_offset", params=None, *, activation_id=None):
        """Open a *new independent imaginary layer* at the current real pole.

        Unlike the historical open_child() API, the new layer starts at k=0
        and may be pushed while the parent is moving in either direction.
        Activating a function does not consume a tick.
        """
        with self._lock:
            if not self.layers:
                return self.open_pole(name, params, activation_id=activation_id)
            if len(self.layers) >= MAX_LAYERS:
                raise ValueError("Maximum nested layer depth reached.")
            spec = function_definition(name, params)
            parent = self.layers[-1]
            state = self.virtual.snapshot()
            absolute = address_to_integer(state["coordinate"], state["counter_universe"])
            ref = self._validate_ref(activation_id or "pi_" + uuid.uuid4().hex[:16])
            if any(frame["id"] == ref for frame in self.layers):
                raise ValueError("Activation ID already exists in this stack.")
            frame = {"id": ref, "definition": spec, "pole_index": absolute,
                     "pole_real": state["coordinate"],
                     "pole_counter_universe": state["counter_universe"],
                     "parent": parent["id"],
                     "opened_at": {"parent_step": parent["k"],
                                   "parent_leg": parent["leg"]},
                     "k": 0, "leg": "away"}
            proposed = deepcopy(self.layers) + [frame]
            if self.on_open:
                self.on_open(deepcopy(frame), entry_seed=None)
            result = self._apply(proposed, "push:" + ref, fallback=absolute)
            self.auto_enabled = True
            return self.snapshot()

    def compact_state(self):
        """Minimal evolving OAIS coordinate: real projection and k-layer stack."""
        with self._lock:
            v = self.virtual.snapshot()
            return {"real": v["coordinate"],
                    "counter_universe": v["counter_universe"],
                    "direction": (-1 if self.layers and self.layers[-1]["leg"] == "toward" else 1),
                    "functions": [{"f": expression_for_definition(layer["definition"]),
                                   "k": layer["k"],
                                   "direction": (-1 if layer["leg"] == "toward" else 1)}
                                  for layer in self.layers]}

    @staticmethod
    def portable_state(snapshot, *, source=None, source_coordinate=None,
                       source_universes=None):
        """The smallest *mathematically sufficient* resumable navigation state.

        There is one root pole, plus an ordered list of independent functions.
        The path-universe, activation IDs and transient Navigator snapshot are
        deliberately not persisted here: they describe runtime history, not
        how to calculate the next real position. Sticky Notes have their own
        note-seeded deterministic history.
        """
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("virtual"), dict):
            raise ValueError("A Navigator snapshot is required.")
        virtual = snapshot["virtual"]
        coordinate = virtual["coordinate"]
        layers = snapshot["layers"]
        result = {
            "coordinate": coordinate,
            "coordinate_list": [int(part) for part in coordinate.split()],
            "universes": virtual["counter_universe"],
            "source": source if source is not None else "oais",
            "functions": [
                {"f": expression_for_definition(frame["definition"]),
                 "k": frame["k"],
                 "direction": -1 if frame["leg"] == "toward" else 1}
                for frame in layers
            ],
        }
        if (not isinstance(result["source"], str) or
                not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", result["source"])):
            raise ValueError("Navigation source must be a terminal identifier.")
        if layers:
            root = layers[0]
            result["pole"] = root["pole_real"]
            if root["pole_counter_universe"]:
                result["pole_universes"] = root["pole_counter_universe"]
            if not snapshot.get("auto_enabled", True):
                result["paused"] = True
        else:
            # The final pole after unwinding stays FREE until the next source
            # command. FOLLOW and FREE must remain distinguishable on restart.
            if virtual.get("mode") == "free":
                result["free"] = True
        if source_coordinate is not None:
            if source_universes is None:
                raise ValueError("Source universe must accompany source coordinate.")
            source_coordinate, source_universes = integer_to_address(
                address_to_integer(source_coordinate, source_universes))
            result["source_coordinate"] = source_coordinate
            result["source_universes"] = source_universes
        return result

    @staticmethod
    def snapshot_from_portable(data):
        """Validate compact storage and reconstruct a Navigator runtime snapshot.

        The mathematical stack is preserved exactly. Runtime pole identifiers
        and path history are freshly *deterministically* derived from the
        checkpoint, rather than falsely claiming to preserve its old history.
        """
        if not isinstance(data, dict):
            raise ValueError("Invalid portable Navigator checkpoint.")
        coordinate = data.get("coordinate")
        u = data.get("universes", 0)
        target = address_to_integer(coordinate, u)
        if data.get("coordinate_list") is not None and data["coordinate_list"] != [
                int(v) for v in coordinate.split()]:
            raise ValueError("Checkpoint coordinate_list does not match coordinate.")
        layers_data = data.get("functions", [])
        if not isinstance(layers_data, list) or len(layers_data) > MAX_LAYERS:
            raise ValueError("Invalid function stack in checkpoint.")
        if not layers_data and ("pole" in data or "paused" in data):
            raise ValueError("Linear checkpoint cannot contain a pole or paused functions.")
        frames = []
        root = None
        absolute = target
        if layers_data:
            if "pole" not in data:
                raise ValueError("Active functions require a root pole.")
            root = address_to_integer(data["pole"], data.get("pole_universes", 0))
            absolute = root
        canonical = []
        for index, item in enumerate(layers_data):
            if not isinstance(item, dict) or set(item) != {"f", "k", "direction"}:
                raise ValueError("Each function must specify f, k, and direction.")
            depth = item["k"]
            direction = item["direction"]
            if (isinstance(depth, bool) or not isinstance(depth, int) or
                    not 0 <= depth <= MAX_STEP or direction not in (1, -1) or
                    isinstance(direction, bool)):
                raise ValueError("Invalid function tick or direction.")
            spec = function_definition(item["f"])
            expression = expression_for_definition(spec)
            canonical.append({"f": expression, "k": depth, "direction": direction})
            # Stable internal IDs are *not* required for portable navigation;
            # they only make the restored in-memory frames well formed.
            identity = json.dumps([data.get("pole"), canonical, index],
                                  sort_keys=True, separators=(",", ":"))
            ref = "pi_" + hashlib.blake2b(identity.encode(), digest_size=8,
                       person=b"OAISNav-v11").hexdigest()
            pole_real, pole_u = integer_to_address(absolute)
            parent = frames[-1] if frames else None
            frame = {"id": ref, "definition": spec, "pole_index": absolute,
                     "pole_real": pole_real, "pole_counter_universe": pole_u,
                     "parent": parent["id"] if parent else None,
                     "opened_at": ({"parent_step": parent["k"],
                                    "parent_leg": parent["leg"]} if parent else None),
                     "k": depth, "leg": "away" if direction == 1 else "toward"}
            frames.append(frame)
            absolute += evaluate_offset(spec, depth)
        if absolute != target:
            raise ValueError("Virtual coordinate does not match the pole and function ticks.")
        # No runtime-specific history is copied from the old file; this seed is
        # a deterministic resume checkpoint, not the original path universe.
        seed_text = json.dumps([coordinate, u, data.get("pole"), canonical],
                               sort_keys=True, separators=(",", ":"))
        path_u = seed_path_universe(coordinate, "checkpoint-v11:" + seed_text,
                                    counter_universe=u)
        mode = "free" if frames or data.get("free", False) else "follow"
        stack = [{"activation": f["id"], "step": f["k"], "leg": f["leg"]}
                 for f in frames]
        source_coordinate = data.get("source_coordinate")
        source_universe = data.get("source_universes", 0)
        host = None
        if source_coordinate is not None:
            addr, su = integer_to_address(address_to_integer(source_coordinate, source_universe))
            host = {"coordinate": addr, "counter_universe": su}
            if mode == "follow" and (addr, su) != (coordinate, u):
                raise ValueError("FOLLOW checkpoint must match its source coordinate.")
        v = {"coordinate": coordinate, "universe": u, "counter_universe": u,
             "path_universe": path_u,
             "imaginary": stack if frames else ([] if mode == "free" else 0),
             "function": frames[-1]["id"] if frames else "linear_offset",
             "direction": frames[-1]["leg"] if frames else "linear",
             "mode": mode, "host": host}
        return {"version": 1, "virtual": v, "layers": frames,
                "entry_seed": None,
                "auto_enabled": bool(frames) and not data.get("paused", False)}

    def restore_portable(self, data):
        """Resume the *mathematics* of a stored path without filesystem lookups."""
        return self.restore(self.snapshot_from_portable(data))

    def advance_linear(self, delta, *, operation="linear"):
        """Continue linearly from the last virtual pole after all layers unwind."""
        with self._lock:
            if self.layers or self.virtual.mode != "free":
                return None
            if isinstance(delta, bool) or not isinstance(delta, int):
                raise ValueError("Linear step must be an integer.")
            if not delta:
                return self.snapshot()
            old = self.virtual.snapshot()
            absolute = address_to_integer(old["coordinate"], old["counter_universe"])
            real, u = integer_to_address(absolute + delta)
            key = evolve_path_universe(old["path_universe"],
                [old["coordinate"], [], "linear_offset"],
                [real, [], "linear_offset"], operation,
                counter_universe_before=old["counter_universe"],
                counter_universe_after=u, secret=self.history_secret)
            self.virtual.set_projection(real, u, imaginary=[], function="linear_offset",
                                        direction="linear", path_universe=key)
            return self.snapshot()

    def open_child(self, name=None, params=None, *, activation_id=None):
        """A reversal while returning: new child pole, first step consumed."""
        with self._lock:
            if not self.layers:
                raise ValueError("Cannot open a child without an active parent.")
            if len(self.layers) >= MAX_LAYERS:
                raise ValueError("Maximum nested layer depth reached.")
            parent = self.layers[-1]
            if parent["leg"] != "toward" or parent["k"] == 0:
                raise ValueError("A child pole can open only during an unfinished return.")
            if name is None:
                spec = deepcopy(parent["definition"]) if params is None else function_definition(
                    parent["definition"]["name"], params)
            else:
                spec = function_definition(name, params)
            state = self.virtual.snapshot()
            absolute = address_to_integer(state["coordinate"], state["counter_universe"])
            ref = self._validate_ref(activation_id or "pi_" + uuid.uuid4().hex[:16])
            if any(l["id"] == ref for l in self.layers):
                raise ValueError("Activation ID already exists in this stack.")
            frame = {"id": ref, "definition": spec, "pole_index": absolute,
                     "pole_real": state["coordinate"],
                     "pole_counter_universe": state["counter_universe"],
                     "parent": parent["id"],
                     "opened_at": {"parent_step": parent["k"], "parent_leg": parent["leg"]},
                     "k": 1, "leg": "away"}
            evaluate_offset(spec, 1)  # ensure function can be evaluated before store
            proposed = deepcopy(self.layers) + [frame]
            if self.on_open:
                self.on_open(deepcopy(frame), entry_seed=None)
            return self._apply(proposed, "child:" + ref, fallback=absolute)

    def away(self):
        with self._lock:
            if not self.layers:
                raise ValueError("No active pole. Open a function first.")
            if self.layers[-1]["leg"] != "away":
                raise ValueError("Already returning. Use 'child' or 'turn' to reverse again.")
            proposed = deepcopy(self.layers)
            if proposed[-1]["k"] >= MAX_STEP:
                raise ValueError("Maximum imaginary depth reached.")
            proposed[-1]["k"] += 1
            return self._apply(proposed, "away", fallback=self._absolute())

    def turn(self, name=None, params=None):
        """At apex: first return step. During return: child with first step."""
        with self._lock:
            if not self.layers:
                raise ValueError("No active pole to turn from.")
            if self.layers[-1]["leg"] == "toward":
                return self.open_child(name, params)
            if name is not None or params is not None:
                raise ValueError("Function argument is only valid when turning mid-return.")
            proposed = deepcopy(self.layers)
            if proposed[-1]["k"] == 0:
                if len(proposed) == 1:
                    raise ValueError("Cannot turn before taking an outward step.")
                # No tick may disappear at an empty child. Unwind it and
                # apply this same reverse tick to the nearest nonempty parent.
                proposed.pop()
                while proposed and proposed[-1]["k"] == 0:
                    proposed.pop()
                if proposed:
                    proposed[-1]["leg"] = "toward"
                    proposed[-1]["k"] -= 1
                    if proposed[-1]["k"] == 0:
                        proposed.pop()
                return self._apply(proposed, "turn:empty-child",
                                   fallback=self.layers[0]["pole_index"])
            proposed[-1]["leg"] = "toward"
            proposed[-1]["k"] -= 1
            if proposed[-1]["k"] == 0:
                proposed.pop()
            return self._apply(proposed, "turn", fallback=self.layers[-1]["pole_index"])

    def toward(self):
        with self._lock:
            if not self.layers:
                raise ValueError("No active pole.")
            if self.layers[-1]["leg"] != "toward":
                raise ValueError("Use 'turn' to begin returning from an outward leg.")
            proposed = deepcopy(self.layers)
            proposed[-1]["k"] -= 1
            if proposed[-1]["k"] == 0:
                finished = proposed.pop()
                fallback = finished["pole_index"]
            else:
                fallback = self._absolute()
            return self._apply(proposed, "toward", fallback=fallback)

    def advance_host_direction(self, delta):
        """Apply one signed source command to the active function tick.

        A BASE `backwards` contributes -1. Every other BASE input,
        including an unknown command, contributes +1. The previous leg
        merely describes the LAST step; it never chooses the next step.

        Reaching k=0 preserves the layer so a subsequent forward command
        returns along the same function. A further reverse step from an
        empty nested layer exits it and continues through its parent. At
        the root pole, reverse movement is bounded at k=0.
        """
        if isinstance(delta, bool) or delta not in (-1, 1):
            raise ValueError("Host direction must be +1 or -1.")
        with self._lock:
            if not self.layers or not self.auto_enabled:
                return None
            proposed = deepcopy(self.layers)
            if delta > 0:
                if proposed[-1]["k"] >= MAX_STEP:
                    raise ValueError("Maximum imaginary depth reached.")
                proposed[-1]["k"] += 1
                proposed[-1]["leg"] = "away"
                return self._apply(proposed, "host:forward", fallback=self._absolute())

            # An already empty child is exited by the NEXT backward tick.
            # Hitting zero from k=1 does not delete the function or its pole.
            while len(proposed) > 1 and proposed[-1]["k"] == 0:
                proposed.pop()
            if proposed[-1]["k"] > 0:
                proposed[-1]["k"] -= 1
            proposed[-1]["leg"] = "toward"
            return self._apply(proposed, "host:backward", fallback=self._absolute())

    def advance_automatic(self):
        """Advance once for an eligible host command; never for menu controls."""
        with self._lock:
            if not self.layers or not self.auto_enabled:
                return None
            if self.layers[-1]["leg"] == "away":
                return self.away()
            return self.toward()

    def pause(self):
        with self._lock:
            self.auto_enabled = False
            return self.snapshot()

    def resume(self):
        with self._lock:
            if not self.layers:
                raise ValueError("No active excursion to resume.")
            self.auto_enabled = True
            return self.snapshot()

    def reset_to_linear(self, coordinate=None, counter_universe=0):
        """Clear all imaginary layers; host/standalone coordinate is authoritative."""
        with self._lock:
            self.layers = []
            self.auto_enabled = False
            self.entry_seed = None
            if coordinate is None:
                return self.virtual.sync_to_host()
            return self.virtual.sync_to_host(coordinate, counter_universe)

    def _absolute(self):
        s = self.virtual.snapshot()
        return address_to_integer(s["coordinate"], s["counter_universe"])

    @staticmethod
    def _validate_ref(ref):
        if (not isinstance(ref, str) or len(ref) != 19 or not ref.startswith("pi_")
                or any(c not in "0123456789abcdef" for c in ref[3:])):
            raise ValueError("Activation must be pi_ followed by 16 lowercase hex digits.")
        return ref

    def snapshot(self):
        """JSON-safe exact snapshot. A full snapshot contains pole definitions;
        do not store it as an ordinary command event. Future Sticky Notes can
        persist a compact plan and resolve functions at their opening poles.
        """
        with self._lock:
            return {"version": 1, "virtual": self.virtual.snapshot(),
                    "layers": deepcopy(self.layers),
                    "entry_seed": self.entry_seed,
                    "auto_enabled": self.auto_enabled}

    def restore(self, snapshot):
        """Restore a validated in-memory snapshot to a fresh engine (no disk IO)."""
        if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
            raise ValueError("Unsupported Navigator snapshot version.")
        with self._lock:
            layers = deepcopy(snapshot.get("layers"))
            state = snapshot.get("virtual")
            if not isinstance(layers, list) or not isinstance(state, dict):
                raise ValueError("Invalid Navigator snapshot contents.")
            for i, f in enumerate(layers):
                if not isinstance(f, dict):
                    raise ValueError("Invalid layer frame.")
                self._validate_ref(f.get("id"))
                if (isinstance(f.get("pole_index"), bool) or
                        not isinstance(f.get("pole_index"), int)):
                    raise ValueError("Invalid pole absolute coordinate.")
                if f.get("leg") not in ("away", "toward"):
                    raise ValueError("Invalid excursion leg.")
                k = f.get("k")
                if isinstance(k, bool) or not isinstance(k, int) or k < 0 or k > MAX_STEP:
                    raise ValueError("Invalid depth.")
                if i == 0:
                    if f.get("parent") is not None or f.get("opened_at") is not None:
                        raise ValueError("Invalid root parent linkage.")
                elif f.get("parent") != layers[i-1]["id"] or not isinstance(f.get("opened_at"), dict):
                    raise ValueError("Broken nested parent linkage.")
                f["definition"] = function_definition(
                    f["definition"]["name"], f["definition"].get("params", {}))
                if f.get("pole_real") != integer_to_address(f["pole_index"])[0] or (
                    f.get("pole_counter_universe") != integer_to_address(f["pole_index"])[1]
                ):
                    raise ValueError("Pole coordinate and absolute index disagree.")
            if len(layers) > MAX_LAYERS:
                raise ValueError("Too many active layers.")
            if len({f["id"] for f in layers}) != len(layers):
                raise ValueError("Duplicated active layer ID.")
            for parent, child in zip(layers, layers[1:]):
                anchor = child["opened_at"]
                if (anchor.get("parent_step") != parent["k"]
                        or anchor.get("parent_leg") != parent["leg"]
                        or child["pole_index"] != self._project([parent], 0)):
                    raise ValueError("Nested child does not match its parent opening anchor.")
            # The full address must match the mathematical projection, not
            # merely be copied from an unvalidated snapshot.
            expected = self._project(layers, address_to_integer(
                state["coordinate"], state["counter_universe"]))
            expected_real, expected_u = integer_to_address(expected)
            if (expected_real != state["coordinate"] or expected_u != state["counter_universe"]
                    or (state["imaginary"] != self._imaginary(layers)
                        and not (not layers and state.get("mode") == "follow"
                                 and state["imaginary"] == 0))
                    or state["function"] != self._ref(layers)
                    or state["direction"] != self._leg(layers)):
                raise ValueError("Snapshot does not match functional projection/state.")
            if snapshot.get("auto_enabled") and not layers:
                raise ValueError("Cannot auto-advance with an empty layer stack.")
            if layers and state.get("mode") != "free":
                raise ValueError("Active navigation must have a FREE virtual counter.")
            if layers or state.get("mode") == "free":
                self.virtual.set_projection(
                    state["coordinate"], state["counter_universe"],
                    imaginary=state["imaginary"], function=state["function"],
                    direction=state["direction"], path_universe=state["path_universe"])
            else:
                self.virtual.sync_to_host(state["coordinate"], state["counter_universe"],
                                          path_universe=state["path_universe"])
            self.layers = layers
            self.auto_enabled = bool(snapshot.get("auto_enabled"))
            self.entry_seed = snapshot.get("entry_seed")
            return self.snapshot()
