"""Interactive OAIS Navigator command, independent of the physical/host Counter.

No-argument ``navigator`` enters a subterminal. One-line commands remain valid:
``navigator open cubic`` or ``oais navigator function '2*k**2 + 1'``.
"""
import json
import shlex
from pathlib import Path

try:
    from .NavigatorEngine import (
        FUNCTION_PARAMETERS, expression_for_definition, function_definition,
    )
except ImportError:
    from NavigatorEngine import (
        FUNCTION_PARAMETERS, expression_for_definition, function_definition,
    )


FUNCTION_ALIASES = {
    "linear": ("linear_offset", {"slope": 1}),
    "backward": ("linear_offset", {"slope": -1}),
    "cubic": ("cubic_offset", {}),
    "constant": ("constant_offset", {}),
    "wave": ("wave_offset", {}),
}


class Navigator:
    """Command UI for the independent, nested mathematical navigator."""

    def __init__(self, terminal):
        self.terminal = terminal
        self.engine = terminal.navigator_engine
        self.manager = terminal.data_manager
        self.checkpoint_path = Path(self.manager.base_dir) / "navigator_checkpoint.json"

    @staticmethod
    def _parse_function(tokens):
        if not tokens:
            raise ValueError("Choose a preset or enter a function of k; e.g. 'cubic' or 'k**3'.")
        raw = tokens[0]
        preset = FUNCTION_ALIASES.get(raw.lower())
        if preset is None and raw in FUNCTION_PARAMETERS:
            preset = (raw, {})
        if preset is None:
            # Whitespace is legitimate within custom expressions. Legacy i input
            # is normalized by the expression validator to canonical k.
            return " ".join(tokens), {}
        name, defaults = preset
        params = dict(defaults)
        for token in tokens[1:]:
            key, sep, value = token.partition("=")
            if not sep or not key or not value:
                raise ValueError("Preset parameters use key=integer, e.g. cubic scale=2.")
            try:
                params[key.lower()] = int(value)
            except ValueError as exc:
                raise ValueError(f"Invalid integer parameter: {token}") from exc
        return name, params

    @staticmethod
    def _brief(snapshot):
        """Print portable function state, not runtime pi_ IDs/history hashes."""
        virtual = snapshot["virtual"]
        layers = snapshot["layers"]
        path = " > ".join(
            f"{expression_for_definition(layer['definition'])} "
            f"(k={layer['k']}, {'out' if layer['leg'] == 'away' else 'back'})"
            for layer in layers
        )
        return (f"Navigator [{'AUTO' if snapshot['auto_enabled'] else 'PAUSED'}]: "
                f"{virtual['coordinate']} (U={virtual['counter_universe']})\n"
                f"layers: {path or '(none — linear source)'}")

    @staticmethod
    def help_text():
        return ("Navigator: choose a function to project BASE ticks.\n"
                "  functions          List presets\n"
                "  function <f(k)>    Select a preset or custom expression\n"
                "  exit               Return to OAIS\n"
                "Examples: function cubic, function k**3\n"
                "Use BASE 'backwards' to reduce k and 'forwards' to increase k.")

    @staticmethod
    def presets_text():
        return (
            "PRESET FUNCTIONS — g(k)-g(0) (integer projection)\n"
            "  linear [slope=1]       k\n"
            "  backward               -k\n"
            "  cubic [scale=1]        k**3\n"
            "  constant               0 (k advances; real stays fixed)\n"
            "  wave [amplitude=1]     2-abs((k+2)%8-4)\n"
            "\nCUSTOM FUNCTIONS\n"
            "  function k**2\n"
            "  function 2*k**3 + 5\n"
            "  open (k+1)**2\n"
            "Safe integer operations: +, -, *, **, //, %, abs(), wave().\n"
            "No Python code, floats, imports, or other variable names."
        )

    def run(self, arguments="", *, input_func=input, print_func=print):
        """No arguments opens a nested command menu; args execute one action."""
        if arguments.strip():
            return self.process_command(arguments)
        print_func("\nNAVIGATOR — FUNCTION SELECTOR")
        print_func("Type 'functions', 'function k**3', or 'exit'.")
        while True:
            try:
                command = input_func("Navigator> ").strip()
            except (EOFError, KeyboardInterrupt):
                print_func("")
                break
            if not command:
                continue
            before_state = self.terminal.begin_nested_input(command)
            if command.lower() in ("exit", "back"):
                self.terminal.end_nested_input("navigator " + command, before_state)
                break
            success = True
            try:
                message = self.process_command(command)
            except (ValueError, TypeError, OSError) as exc:
                message = f"Navigator error: {exc}"
                success = False
            self.terminal.end_nested_input(
                "navigator " + command, before_state, success=success,
            )
            if message:
                print_func(message)
        return "Returning to OAIS terminal."

    def _open(self, name, params):
        # Validate *before* resetting the origin or modifying the stack.
        function_definition(name, params)
        if not self.engine.active:
            coordinate, universe = self.terminal.navigation_origin()
            self.engine.reset_to_linear(coordinate, universe)
        result = self.engine.push_function(name, params)
        self.terminal._explicit_hold = False
        return "Opened pole.\n" + self._brief(result)

    def process_command(self, arguments):
        try:
            tokens = shlex.split(arguments.strip())
        except ValueError as exc:
            raise ValueError("Unmatched quotes in Navigator command.") from exc
        action = tokens[0].lower() if tokens else "status"
        args = tokens[1:]
        if action in ("help", "?"):
            return self.help_text()
        if action in ("functions", "presets"):
            return self.presets_text()
        if action == "trace":
            if not args:
                return "Usage: trace <Sticky Note title or ID>"
            try:
                return self.terminal.replay_engine.trace(" ".join(args))
            except KeyError:
                return "Saved Sticky Note not found: " + " ".join(args)
        if action == "status":
            return self._brief(self.engine.snapshot())
        if action == "stack":
            return json.dumps(self.engine.compact_state(), indent=2)
        if action == "inspect":
            v = self.engine.virtual
            return json.dumps({"address": v.logical_address(),
                               "counter_universe": v.snapshot()["counter_universe"],
                               "direction": v.snapshot()["direction"]}, indent=2)
        if action in ("open", "set", "function", "custom"):
            name, params = self._parse_function(args)
            return self._open(name, params)
        if action == "child":
            name, params = self._parse_function(args)
            result = self.engine.push_function(name, params)
            self.terminal._explicit_hold = False
            return "Opened nested pole.\n" + self._brief(result)
        if action == "away":
            return self._brief(self.engine.away())
        if action == "turn":
            if args:
                name, params = self._parse_function(args)
                return self._brief(self.engine.turn(name, params))
            return self._brief(self.engine.turn())
        if action == "toward":
            return self._brief(self.engine.toward())
        if action == "pause":
            return self._brief(self.engine.pause())
        if action == "resume":
            result = self.engine.resume()
            self.terminal._explicit_hold = False
            return self._brief(result)
        if action == "sync":
            coordinate, universe = self.terminal.navigation_origin()
            self.engine.reset_to_linear(coordinate, universe)
            self.terminal._explicit_hold = False
            return "Navigator cleared and synchronized.\n" + self._brief(self.engine.snapshot())
        if action == "checkpoint":
            self.checkpoint()
            return f"Navigator checkpoint saved at {self.checkpoint_path}"
        if action == "restore":
            if self.terminal.sticky_note.active or self.terminal.sticky_note.get_path():
                raise ValueError("Save or clear the temporary Sticky Note before restoring.")
            return "Restored navigator checkpoint.\n" + self._brief(self.restore())
        if action in ("exit", "back"):
            return "Returning to OAIS terminal."
        return "Unknown Navigator command. Type 'help' for function selection."

    def checkpoint(self):
        """Save a self-contained terminal-local snapshot; no coordinate poles."""
        state = self.engine.snapshot()
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.manager._write_json(self.checkpoint_path, state, sort_coordinates=False)
        return state

    def restore(self):
        data = self.manager._load_json(self.checkpoint_path)
        if not isinstance(data, dict):
            raise ValueError("No readable navigator checkpoint.")
        frames = data.get("layers")
        if not isinstance(frames, list):
            raise ValueError("Invalid Navigator checkpoint layers.")
        if all(isinstance(frame, dict) and "definition" in frame for frame in frames):
            # v12 checkpoint carries each definition; no coordinate reads.
            return self.engine.restore(data)
        # Backward read support for existing pole-based navigator checkpoints.
        full = dict(data)
        full["layers"] = []
        for frame in frames:
            if not isinstance(frame, dict):
                raise ValueError("Invalid stored pole frame.")
            pole = self.manager.load_pole_function(
                frame["pole_real"], frame["id"],
                counter_universe=frame["pole_counter_universe"])
            full["layers"].append({**frame, "definition": pole["definition"]})
        if frames:
            root = self.manager.load_pole_function(
                frames[0]["pole_real"], frames[0]["id"],
                counter_universe=frames[0]["pole_counter_universe"])
            full["entry_seed"] = root.get("entry_seed")
        else:
            full["entry_seed"] = None
        return self.engine.restore(full)
