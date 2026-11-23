"""Pure functional progression for the OAIS VirtualCounter.

No terminal, filesystem, or DEEP imports. A caller may register each newly
opened pole with DataManager via the optional ``on_open`` callback. The
existing linear Counter is NEVER mutated here.

Virtual logical address: [real, imaginary_layer_stack, function_ref, path_universe]
Counter's base-60 overflow universe is a separate field on VirtualCounter.
"""
from copy import deepcopy
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


def function_definition(name, params=None):
    """Build an explicit, versioned and validated registry specification."""
    if name not in FUNCTION_PARAMETERS:
        raise ValueError("Unknown function. Use 'navigator functions' to list options.")
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
    return {"name": name, "version": 1, "params": normalized}


def evaluate_offset(definition, step):
    """Evaluate a registered position function without evaluating arbitrary code."""
    if isinstance(step, bool) or not isinstance(step, int) or not 0 <= step <= MAX_STEP:
        raise ValueError(f"Imaginary depth must be an integer from 0 to {MAX_STEP}.")
    if not isinstance(definition, dict) or definition.get("version") != 1:
        raise ValueError("Unsupported function definition/version.")
    spec = function_definition(definition.get("name"), definition.get("params", {}))
    name, params = spec["name"], spec["params"]
    if name == "linear_offset":
        return params["slope"] * step
    if name == "cubic_offset":
        return params["scale"] * step ** 3
    if name == "constant_offset":
        return 0
    if name == "wave_offset":
        return params["amplitude"] * _WAVE[step % len(_WAVE)]
    raise AssertionError("Registry handling is incomplete")


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
                raise ValueError("Cannot turn before taking an outward step.")
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
                        or parent["leg"] != "toward"
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
