"""Minimal OAIS terminal: command dispatch only.

Sticky Note, Navigation, and Replay logic belong in Commands/.
"""

from dataclasses import dataclass
from functools import wraps
import json
import os
from pathlib import Path
import tempfile
from threading import RLock

try:
    from ..utils.counter import Counter
    from ..utils.data_manager import DataManager
    from ..utils.virtual_counter import VirtualCounter, address_to_integer, integer_to_address
    from ..Commands.Navigator.NavigatorEngine import NavigatorEngine
    from ..Commands.Navigator.Navigator import Navigator
    from ..Commands.StickyNote.StickyNoteEngine import StickyNoteEngine
    from ..Commands.StickyNote.StickyNote import StickyNote
    from ..Commands.Replay.ReplayEngine import ReplayEngine
    from ..Commands.Replay.Replay import Replay
except ImportError:  # python main.py from the project root
    from utils.counter import Counter
    from utils.data_manager import DataManager
    from utils.virtual_counter import VirtualCounter, address_to_integer, integer_to_address
    from Commands.Navigator.NavigatorEngine import NavigatorEngine
    from Commands.Navigator.Navigator import Navigator
    from Commands.StickyNote.StickyNoteEngine import StickyNoteEngine
    from Commands.StickyNote.StickyNote import StickyNote
    from Commands.Replay.ReplayEngine import ReplayEngine
    from Commands.Replay.Replay import Replay


@dataclass
class OAISResult:
    handled: bool
    output: str = ""
    should_exit: bool = False


