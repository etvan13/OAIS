"""OAIS Navigator command, separate from its pure mathematical engine.

The adapter alone knows DataManager and the terminal. The function definition
exists only at its activation pole. Commands elsewhere are not written here;
that remains the upcoming Sticky Note integration.
"""
import json
import os
from pathlib import Path

try:
    from .NavigatorEngine import FUNCTION_PARAMETERS
except ImportError:
    from NavigatorEngine import FUNCTION_PARAMETERS


FUNCTION_ALIASES = {
    "linear": ("linear_offset", {"slope": 1}),
    "backward": ("linear_offset", {"slope": -1}),
    "cubic": ("cubic_offset", {}),
    "constant": ("constant_offset", {}),
    "wave": ("wave_offset", {}),
}


class Navigator:
    """Small one-command-at-a-time UI. Never advances the DEEP Counter."""

    def __init__(self, terminal):
        self.terminal = terminal
        self.engine = terminal.navigator_engine
        self.manager = terminal.data_manager
        self.checkpoint_path = Path(self.manager.base_dir) / "navigator_checkpoint.json"

    @staticmethod
    def _parse_function(tokens):
        if not tokens:
            raise ValueError("Specify a function (linear, backward, cubic, constant, wave).")
        raw = tokens[0].lower()
        name, defaults = FUNCTION_ALIASES.get(raw, (raw, {}))
        params = dict(defaults)
        for token in tokens[1:]:
            key, sep, value = token.partition("=")
            if not sep or not key or not value:
                raise ValueError("Parameters use key=integer (example: scale=2).")
            try:
                params[key.lower()] = int(value)
            except ValueError as exc:
                raise ValueError(f"Invalid integer parameter: {token}") from exc
        return name, params

    @staticmethod
    def _brief(s):
        v = s["virtual"]
        layers = s["layers"]
        path = " > ".join(f"{f['id']} (k={f['k']}, {f['leg']})" for f in layers)
        return (f"Navigator [{'AUTO' if s['auto_enabled'] else 'PAUSED'}]: "
                f"{v['coordinate']} (counter_universe {v['counter_universe']}, "
                f"path_universe {v['path_universe']})\n"
                f"function={v['function']}, imaginary={v['imaginary']}, "
                f"direction={v['direction']}\n"
                f"layers: {path or '(none)'}")

    def run(self, arguments=""):
        tokens = arguments.strip().split()
        action = tokens[0].lower() if tokens else "status"
        args = tokens[1:]
        if action in ("help", "?"):
            return (
                "Navigator commands:\n"
                "  functions                    List built-in functions\n"
                "  open <function> [key=value]  Open pole at virtual coordinate (k=0)\n"
                "  away                         One outward step\n"
                "  turn [function]              First return step, or child on a return\n"
                "  toward                       Continue returning one step\n"
                "  child <function> [key=value] Open nested pole on a return; step once\n"
                "  pause / resume               Disable/enable automatic host-command stepping\n"
                "  status                       Display virtual position and layers\n"
                "  inspect                      Full four-part address (JSON)\n"
                "  checkpoint / restore         Save/reload unfinished active state\n"
                "  trace <note>                 Read full path from coordinate storage\n"
                "  sync                         Abandon layers and follow host/standalone counter\n"
                "Functions: linear, backward, cubic, constant, wave.\n"
                "When active, ordinary BASE commands each consume ONE functional step.\n"
                "Navigator controls, virtual controls, and META switches do not."
            )
        if action == "trace":
            if not args:
                return "Usage: navigator trace <Sticky Note title or ID>"
            try:
                return self.terminal.replay_engine.trace(" ".join(args))
            except KeyError:
                return "Saved Sticky Note not found: " + " ".join(args)
        if action == "functions":
            return ("Built-in position offsets f(k), f(0)=0:\n"
                    "  linear [slope=1]: slope*k\n"
                    "  backward: -k\n"
                    "  cubic [scale=1]: scale*k^3\n"
                    "  constant: 0 (imaginary-only progression)\n"
                    "  wave [amplitude=1]: amplitude*(0,1,2,1,0,-1,-2,-1)[k mod 8]\n"
                    "Full registry keys: " + ", ".join(FUNCTION_PARAMETERS))
        if action == "status":
            return self._brief(self.engine.snapshot())
        if action == "inspect":
            v = self.engine.virtual
            return json.dumps({"address": v.logical_address(),
                               "counter_universe": v.snapshot()["counter_universe"],
                               "direction": v.snapshot()["direction"]}, indent=2)
        if action == "open":
            name, params = self._parse_function(args)
            return "Opened pole.\n" + self._brief(self.engine.open_pole(name, params))
        if action == "away":
            return self._brief(self.engine.away())
        if action == "turn":
            if args:
                name, params = self._parse_function(args)
                return self._brief(self.engine.turn(name, params))
            return self._brief(self.engine.turn())
        if action == "toward":
            return self._brief(self.engine.toward())
        if action == "child":
            name, params = self._parse_function(args)
            return self._brief(self.engine.open_child(name, params))
        if action == "pause":
            return self._brief(self.engine.pause())
        if action == "resume":
            return self._brief(self.engine.resume())
        if action == "sync":
            return self._brief_after_sync()
        if action == "checkpoint":
            self.checkpoint()
            return f"Navigator checkpoint saved at {self.checkpoint_path}"
        if action == "restore":
            return "Restored navigator checkpoint.\n" + self._brief(self.restore())
        return "Unknown Navigator command. Type 'navigator help'."

    def _brief_after_sync(self):
        counter = self.terminal.counter
        self.engine.reset_to_linear(counter.get_counters(), counter.universes)
        return "Navigator cleared and synchronized.\n" + self._brief(self.engine.snapshot())

    def checkpoint(self):
        """Save only pole references and active state: no duplicated formulas."""
        snapshot = self.engine.snapshot()
        state = dict(snapshot)
        state["layers"] = [
            {k: v for k, v in frame.items() if k != "definition"}
            for frame in snapshot["layers"]
        ]
        state.pop("entry_seed", None)  # available only at the root pole
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
        # The engine validates the full state against its projection before
        # replacing the live virtual coordinate. Never execute saved commands.
        return self.engine.restore(full)
