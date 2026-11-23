"""Minimal OAIS terminal: command dispatch only.

Sticky Note, Navigation, and Replay logic belong in Commands/.
"""

from dataclasses import dataclass

try:
    from ..utils.counter import Counter
    from ..utils.data_manager import DataManager
    from ..utils.virtual_counter import VirtualCounter
    from ..Commands.Navigator.NavigatorEngine import NavigatorEngine
    from ..Commands.Navigator.Navigator import Navigator
    from ..Commands.StickyNote.StickyNoteEngine import StickyNoteEngine
    from ..Commands.StickyNote.StickyNote import StickyNote
    from ..Commands.Replay.ReplayEngine import ReplayEngine
    from ..Commands.Replay.Replay import Replay
except ImportError:  # python main.py from the project root
    from utils.counter import Counter
    from utils.data_manager import DataManager
    from utils.virtual_counter import VirtualCounter
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
    def __init__(self, counter=None, data_manager=None, sticky_note=None, runtime=None):
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

        # Navigator controls only the virtual projection. Its callback stores
        # each function once, at the pole where this activation opens.
        def register_pole(frame, *, entry_seed=None):
            self.data_manager.save_pole_function(
                frame["pole_real"], frame["definition"],
                counter_universe=frame["pole_counter_universe"],
                function_ref=frame["id"], entry_seed=entry_seed,
            )

        self.navigator_engine = NavigatorEngine(
            self.virtual_counter, on_open=register_pole,
        )

        # One recorder persists for the lifetime of the terminal.
        self.sticky_note = sticky_note if sticky_note is not None else StickyNoteEngine(
            counter=self.counter, data_manager=self.data_manager,
            navigation_provider=self.navigator_engine.snapshot,
        )
        # A supplied recorder may be a legacy instance without an attached Navigator.
        if getattr(self.sticky_note, "navigation_provider", None) is None:
            self.sticky_note.navigation_provider = self.navigator_engine.snapshot

        self.replay_engine = ReplayEngine(self.data_manager)

        self.commands = {
            "help": self.show_help,
            "status": self.status,
            "virtual": self.virtual_command,
            "stickynote": self.sticky_note_command,
            "sticky": self.sticky_note_command,
            "navigator": self.navigator_command,
            "replay": self.replay_command,
            "exit": self.exit_command,
        }

    def attach_host(self, coordinate, universes=0):
        """Temporarily bind OAIS to the host's observed coordinate."""
        self.host_counter.sync(coordinate, universes=universes, save=False)
        # Follow host only while the virtual counter is in FOLLOW mode.
        self.virtual_counter.observe_host(coordinate, universes)
        self.connected = True
        self.counter = self.host_counter
        self.sticky_note.counter = self.counter

    def detach_host(self):
        """Return to OAIS's independent, preserved counter."""
        self.connected = False
        self.counter = self.standalone_counter
        self.sticky_note.counter = self.counter
        # Virtual Counter deliberately retains its projection/mode on detach.

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
        if name == "navigator":
            if action in ("open", "child"):
                return {"op": action, "ref": after["layers"][-1]["id"]}
            if action == "turn":
                if before["layers"] and before["layers"][-1]["leg"] == "toward":
                    return {"op": "child", "ref": after["layers"][-1]["id"]}
                return {"op": "turn"}
            if action in ("away", "toward", "pause", "resume", "sync"):
                return {"op": action}
        if name == "virtual":
            if action == "hold":
                return {"op": "hold"}
            if action == "sync":
                return {"op": "sync"}
        return {"op": "auto" if automatic else "none"}

    def observe_event(self, event):
        """Receive a host event, recording its actual pre-command virtual state."""
        # Before must be captured BEFORE FOLLOW mirrors BASE's after-coordinate.
        before = self.navigator_engine.snapshot()
        if event.get("source") == "base" or event.get("type") == "state":
            self.attach_host(event["coordinate_after"], event.get("universe_after", 0))
        if event.get("type") not in ("command", "transition"):
            return False
        automatic = (event.get("type") == "command"
                     and event.get("source") == "base"
                     and bool(before["layers"]) and before["auto_enabled"])
        if automatic:
            self.navigator_engine.advance_automatic()
        after = self.navigator_engine.snapshot()
        decorated = self._logical_event(
            event, before, after, {"op": "auto" if automatic else "none"},
            follow_update=event.get("source") == "base")
        scope = self.sticky_note.session_metadata.get("scope", self.recording_scope)
        if event.get("source") != "base" and scope != "all":
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
        before = self.counter.get_counters()
        universe_before = self.counter.universes
        before_nav = self.navigator_engine.snapshot()
        follow_update = not self.connected
        if not self.connected:
            self.counter.increment()
            self.virtual_counter.observe_host(self.counter.get_counters(), self.counter.universes)
        return before, universe_before, before_nav, follow_update

    def end_nested_input(self, command, before_state):
        """Record menu inputs only while a recording is already running."""
        if command.strip().lower().split()[0] not in ("start", "save", "clear", "stop"):
            self._own_event(command, *before_state[:2],
                            before_nav=before_state[2],
                            follow_update=before_state[3])

    def default_message(self):
        return f"OAIS Coordinate: {self.counter.get_counters()}\nType 'help' for OAIS commands."

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
                "sticky", "stickynote", "navigator", "replay", "virtual"):
            return OAISResult(False)

        before = self.counter.get_counters()
        universe_before = self.counter.universes
        before_nav = self.navigator_engine.snapshot()
        follow_update = not self.connected
        handler = self.commands.get(name)
        success = handler is not None
        if not self.connected:
            self.counter.increment()
            self.virtual_counter.observe_host(self.counter.get_counters(), self.counter.universes)
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
            "sticky", "stickynote", "navigator", "virtual", "replay", "exit")
            and bool(before_nav["layers"]) and before_nav["auto_enabled"])
        if automatic:
            self.navigator_engine.advance_automatic()
        # Sticky Note menu records its own nested inputs; never reorder those
        # events by recording the outer command after its menu has exited.
        if name not in ("sticky", "stickynote"):
            self._own_event(command, before, universe_before, before_nav=before_nav,
                            success=success, automatic=automatic,
                            follow_update=follow_update)
        return OAISResult(True, str(output), should_exit=(name == "exit" and not connected))

    def run(self, input_func=input, print_func=print):
        self.detach_host()
        print_func(self.default_message())
        while True:
            try:
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
            "- navigator  : Functional virtual navigation (navigator help)\n"
            "- replay     : Play back a coordinate-stored path (replay help)\n"
            "- exit       : Exit standalone OAIS"
        )

    def status(self, arguments=""):
        mode = "connected" if self.connected else "standalone"
        return f"OAIS {mode}: {self.counter.get_counters()}"

    def virtual_command(self, arguments=""):
        """Inspect/synchronize the Virtual Counter. No navigation here yet."""
        action = arguments.strip().lower() or "status"
        if action == "hold":
            state = self.virtual_counter.hold()
            self.navigator_engine.pause()  # HOLD freezes automatic navigation
        elif action == "sync":
            # Explicit resynchronization discards the active imaginary stack.
            state = self.navigator_engine.reset_to_linear(
                self.counter.get_counters(), self.counter.universes
            )
        elif action == "status":
            state = self.virtual_counter.snapshot()
        else:
            return "Usage: virtual [status | hold | sync]"
        return (f"Virtual [{state['mode'].upper()}]: {state['coordinate']} "
                f"(counter_universe {state['universe']}, "
                f"path_universe {state['path_universe']}); "
                f"imaginary={state['imaginary']}, "
                f"function={state['function']}, direction={state['direction']}")

    def sticky_note_command(self, arguments=""):
        return StickyNote(self).run(arguments)

    def navigator_command(self, arguments=""):
        return Navigator(self).run(arguments)

    def replay_command(self, arguments=""):
        return Replay(self).run(arguments)

    def exit_command(self, arguments=""):
        return "Exiting OAIS Terminal."