class OaisTerminal:
    def __init__(self, counter=None, data_manager=None, sticky_note=None, runtime=None, terminal_id="oais_standalone", persist_virtual_state=True, legacy_pole_storage=False):
        self.standalone_counter = counter if counter is not None else Counter(load_state=False)
        self.host_counter = Counter(load_state=False)
        self.counter = self.standalone_counter
        # Separate, virtual-only position: never replaces or writes Counter.
        self.virtual_counter = VirtualCounter(
            self.standalone_counter.get_counters(),
            self.standalone_counter.universes,
        )
        self.data_manager = data_manager if data_manager is not None else DataManager()
        self.runtime = runtime
        self.connected = False
        self.source_name = "base"
        self.recording_scope = "all"
        self._explicit_hold = False

        # Ordinary Navigator functions live in virtual_coordinate.json and in
        # a Sticky Note's private starting state / event plan. They must NOT
        # create pole_function objects in shared coordinate storage. Keep the
        # old callback only as an explicit opt-in to write historical v4 notes;
        # previously stored v4 notes can still be read with their pole objects.
        def register_pole(frame, *, entry_seed=None):
            self.data_manager.save_pole_function(
                frame["pole_real"], frame["definition"],
                counter_universe=frame["pole_counter_universe"],
                function_ref=frame["id"], entry_seed=entry_seed,
            )

        self.navigator_engine = NavigatorEngine(
            self.virtual_counter,
            on_open=register_pole if legacy_pole_storage else None,
        )

        # Persisted source ownership matters: restoring a BASE excursion into
        # standalone OAIS (or the reverse) must not silently reuse its pole.
        # The Meta Terminal's parent mirror is read-only; only its OAIS worker
        # writes the live checkpoint, avoiding competing process writes.
        self.persist_virtual_state = bool(persist_virtual_state)
        self._virtual_save_lock = RLock()
        self.virtual_state_path = self.data_manager.base_dir / "virtual_coordinate.json"
        self._source_mode = "oais"
        self._source_position = (self.standalone_counter.get_counters(),
                                 self.standalone_counter.universes)
        self._source_confirmed = False
        self._suspended_context = None
        if self.virtual_state_path.exists():
            with self.virtual_state_path.open("r", encoding="utf-8") as stream:
                saved = json.load(stream)
            if not isinstance(saved, dict):
                raise ValueError("Invalid virtual_coordinate.json")
            # Read old v9/v10 files once, then write compact v11 on the next
            # checkpoint. No manual migration is necessary.
            old_state = saved.get("navigation")
            if old_state is not None:
                self.navigator_engine.restore(old_state)
            else:
                self.navigator_engine.restore_portable(saved)
            previous_source = saved.get("source", "oais")
            if (not isinstance(previous_source, str) or not previous_source or
                    not all(c.isalnum() or c in "_-" for c in previous_source)):
                raise ValueError("Invalid persisted navigation source")
            self._source_mode = previous_source
            previous_position = saved.get("source_coordinate")
            previous_universes = saved.get("source_universes")
            if previous_position is None and old_state is not None:
                observed = old_state["virtual"].get("host")
                if isinstance(observed, dict):
                    previous_position = observed.get("coordinate")
                    previous_universes = observed.get("counter_universe")
            if previous_position is None:
                previous_position = saved["coordinate"]
                previous_universes = saved.get("universes", 0)
            self._source_position = integer_to_address(
                address_to_integer(previous_position, previous_universes or 0))
            self._explicit_hold = bool(saved.get("held", False))
            self._suspended_context = saved.get("suspended_context")
            if (isinstance(self._suspended_context, dict) and
                    "navigation" in self._suspended_context):
                previous = self._suspended_context
                self._suspended_context = self.navigator_engine.portable_state(
                    previous["navigation"], source=previous["source"],
                    source_coordinate=previous["source_coordinate"],
                    source_universes=previous["source_universes"])
        if self.persist_virtual_state:
            self._install_virtual_persistence()
            if not self.virtual_state_path.exists():
                self.save_virtual_coordinate()

        # One recorder persists for the lifetime of the terminal.
        self.sticky_note = sticky_note if sticky_note is not None else StickyNoteEngine(
            counter=self.counter, data_manager=self.data_manager,
            navigation_provider=self.navigator_engine.snapshot,
            navigation_context_provider=self.navigation_context,
            terminal_id=terminal_id,
        )
        # A supplied recorder may be a legacy instance without an attached Navigator.
        if getattr(self.sticky_note, "navigation_provider", None) is None:
            self.sticky_note.navigation_provider = self.navigator_engine.snapshot
        if getattr(self.sticky_note, "navigation_context_provider", None) is None:
            self.sticky_note.navigation_context_provider = self.navigation_context

        self.replay_engine = ReplayEngine(self.data_manager, terminal_id=self.sticky_note.terminal_id)

        self.commands = {
            "help": self.show_help,
            "status": self.status,
            "virtual": self.virtual_command,
            "stickynote": self.sticky_note_command,
            "sticky": self.sticky_note_command,
            "navigator": self.navigator_command,
            "function": self.function_command,
            "replay": self.replay_command,
            "exit": self.exit_command,
        }

    def navigation_context(self, snapshot=None):
        """Same portable function context for live state and Sticky Note entry."""
        state = snapshot if snapshot is not None else self.navigator_engine.snapshot()
        context = self.navigator_engine.portable_state(
            state, source=self._source_mode,
            source_coordinate=self._source_position[0],
            source_universes=self._source_position[1])
        if self._explicit_hold:
            context["held"] = True
        return context

    def save_virtual_coordinate(self):
        """Atomically persist the current projection and exact resume snapshot."""
        with self._virtual_save_lock:
            if not self.persist_virtual_state:
                return self.navigation_context()
            return self._write_virtual_coordinate()

    def _write_virtual_coordinate(self):
        state = self.navigator_engine.snapshot()
        payload = self.navigation_context(state)
        # Only the mathematically sufficient pole and k stack are persistent.
        # Activation IDs and runtime path history stay in the live Navigator.
        if self._suspended_context is not None:
            payload["suspended_context"] = self._suspended_context
        path = self.virtual_state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".virtual_coordinate-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(payload, output, indent=4, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return payload

    def _install_virtual_persistence(self):
        # Capture menu-driven navigation too: these commands do not necessarily
        # pass through OaisTerminal.process_command(). Nested calls are safe.
        names = ("open_pole", "push_function", "open_child", "away", "toward",
                 "turn", "advance_host_direction", "advance_automatic",
                 "advance_linear", "pause", "resume", "reset_to_linear", "restore")
        for name in names:
            original = getattr(self.navigator_engine, name, None)
            if original is None:
                continue
            @wraps(original)
            def persist(*args, _original=original, **kwargs):
                result = _original(*args, **kwargs)
                self.save_virtual_coordinate()
                return result
            setattr(self.navigator_engine, name, persist)

    def navigation_origin(self):
        """BASE while connected; OAIS's own Counter when standalone."""
        source = self.host_counter if self.connected else self.standalone_counter
        return source.get_counters(), source.universes

    def _select_navigation_source(self, name, coordinate, universes):
        """Choose one source; rebase once on a switch or stale restart.

        Ordinary movement of an already-connected source must NEVER rebase the
        stack: the following event still needs to advance exactly one k tick.
        """
        position = integer_to_address(address_to_integer(coordinate, universes))
        needs_rebase = (name != self._source_mode or
                        (not self._source_confirmed and position != self._source_position))
        if needs_rebase:
            recorder = getattr(self, "sticky_note", None)
            if recorder is not None and (recorder.active or recorder.get_path()):
                raise ValueError("Save or clear the Sticky Note before changing navigation source.")
            old_snapshot = self.navigator_engine.snapshot()
            if old_snapshot["layers"]:
                self._suspended_context = self.navigation_context(old_snapshot)
        # Set the new source before reset_to_linear's save hook fires. This
        # prevents a transient checkpoint with new coordinates and old source.
        self._source_mode = name
        self._source_position = position
        self._source_confirmed = True
        if needs_rebase:
            self.navigator_engine.reset_to_linear(*position)
            self._explicit_hold = False
        return needs_rebase

    def attach_host(self, coordinate, universes=0, source="base"):
        """Follow a connected program's real or OAIS-synthesized coordinates."""
        self._select_navigation_source(source, coordinate, universes)
        self.source_name = source
        self.host_counter.sync(coordinate, universes=universes, save=False)
        self.connected = True
        self.virtual_counter.observe_host(coordinate, universes)
        self.save_virtual_coordinate()

    def detach_host(self):
        """Standalone mode: rebase virtual progression to OAIS's own Counter."""
        position = (self.standalone_counter.get_counters(),
                    self.standalone_counter.universes)
        self._select_navigation_source("oais", *position)
        self.connected = False
        self.virtual_counter.observe_host(*position)
        self.save_virtual_coordinate()

    def coordinate_display(self):
        """Show independent OAIS real and BASE/OAIS-derived virtual coordinates."""
        v = self.virtual_counter.snapshot()
        source = self.source_name.upper() if self.connected else "OAIS"
        frames = self.navigator_engine.compact_state()["functions"]
        activity = (f" | f(k)={frames[-1]['f']} | k={frames[-1]['k']}"
                    if frames else " | linear")
        return (f"OAIS Counter:    {self.standalone_counter.get_counters()} "
                f"(U={self.standalone_counter.universes})\n"
                f"Virtual Counter: {v['coordinate']} "
                f"(U={v['counter_universe']}, source={source}, {v['mode'].upper()})"
                f"{activity}")

    def coordinate_payload(self):
        """Lightweight state for Meta Terminal's screen switch."""
        return {"oais": self.standalone_counter.get_counters(),
                "oais_universe": self.standalone_counter.universes,
                "virtual": self.virtual_counter.coordinate,
                "virtual_universe": self.virtual_counter.universe,
                "virtual_mode": self.virtual_counter.mode,
                "active": self.navigator_engine.compact_state()["functions"],
                "source": self.source_name.upper() if self.connected else "OAIS",
                "source_coordinate": self._source_position[0],
                "source_universes": self._source_position[1]}

    def _logical_event(self, event, before, after, operation, *, follow_update=False):
        """Annotate only the in-memory recording with pre/post virtual state.

        Saving later writes the pre-address and operation, not a next pointer.
        """
        payload = dict(event)
        bv, av = before["virtual"], after["virtual"]
        payload.update({
            "logical_before": self.data_manager.validate_logical_address(
                [bv["coordinate"], bv["imaginary"], bv["function"], bv["path_universe"]]),
            "logical_after": self.data_manager.validate_logical_address(
                [av["coordinate"], av["imaginary"], av["function"], av["path_universe"]]),
            "logical_counter_universe_before": bv["counter_universe"],
            "logical_counter_universe_after": av["counter_universe"],
            "logical_direction_before": bv["direction"],
            "logical_direction_after": av["direction"],
            "navigation": operation,
            "follow_update": bool(follow_update),
        })
        if "coordinate_after" in payload:
            payload["host_after"] = payload["coordinate_after"]
            payload["host_universe_after"] = int(payload.get("universe_after", 0))
        return payload

    @staticmethod
    def _operation_for_own(text, before, after, success=True, automatic=False):
        if not success:
            return {"op": "none"}
        command = text.strip().lower()
        name, _, argstr = command.partition(" ")
        action = argstr.strip().split(" ", 1)[0] if argstr.strip() else "status"
        if name == "function":
            action = "function"
        if name in ("navigator", "function"):
            if action in ("open", "set", "function", "custom", "child"):
                # Every activation after the root is a new independent pole.
                opening = {"op": "push" if before["layers"] else "open",
                           "ref": after["layers"][-1]["id"],
                           "f": after["layers"][-1]["definition"]["f"]}
                if opening["op"] == "open":
                    opening["seed"] = after["entry_seed"]
                if (not before["layers"] and
                        (before["virtual"]["coordinate"] != after["layers"][-1]["pole_real"] or
                         before["virtual"]["counter_universe"] !=
                         after["layers"][-1]["pole_counter_universe"])):
                    opening["anchor"] = after["layers"][-1]["pole_real"]
                    opening["counter_universe"] = after["layers"][-1]["pole_counter_universe"]
                return opening
            if action == "turn":
                if before["layers"] and before["layers"][-1]["leg"] == "toward":
                    return {"op": "child", "ref": after["layers"][-1]["id"],
                            "f": after["layers"][-1]["definition"]["f"]}
                return {"op": "turn"}
            if action in ("away", "toward", "pause", "resume", "sync"):
                if action == "sync":
                    v = after["virtual"]
                    return {"op": "sync", "target": v["coordinate"],
                            "counter_universe": v["counter_universe"]}
                return {"op": action}
        if name == "virtual":
            if action == "hold":
                return {"op": "hold"}
            if action == "sync":
                v = after["virtual"]
                return {"op": "sync", "target": v["coordinate"],
                        "counter_universe": v["counter_universe"]}
        if (not before["layers"] and before["virtual"]["mode"] == "free"
                and after["virtual"]["mode"] == "follow"):
            v = after["virtual"]
            return {"op": "sync", "target": v["coordinate"],
                    "counter_universe": v["counter_universe"]}
        return {"op": "auto_forward" if automatic else "none"}

    def observe_event(self, event):
        """Observe a connected program, including programs without coordinates.

        The host's native position is authoritative when provided. Otherwise
        OAIS synthesizes a base-60 source counter, one tick per observed input
        (unless the adapter explicitly reports a movement). This counter is
        not the independent OAIS Counter or the functional Virtual Counter.
        """
        event = dict(event)
        source = event.get("source", self.source_name)
        kind = event.get("type")
        external = source not in ("oais", "meta")
        before = self.navigator_engine.snapshot()
        if external and kind in ("command", "state"):
            if event.get("coordinate_after") is None:
                if self._source_mode != source or not self.connected:
                    # A fresh coordinate-free connection begins at zero.
                    self.attach_host("0 0 0 0 0 0", 0, source=source)
                coordinate, universe = self._source_position
                if kind == "command":
                    movement = event.get("movement")
                    if movement is None:
                        movement = 1
                    if isinstance(movement, bool) or not isinstance(movement, int):
                        raise ValueError("Host movement must be an integer or None.")
                    after_coordinate, after_universe = integer_to_address(
                        address_to_integer(coordinate, universe) + movement)
                    event.update(coordinate_before=coordinate,
                                 universe_before=universe,
                                 coordinate_after=after_coordinate,
                                 universe_after=after_universe)
                else:
                    event.update(coordinate_after=coordinate,
                                 universe_after=universe)
            self.attach_host(event["coordinate_after"],
                             event.get("universe_after", 0), source=source)
        if kind not in ("command", "transition"):
            return False
        automatic = (kind == "command" and external and
                     bool(before["layers"]) and before["auto_enabled"])
        follow_restarted = False
        # Preserve the v13 BASE rule. Other adapters can report a signed
        # movement without adopting BASE's `backwards` command spelling.
        movement = event.get("movement")
        if movement is not None and type(movement) is not int:
            raise ValueError("Host movement must be an integer or None.")
        backwards = (external and
                     (movement is not None and movement < 0 or
                      source == "base" and
                      event.get("value", "").strip().split(" ", 1)[0].lower() == "backwards"))
        if automatic:
            self.navigator_engine.advance_host_direction(-1 if backwards else 1)
        elif (external and kind == "command" and not before["layers"]
              and self.virtual_counter.mode == "free" and not self._explicit_hold):
            self.navigator_engine.reset_to_linear(
                event["coordinate_after"], event.get("universe_after", 0))
            follow_restarted = True
        after = self.navigator_engine.snapshot()
        nav_op = {"op": ("auto_back" if backwards else "auto_forward")
                  if automatic else "sync" if follow_restarted else "none"}
        if follow_restarted:
            nav_op.update(target=after["virtual"]["coordinate"],
                          counter_universe=after["virtual"]["counter_universe"])
        decorated = self._logical_event(
            event, before, after, nav_op, follow_update=external)
        scope = self.sticky_note.session_metadata.get("scope", self.recording_scope)
        if not external and scope != "all":
            return False
        return self.sticky_note.record_event(decorated)

    def _own_event(self, text, before_coordinate, before_universe, *,
                   before_nav=None, success=True, automatic=False,
                   follow_update=False):
        if not text.strip():
            return
        after_nav = self.navigator_engine.snapshot()
        before_nav = before_nav if before_nav is not None else after_nav
        operation = self._operation_for_own(text, before_nav, after_nav,
                                             success=success, automatic=automatic)
        scope = self.sticky_note.session_metadata.get("scope", self.recording_scope)
        # BASE-only recordings still require NAVIGATOR control transitions.
        if scope != "all" and operation["op"] == "none":
            return
        event = {
            "type": "command", "source": "oais", "value": text,
            "coordinate_before": before_coordinate,
            "coordinate_after": self.counter.get_counters(),
            "universe_before": before_universe,
            "universe_after": self.counter.universes,
            "success": success,
        }
        self.sticky_note.record_event(self._logical_event(
            event, before_nav, after_nav, operation,
            follow_update=follow_update))

    def begin_nested_input(self, command):
        """Called before processing a command inside the OAIS Sticky Note menu."""
        if not self.connected and (self._source_mode != "oais" or not self._source_confirmed):
            self.detach_host()
        before = self.counter.get_counters()
        universe_before = self.counter.universes
        before_nav = self.navigator_engine.snapshot()
        follow_update = not self.connected
        self.standalone_counter.increment()
        if not self.connected:
            self._source_position = (self.counter.get_counters(), self.counter.universes)
            self.virtual_counter.observe_host(*self._source_position)
        if (not before_nav["layers"] and self.virtual_counter.mode == "free"
                and not self._explicit_hold):
            coordinate, universe = self.navigation_origin()
            self.navigator_engine.reset_to_linear(coordinate, universe)
        return before, universe_before, before_nav, follow_update

    def end_nested_input(self, command, before_state, *, success=True):
        """Record menu inputs only while a recording is already running."""
        if command.strip().lower().split()[0] not in ("start", "save", "clear", "stop"):
            self._own_event(command, *before_state[:2],
                            before_nav=before_state[2], success=success,
                            follow_update=before_state[3])

    def default_message(self):
        return "Type 'help' for OAIS commands."

    def process_command(self, command, connected=False):
        """Dispatch OAIS command; keep Navigator and recording event order exact."""
        command = command.strip()
        if not command:
            return OAISResult(False)
        prefixed = command.lower() == "oais" or command.lower().startswith("oais ")
        if prefixed:
            command = command[4:].strip() or "help"
        name, _, arguments = command.partition(" ")
        name = name.lower()
        if connected and not prefixed and name not in (
                "sticky", "stickynote", "navigator", "function", "replay", "virtual"):
            return OAISResult(False)

        if (name != "replay" and not self.connected and
                (self._source_mode != "oais" or not self._source_confirmed)):
            self.detach_host()
        before = self.counter.get_counters()
        universe_before = self.counter.universes
        before_nav = self.navigator_engine.snapshot()
        follow_update = not self.connected
        handler = self.commands.get(name)
        success = handler is not None
        # Replay is inspection, not a navigation event. Keep the independent
        # OAIS Counter and the current mathematical state untouched.
        if name != "replay":
            self.standalone_counter.increment()
            if not self.connected:
                self._source_position = (self.counter.get_counters(), self.counter.universes)
                self.virtual_counter.observe_host(*self._source_position)
        # After an excursion finishes, the next ordinary command returns to
        # source-following instead of drifting along the old virtual pole.
        if (not before_nav["layers"] and self.virtual_counter.mode == "free"
                and not self._explicit_hold and name not in ("navigator", "function", "virtual", "replay")):
            coordinate, universe = self.navigation_origin()
            self.navigator_engine.reset_to_linear(coordinate, universe)
        if handler is None:
            output = f"Unknown OAIS command: {name}"
        else:
            try:
                if (name == "navigator" and arguments.strip().split(" ", 1)[0].lower() == "restore"
                        and (self.sticky_note.active or self.sticky_note.get_path())):
                    raise ValueError("Save or clear the temporary Sticky Note before restoring a checkpoint.")
                output = handler(arguments.strip())
            except (ValueError, TypeError, OSError) as exc:
                output = f"OAIS command error: {exc}"
                success = False

        automatic = (not self.connected and name not in (
            "sticky", "stickynote", "navigator", "function", "virtual", "replay", "exit")
            and bool(before_nav["layers"]) and before_nav["auto_enabled"])
        if automatic:
            self.navigator_engine.advance_host_direction(1)
        # Sticky Note menu records its own nested inputs; never reorder those
        # events by recording the outer command after its menu has exited.
        if name not in ("sticky", "stickynote", "replay") and not (name == "navigator" and not arguments.strip()):
            self._own_event(command, before, universe_before, before_nav=before_nav,
                            success=success, automatic=automatic,
                            follow_update=follow_update)
        if name != "replay":
            self.save_virtual_coordinate()
        return OAISResult(True, str(output), should_exit=(name == "exit" and not connected))

    def run(self, input_func=input, print_func=print):
        self.detach_host()
        print_func(self.default_message())
        while True:
            try:
                print_func(self.coordinate_display())
                command = input_func("OAIS > ")
            except (EOFError, KeyboardInterrupt):
                break
            result = self.process_command(command, connected=False)
            if result.output:
                print_func(result.output)
            if result.should_exit:
                break

    def show_help(self, arguments=""):
        return (
            "OAIS commands:\n"
            "- help       : Show this help\n"
            "- status     : Show current coordinate\n"
            "- virtual    : Show virtual address (virtual hold / virtual sync)\n"
            "- stickynote : Open Sticky Note menu (or use 'stickynote start')\n"
            "- navigator  : Interactive function terminal (navigator help)\n"
            "- function   : Select a function, preserving existing layers\n"
            "- replay     : Browse saved Sticky Notes and display their command paths\n"
            "- exit       : Exit standalone OAIS"
        )

    def status(self, arguments=""):
        return self.coordinate_display()

    def virtual_command(self, arguments=""):
        """Inspect/synchronize the Virtual Counter. No navigation here yet."""
        action = arguments.strip().lower() or "status"
        if action == "hold":
            state = self.virtual_counter.hold()
            self._explicit_hold = True
            self.navigator_engine.pause()  # HOLD freezes automatic navigation
        elif action == "sync":
            # Explicit resynchronization discards the active imaginary stack.
            coordinate, universe = self.navigation_origin()
            self._explicit_hold = False
            state = self.navigator_engine.reset_to_linear(coordinate, universe)
        elif action == "status":
            state = self.virtual_counter.snapshot()
        else:
            return "Usage: virtual [status | hold | sync]"
        functions = self.navigator_engine.compact_state()["functions"]
        sequence = " > ".join(
            f"{layer['f']} (k={layer['k']}, "
            f"{'out' if layer['direction'] == 1 else 'back'})"
            for layer in functions
        )
        return (f"Virtual [{state['mode'].upper()}]: {state['coordinate']} "
                f"(counter_universe {state['universe']}); "
                f"layers: {sequence or 'linear'}")

    def sticky_note_command(self, arguments=""):
        return StickyNote(self).run(arguments)

    def navigator_command(self, arguments=""):
        return Navigator(self).run(arguments)

    def function_command(self, arguments=""):
        """Short form for `navigator function <f(k)>`, including from BASE."""
        if not arguments.strip():
            return "Usage: function <preset or f(k)> (e.g. function k**3)"
        return Navigator(self).process_command("function " + arguments)

    def replay_command(self, arguments=""):
        return Replay(self).run(arguments)

    def exit_command(self, arguments=""):
        return "Exiting OAIS Terminal."
