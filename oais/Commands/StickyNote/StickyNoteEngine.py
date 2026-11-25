# OAIS/Commands/StickyNote/StickyNoteEngine.py

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from threading import RLock
import uuid

try:
    from ...utils.counter import Counter
    from ...utils.data_manager import DataManager
    from ...utils.virtual_counter import VirtualCounter, seed_path_universe, evolve_path_universe, address_to_integer
    from ..Navigator.NavigatorEngine import NavigatorEngine, expression_for_definition, evaluate_offset
except ImportError:  # python main.py from the project root
    from utils.counter import Counter
    from utils.data_manager import DataManager
    from utils.virtual_counter import VirtualCounter, seed_path_universe, evolve_path_universe, address_to_integer
    from Commands.Navigator.NavigatorEngine import NavigatorEngine, expression_for_definition, evaluate_offset


class StickyNoteEngine:
    """
    Universal OAIS path recorder.

    StickyNoteEngine does NOT know about:

        - DEEP Terminal
        - Pygame
        - physical keyboards
        - terminal prompts
        - F8
        - replay
        - specific IO backends

    It only knows how to:

        - begin recording
        - receive OAIS events
        - pause/resume recording
        - hold a temporary path
        - clear a temporary path
        - save a path
        - list saved paths
        - read saved paths

    Input/connection systems are responsible for calling:

        record_event(...)

    whenever something relevant occurs.
    """

    OBJECT_TYPE = "sticky_note"


    def __init__(
        self,
        counter=None,
        data_manager=None,
        state_provider=None,
        navigation_provider=None,
        navigation_context_provider=None,
        terminal_id="oais_standalone",
    ):
        """
        counter:
            OAIS counter used for storage coordinates.

        data_manager:
            OAIS DataManager shared by the runtime.

        state_provider:
            Optional callable returning the current state of
            whatever system OAIS is observing.

            Example:

                state_provider = connection.get_state

            Sticky Note does not care what that state looks like.
        """

        self.counter = (
            counter
            or Counter()
        )

        self.data_manager = (
            data_manager
            or DataManager()
        )

        self.state_provider = (
            state_provider
        )
        # Optional source of the pure Navigator snapshot at recording start.
        # Standalone legacy StickyNoteEngine instances do not require it.
        self.navigation_provider = navigation_provider
        # Optional portable companion to navigation_provider(snapshot). The
        # terminal supplies source identity without coupling this engine to JSON.
        self.navigation_context_provider = navigation_context_provider
        self.terminal_id = DataManager._safe_storage_name(terminal_id, "Terminal ID")
        self.navigation_start = None
        self.navigation_context_start = None
        self.route_seed = None
        self.note_id = None

        self.active = False
        self.paused = False

        self.path = []

        self.start_coordinate = None
        self.start_state = None

        self.started_at = None

        self.session_metadata = {}

        self._lock = RLock()


    # ==========================================================
    # RECORDING LIFECYCLE
    # ==========================================================

    def start(
        self,
        clear=True,
        metadata=None,
    ):
        """
        Begin recording events.

        Starting Sticky Note does not start an IO listener.
        IO systems should already exist independently and
        publish events through record_event().
        """

        with self._lock:

            if clear:
                self.path.clear()

            self.active = True
            self.paused = False

            self.start_coordinate = (
                self.current_coordinate()
            )

            self.start_state = (
                self.current_state()
            )

            self.started_at = (
                self._timestamp()
            )

            self.session_metadata = (
                deepcopy(metadata)
                if metadata
                else {}
            )
            self.navigation_start = None
            self.navigation_context_start = None
            self.route_seed = None
            self.note_id = None
            if self.session_metadata.get("storage") == "logical":
                if self.navigation_provider is None:
                    raise ValueError("Logical Sticky Note requires a Navigator state provider.")
                self.navigation_start = deepcopy(self.navigation_provider())
                if self.navigation_context_provider is not None:
                    self.navigation_context_start = deepcopy(
                        self.navigation_context_provider(self.navigation_start))
                else:
                    self.navigation_context_start = NavigatorEngine.portable_state(
                        self.navigation_start)
                self.route_seed = uuid.uuid4().hex
                self.note_id = uuid.uuid4().hex[:12]

            return self.status()


    def stop(
        self,
        clear=False,
    ):
        """
        Stop recording.

        By default the temporary path remains available.

        This is intentional:

            stop
              ↓
            inspect
              ↓
            save

        should be possible.

        Clearing is a separate operation.
        """

        with self._lock:

            self.active = False
            self.paused = False

            if clear:
                self._clear_unlocked()

            return self.status()


    def pause(self):

        with self._lock:

            if self.active:
                self.paused = True

            return self.status()


    def resume(self):

        with self._lock:

            if self.active:
                self.paused = False

            return self.status()


    # ==========================================================
    # EVENT RECORDING
    # ==========================================================

    def record_event(
        self,
        event,
    ):
        """
        Record one event into the current temporary path.

        Event may initially be as simple as:

            "forwards"

        or:

            {
                "type": "command",
                "value": "forwards"
            }

        More sophisticated connections may later provide:

            {
                "type": "command",
                "value": "forwards",
                "source": "deep_terminal",
                "state_before": {...},
                "state_after": {...}
            }

        Sticky Note stores the event without needing to
        understand the host-specific details.
        """

        with self._lock:

            if not self.active:
                return False

            if self.paused:
                return False

            normalized = (
                self._normalize_event(
                    event
                )
            )

            normalized["sequence"] = (
                len(self.path)
            )

            self.path.append(
                normalized
            )

            return True


    def record_command(
        self,
        command,
        source=None,
        metadata=None,
    ):
        """
        Convenience wrapper for command-based hosts.

        DEEP's current input observer can use this immediately.
        """

        event = {
            "type": "command",
            "value": str(command),
        }

        if source is not None:
            event["source"] = source

        if metadata:
            event["metadata"] = deepcopy(
                metadata
            )

        return self.record_event(
            event
        )


    # ==========================================================
    # TEMPORARY PATH
    # ==========================================================

    def get_path(self):

        with self._lock:

            return deepcopy(
                self.path
            )


    def clear(self):

        with self._lock:

            self._clear_unlocked()

            return self.status()


    def _clear_unlocked(self):

        self.path.clear()

        self.start_coordinate = None
        self.start_state = None
        self.started_at = None
        self.session_metadata = {}
        self.navigation_start = None
        self.navigation_context_start = None
        self.route_seed = None
        self.note_id = None


    # ==========================================================
    # SAVING
    # ==========================================================

    def save(
        self,
        title="Sticky Note",
        metadata=None,
        clear=False,
        storage_coordinate=None,
    ):
        """Save a compact, linked path; preserve the older save() API."""
        note = self.save_reference(
            title=title,
            storage_coordinate=storage_coordinate,
            metadata=metadata,
        )
        if clear:
            self.stop(clear=True)
        return note

    def save_reference(self, title="Sticky Note", text_path=None,
                       storage_coordinate=None, metadata=None):
        """Commit lightweight cached commands in reverse order to link successors.

        Each coordinate holds only command text, universe, next locator, and
        optionally source. The Sticky Note holds only endpoint references.
        No coordinate writes occur until this method runs.
        """
        with self._lock:
            if not self.path:
                raise ValueError("No events to save")
            if self.session_metadata.get("storage") == "logical":
                if self.session_metadata.get("storage_version") == 4:
                    return self._save_logical_reference(title, storage_coordinate)
                return self._save_compact_logical_reference(title, storage_coordinate)
            writes = []
            next_locator = None
            try:
                for event in reversed(self.path):
                    coord = event.get("coordinate_before") or self.start_coordinate
                    coord = self.data_manager.coordinate_string(coord)
                    source = str(event.get("source", "base"))
                    # 'meta' identifies terminal transitions; no output/status blobs.
                    locator = self.data_manager.save_command(
                        coord, event.get("value", ""),
                        event.get("universe_before", 0), next_locator, source
                    )
                    writes.append(locator)
                    next_locator = locator
                start = next_locator
                end = writes[0]
                final_event = self.path[-1]
                after = [self.data_manager.coordinate_string(
                    final_event.get("coordinate_after") or end[0]
                ), int(final_event.get("universe_after", 0))]
                result = self.data_manager.save_sticky_pointer(
                    storage_coordinate or start[0], title, start, end, after,
                    self.session_metadata.get("scope", "all")
                )
            except Exception:
                # Reverse append order: earlier-in-path commands were appended last.
                for locator in reversed(writes):
                    try:
                        self.data_manager.delete_last_command(locator)
                    except Exception:
                        pass
                raise
            return deepcopy(result)

    # ==========================================================
    # LOGICAL STICKY NOTES (v4)
    # ==========================================================

    @staticmethod
    def _portable_navigation(snapshot):
        """Only retain pole references; mathematical definitions stay at poles."""
        state = deepcopy(snapshot)
        state["layers"] = [
            {k: v for k, v in frame.items() if k != "definition"}
            for frame in state["layers"]
        ]
        state.pop("entry_seed", None)
        return state

    def _hydrate_navigation(self, portable):
        """Restore a reader from its starting coordinate, without scanning paths."""
        state = deepcopy(portable)
        if state.get("version") != 1 or not isinstance(state.get("layers"), list):
            raise ValueError("Invalid saved navigator starting state.")
        for frame in state["layers"]:
            pole = self.data_manager.load_pole_function(
                frame["pole_real"], frame["id"],
                counter_universe=frame["pole_counter_universe"])
            frame["definition"] = pole["definition"]
        if state["layers"]:
            root = state["layers"][0]
            pole = self.data_manager.load_pole_function(
                root["pole_real"], root["id"],
                counter_universe=root["pole_counter_universe"])
            state["entry_seed"] = pole.get("entry_seed")
        else:
            state["entry_seed"] = None
        virtual = VirtualCounter()
        navigator = NavigatorEngine(virtual)
        navigator.restore(state)
        return navigator

    @staticmethod
    def _logical_event_id(route_seed, index, address, counter_universe, direction):
        """Step-local deterministic lookup identity; never store a recording ID.

        The only seed is held by the Sticky Note at its starting coordinate.
        Repeated or stationary full addresses remain individually addressable.
        """
        packed = json.dumps(
            [4, route_seed, index, address, counter_universe, direction],
            separators=(",", ":"), sort_keys=True, allow_nan=False,
        ).encode("utf-8")
        return "se_" + hashlib.blake2b(
            packed, digest_size=16, person=b"OAISSticky-v4").hexdigest()

    def _advance_recorded_navigation(self, navigator, block):
        """Simulate address movement ONLY; never execute the stored command."""
        host_after = block.get("host_after")
        if host_after is not None and block.get("follow_update", False):
            navigator.virtual.observe_host(
                host_after, block.get("host_universe_after", 0))
        nav = block.get("navigation", {"op": "none"})
        op = nav.get("op", "none")
        if op == "none":
            if (not navigator.layers and navigator.virtual.mode == "free"
                    and block.get("follow_update") and host_after is not None
                    and block.get("host_before") is not None):
                delta = (address_to_integer(host_after, block.get("host_universe_after", 0)) -
                         address_to_integer(block["host_before"], block.get("host_universe_before", 0)))
                navigator.advance_linear(delta)
            return
        if op in ("auto", "auto_back", "auto_forward"):
            result = (navigator.advance_host_direction(-1 if op == "auto_back" else 1)
                      if op != "auto" else navigator.advance_automatic())
            if result is None:
                raise ValueError("Recorded automatic navigation has no active function.")
        elif op in ("open", "child", "push"):
            if op == "open" and nav.get("anchor") is not None:
                navigator.reset_to_linear(nav["anchor"], nav.get("counter_universe", 0))
            ref = nav["ref"]
            # v12 normal recordings already contain the mathematical expression
            # in their in-memory event. Never resolve newly opened functions
            # from shared coordinate objects; those only contain commands.
            if "f" in nav:
                expression = nav["f"]
                seed = nav.get("seed")
                if op == "open":
                    navigator.open_pole(expression, seed=seed, activation_id=ref)
                elif op == "push":
                    navigator.push_function(expression, activation_id=ref)
                else:
                    navigator.open_child(expression, activation_id=ref)
            else:
                # Read older v4 transition events that used pole_function
                # objects. This is backward compatibility, not a new write.
                state = navigator.virtual.snapshot()
                definition = self.data_manager.load_pole_function(
                    state["coordinate"], ref,
                    counter_universe=state["counter_universe"])
                spec = definition["definition"]
                if op == "open":
                    navigator.open_pole(spec["name"], spec.get("params"),
                                        seed=definition.get("entry_seed"), activation_id=ref)
                elif op == "push":
                    navigator.push_function(spec["name"], spec.get("params"), activation_id=ref)
                else:
                    navigator.open_child(spec["name"], spec.get("params"),
                                         activation_id=ref)
        elif op == "away":
            navigator.away()
        elif op == "turn":
            navigator.turn()
        elif op == "toward":
            navigator.toward()
        elif op == "pause":
            navigator.pause()
        elif op == "resume":
            navigator.resume()
        elif op == "hold":
            navigator.virtual.hold()
            navigator.pause()
        elif op == "sync":
            target = nav.get("target", host_after)
            if target is None:
                raise ValueError("Synchronization event has no target.")
            navigator.reset_to_linear(
                target, nav.get("counter_universe", block.get("host_universe_after", 0)))
        else:
            raise ValueError("Unsupported recorded navigation operation: " + str(op))

    @staticmethod
    def _check_cursor(navigator, address, counter_universe, direction):
        v = navigator.virtual
        if (v.logical_address() != address or v.universe != counter_universe
                or v.direction != direction):
            raise ValueError("Saved Sticky Note traversal diverged from its logical address.")

    @staticmethod
    def _portable_signature(snapshot):
        """Hashable projection independent of random pole activation references.

        This is the v5/v6 on-disk history convention; changing it later
        requires a separate hash version and reader. Runtime Navigator history
        uses its own unrelated path-universe calculation.
        """
        layers = snapshot["layers"]
        v = snapshot["virtual"]
        stack = [{"f": expression_for_definition(layer["definition"]),
                  "k": layer["k"],
                  "direction": -1 if layer["leg"] == "toward" else 1}
                 for layer in layers]
        return [v["coordinate"], stack, stack[-1]["f"] if stack else "k"]

    def _save_compact_logical_reference(self, title, storage_coordinate=None):
        """Write existing compact public command blocks and a private v11 plan.

        The terminal note owns the complete starting mathematical context and
        ordered event plan; public coordinate blocks contain only compact
        command data/history keys and optional selector indexes. Replay is
        intentionally separate and is not invoked by saving a note.
        """
        if self.navigation_start is None or self.note_id is None:
            raise ValueError("Missing logical recording origin or note identity.")
        navigator = NavigatorEngine(VirtualCounter())
        navigator.restore(deepcopy(self.navigation_start))
        first = self.path[0]
        start = self.data_manager.validate_logical_address(first["logical_before"])
        overflow_start = int(first["logical_counter_universe_before"])
        if storage_coordinate is not None and self.data_manager.coordinate_string(storage_coordinate) != start[0]:
            raise ValueError("Logical Sticky Note must be anchored at its starting coordinate.")
        history = seed_path_universe(start[0], self.note_id, counter_universe=overflow_start)
        written = []
        functions = []
        plan = []  # Terminal-private, ordered, self-contained replay input.
        lookup = {}
        previous_selector = None
        initial_layers = deepcopy(self.navigation_start["layers"])
        initial_slot = None
        if initial_layers:
            top = initial_layers[-1]
            initial_slot = (expression_for_definition(top["definition"]),
                            -1 if top["leg"] == "toward" else 1)
        try:
            for index, event in enumerate(self.path):
                before = self.data_manager.validate_logical_address(
                    event["logical_before"], direction=event["logical_direction_before"])
                after = self.data_manager.validate_logical_address(
                    event["logical_after"], direction=event["logical_direction_after"])
                before_u = int(event["logical_counter_universe_before"])
                after_u = int(event["logical_counter_universe_after"])
                self._check_cursor(navigator, before, before_u,
                                   event["logical_direction_before"])
                nav = event.get("navigation", {"op": "none"})
                op = nav.get("op", "none")
                before_snapshot = navigator.snapshot()
                before_layers = deepcopy(before_snapshot["layers"])
                simulation = {"navigation": nav,
                              "host_before": event.get("coordinate_before"),
                              "host_universe_before": event.get("universe_before", 0),
                              "host_after": event.get("host_after"),
                              "host_universe_after": event.get("host_universe_after", 0),
                              "follow_update": event.get("follow_update", False)}
                self._advance_recorded_navigation(navigator, simulation)
                self._check_cursor(navigator, after, after_u,
                                   event["logical_direction_after"])
                after_snapshot = navigator.snapshot()
                after_layers = deepcopy(after_snapshot["layers"])
                if op in ("open", "push", "child"):
                    # Newly established pole, k=0 except historical child().
                    active = after_layers[-1] if after_layers else None
                    direction = 1
                elif before_layers:
                    # Even when the final return step POPS its layer, that
                    # command still references the function it just traversed.
                    # Reversing an empty child spends its tick on its parent.
                    active = (before_layers[-2] if op == "turn" and
                              before_layers[-1]["k"] == 0 and
                              len(before_layers) > 1 else before_layers[-1])
                    direction = -1 if (op in ("turn", "toward") or op == "auto_back" or
                                       (op == "auto" and active["leg"] == "toward")) else 1
                else:
                    active = None
                    delta = (address_to_integer(after[0], after_u) -
                             address_to_integer(before[0], before_u))
                    direction = -1 if delta < 0 else 1
                expression = (expression_for_definition(active["definition"])
                              if active is not None else "k")
                signature = (expression, direction)
                if signature not in lookup:
                    selector = len(functions)
                    lookup[signature] = selector
                    function = {"f": expression, "direction": direction}
                    # Common case: recording starts partway through ONE pole.
                    # The real pole is start - [g(k)-g(0)].
                    if (index == 0 and len(initial_layers) == 1
                            and signature == initial_slot and initial_layers[0]["k"]):
                        function["k"] = initial_layers[0]["k"]
                    functions.append(function)
                selector = lookup[signature]
                distance = (address_to_integer(after[0], after_u) -
                            address_to_integer(before[0], before_u))
                if active is not None:
                    step = (1 if before[1] != after[1] and op not in
                            ("open", "push", "pause", "resume", "hold") else 0)
                else:
                    step = (0 if op in ("open", "push", "pause", "resume", "hold", "sync")
                            else abs(distance))
                # Unlike public coordinate blocks, the private terminal note
                # owns the ordered command plan. Function selection, source
                # movement, and control transitions are explicit so the future
                # ReplayEngine never has to guess an event order or look up a
                # pi_ activation ID at the pole. The plan is compact: no
                # duplicated per-step virtual coordinate is necessary.
                item = {"command": str(event.get("value", "")),
                        "source": event.get("source", "base"), "op": op}
                if event.get("success") is False:
                    item["failed"] = True
                host_before = event.get("coordinate_before")
                host_after = event.get("coordinate_after")
                if host_before is not None and host_after is not None:
                    source_delta = (address_to_integer(
                        host_after, int(event.get("universe_after", 0))) -
                        address_to_integer(host_before, int(event.get("universe_before", 0))))
                    if source_delta:
                        item["delta"] = source_delta
                if op in ("open", "push", "child"):
                    item["f"] = expression_for_definition(after_layers[-1]["definition"])
                    if op == "open" and nav.get("anchor") is not None:
                        item["anchor"] = nav["anchor"]
                        if nav.get("counter_universe"):
                            item["anchor_universes"] = nav["counter_universe"]
                elif op == "sync":
                    item["target"] = after[0]
                    if after_u:
                        item["target_universes"] = after_u
                plan.append(item)
                block = self.data_manager.save_command_block(
                    before[0], event.get("value", ""), f"{history:032x}",
                    counter_universe=before_u,
                    function=selector if selector != previous_selector else None,
                    step=step, failed=event.get("success") is False,
                    source=event.get("source", "base"))
                written.append((before[0], block["universe"], before_u))
                previous_selector = selector
                history = evolve_path_universe(
                    history, self._portable_signature(before_snapshot),
                    self._portable_signature(after_snapshot),
                    f"event:{index}:{event.get('value', '')}:{op}",
                    counter_universe_before=before_u,
                    counter_universe_after=after_u)
            last = self.path[-1]
            end = self.data_manager.validate_logical_address(last["logical_after"])
            note = {"id": self.note_id, "title": str(title),
                    "start": start[0], "end": end[0],
                    "start_state": deepcopy(self.navigation_context_start or
                        NavigatorEngine.portable_state(self.navigation_start)),
                    # Preserved catalog for the already-stored command-block
                    # function selectors. No note title/history/plan is public.
                    "functions": functions,
                    "blocks": len(self.path),
                    "plan": plan}
            if (note["start_state"]["coordinate"] != start[0] or
                    note["start_state"]["universes"] != overflow_start):
                raise ValueError("Recorded start differs from the Sticky Note navigation origin.")
            if overflow_start:
                note["start_universe"] = overflow_start
            end_u = int(last["logical_counter_universe_after"])
            if end_u:
                note["end_universe"] = end_u
            collection = self.data_manager.load_terminal_data(self.terminal_id, "sticky_notes")
            notes = collection.setdefault("notes", [])
            if not isinstance(notes, list):
                raise ValueError("Terminal Sticky Note collection is malformed.")
            if any(isinstance(n, dict) and n.get("id") == self.note_id for n in notes):
                raise ValueError("Sticky Note ID collision.")
            notes.append(note)
            # Version 3 notes have self-contained replay plans. Existing v2
            # notes remain present/readable and are never silently migrated.
            collection["version"] = 3
            collection.pop("terminal_id", None)
            self.data_manager.save_terminal_data(self.terminal_id, "sticky_notes", collection)
            return deepcopy(note)
        except Exception:
            for coordinate, universe, counter_universe in reversed(written):
                self.data_manager.delete_command_block(
                    coordinate, universe, counter_universe=counter_universe)
            raise

    def _save_logical_reference(self, title, storage_coordinate=None):
        """Commit event-local records; note at entry carries one lookup seed.

        No whole-path list, recording_id, next locator, or function formula is
        stored in command records. Failures roll back all coordinate events.
        """
        if self.navigation_start is None or self.route_seed is None:
            raise ValueError("Missing Navigator starting state for logical recording.")
        navigator = self._hydrate_navigation(self._portable_navigation(self.navigation_start))
        writes = []
        note_id = uuid.uuid4().hex[:12]
        pointer_coordinate = None
        functions = []
        function_lookup = {}
        previous_function_index = None
        try:
            for index, event in enumerate(self.path):
                addr = self.data_manager.validate_logical_address(event["logical_before"],
                                            direction=event["logical_direction_before"])
                overflow = int(event["logical_counter_universe_before"])
                direction = event["logical_direction_before"]
                self._check_cursor(navigator, addr, overflow, direction)
                event_id = self._logical_event_id(
                    self.route_seed, index, addr, overflow, direction)
                navigation = event.get("navigation", {"op": "none"})
                # A function slot selects a projection rule and its direction.
                # k (imaginary progression) is still owned by Navigator.
                active = navigator.snapshot()["layers"]
                spec = deepcopy(active[-1]["definition"]) if active else {
                    "name": "linear_offset", "version": 1, "params": {"slope": 1}}
                signature = json.dumps([spec, direction], sort_keys=True, separators=(",", ":"))
                if signature not in function_lookup:
                    function_lookup[signature] = len(functions)
                    functions.append({"definition": spec, "direction": direction})
                current_function_index = function_lookup[signature]
                # Store the selector only on the first command or when it changes.
                selector = (current_function_index if current_function_index != previous_function_index
                            else None)
                stored = self.data_manager.save_logical_command(
                    addr, event.get("value", ""), counter_universe=overflow,
                    direction=direction, event_id=event_id,
                    function_index=selector, source=event.get("source", "oais"), navigation=navigation,
                    host_after=(event.get("host_after") if (
                        event.get("follow_update", False) or navigation.get("op") == "sync")
                        else None),
                    host_universe_after=event.get("host_universe_after"),
                    follow_update=event.get("follow_update", False),
                    success=event.get("success", True),
                    event_type=event.get("type", "command"),
                    meta_transition=({"from": event["from"], "to": event["to"]}
                        if event.get("type") == "transition" else None))
                writes.append((addr[0], stored["id"]))
                previous_function_index = current_function_index
                self._advance_recorded_navigation(navigator, stored)
                self._check_cursor(navigator, event["logical_after"],
                                   event["logical_counter_universe_after"],
                                   event["logical_direction_after"])
            first = self.path[0]
            last = self.path[-1]
            start = self.data_manager.validate_logical_address(first["logical_before"])
            after = self.data_manager.validate_logical_address(last["logical_after"])
            pointer_coordinate = self.data_manager.coordinate_string(
                storage_coordinate or start[0])
            if pointer_coordinate != start[0]:
                raise ValueError("Logical Sticky Note must be anchored at its starting coordinate.")
            note = {
                "id": note_id, "type": self.OBJECT_TYPE,
                "schema_version": 4, "storage": "logical", "title": str(title),
                "start": start, "start_counter_universe": first["logical_counter_universe_before"],
                "start_direction": first["logical_direction_before"],
                "initial_state": self._portable_navigation(self.navigation_start),
                "route_seed": self.route_seed,
                "functions": functions,
                "event_count": len(self.path), "after": after,
                "after_counter_universe": last["logical_counter_universe_after"],
                "after_direction": last["logical_direction_after"],
                "scope": self.session_metadata.get("scope", "all"),
            }
            # The path definition belongs to the terminal, not coordinate space.
            collection = self.data_manager.load_terminal_data(self.terminal_id, "sticky_notes")
            notes = collection.setdefault("notes", [])
            if not isinstance(notes, list):
                raise ValueError("Terminal Sticky Note collection is malformed.")
            if any(isinstance(n, dict) and n.get("id") == note_id for n in notes):
                raise ValueError("Sticky Note ID collision.")
            notes.append(note)
            collection["version"] = 1
            collection["terminal_id"] = self.terminal_id
            self.data_manager.save_terminal_data(self.terminal_id, "sticky_notes", collection)
        except Exception:
            for coord, event_id in reversed(writes):
                self.data_manager.delete_object(coord, "logical_command", event_id)
            raise
        return deepcopy(note)

    def _load_logical_path(self, note):
        """Follow a route by computing each address from the starting state.

        The note holds an entry seed and start state, not a list of coordinates.
        At each step a deterministic event key identifies one object at the
        calculated real coordinate; its operation advances the pure Navigator.
        """
        count = note.get("event_count")
        if isinstance(count, bool) or not isinstance(count, int) or not 0 < count <= 100000:
            raise ValueError("Invalid logical Sticky Note event count.")
        seed = note.get("route_seed")
        if not isinstance(seed, str) or not seed:
            raise ValueError("Missing logical path starting seed.")
        navigator = self._hydrate_navigation(note["initial_state"])
        self._check_cursor(navigator, note["start"],
                           note["start_counter_universe"], note["start_direction"])
        events = []
        for index in range(count):
            v = navigator.virtual
            address = v.logical_address()
            before_counter = v.universe
            before_direction = v.direction
            event_id = self._logical_event_id(
                seed, index, address, before_counter, before_direction)
            matches = [obj for obj in self.data_manager.load_logical_commands(
                address[0], address=address, counter_universe=before_counter,
                direction=before_direction) if obj.get("id") == event_id]
            if len(matches) != 1:
                raise ValueError("Missing or ambiguous logical command at calculated step " + str(index))
            record = matches[0]
            self._advance_recorded_navigation(navigator, record)
            after_address = navigator.virtual.logical_address()
            event = {
                "type": record.get("event_type", "command"),
                "value": record["command"], "source": record.get("source", "oais"),
                "success": record.get("success", True), "sequence": index,
                "coordinate_before": address[0], "coordinate_after": after_address[0],
                "universe_before": before_counter,
                "universe_after": navigator.virtual.universe,
                "logical_before": address, "logical_after": after_address,
                "logical_counter_universe_before": before_counter,
                "logical_counter_universe_after": navigator.virtual.universe,
                "logical_direction_before": before_direction,
                "logical_direction_after": navigator.virtual.direction,
                "navigation": deepcopy(record.get("navigation", {"op": "none"})),
            }
            if record.get("meta_transition") is not None:
                event.update(deepcopy(record["meta_transition"]))
            events.append(event)
        self._check_cursor(navigator, note["after"],
                           note["after_counter_universe"], note["after_direction"])
        return events

    def load_path(self, identifier):
        """Reconstruct v4 navigator paths; retain all legacy readers unchanged."""
        note = self.get_note(identifier)
        if isinstance(note.get("plan"), list):
            # v11+ notes own an ordered command plan in terminal_data. The
            # shared coordinate blocks are intentionally NOT read to replay it.
            plan = note["plan"]
            count = note.get("blocks")
            if isinstance(count, bool) or not isinstance(count, int) or count != len(plan):
                raise ValueError("Sticky Note plan length does not match its block count.")
            if not isinstance(note.get("start_state"), dict):
                raise ValueError("Sticky Note lacks its mathematical starting state.")
            if note["start_state"].get("coordinate") != note.get("start"):
                raise ValueError("Sticky Note starting coordinate is inconsistent.")
            events = []
            for index, item in enumerate(plan):
                if (not isinstance(item, dict) or not isinstance(item.get("command"), str)
                        or not isinstance(item.get("source"), str)
                        or not isinstance(item.get("op"), str)):
                    raise ValueError(f"Invalid Sticky Note plan event {index + 1}.")
                events.append({"type": "command", "value": item["command"],
                               "source": item["source"],
                               "success": not bool(item.get("failed", False)),
                               "sequence": index, "from_plan": True,
                               "navigation": {"op": item["op"]}})
            return note, events
        if (note.get("schema_version") == 5 or
                (isinstance(note.get("start"), str) and
                 "functions" in note and "blocks" in note)):
            raise NotImplementedError("Older compact notes without a private plan require legacy reconstruction.")
        if note.get("schema_version") == 4 and note.get("storage") == "logical":
            return note, self._load_logical_path(note)
        if "start" in note and "end" in note:
            events = []
            locator = note["start"]
            seen = set()
            end_key = (note["end"][0], note["end"][1])
            # Bound traversal to detect broken/cyclic chains.
            while locator is not None and len(events) < 100000:
                key = (locator[0], locator[1])
                if key in seen:
                    raise ValueError("Cyclic saved path")
                seen.add(key)
                block = self.data_manager.read_command(locator)
                next_loc = block[2]
                after_coord = next_loc[0] if next_loc else note["after"][0]
                after_universe = (self.data_manager.read_command(next_loc)[1]
                                  if next_loc else note["after"][1])
                source = block[3] if len(block) > 3 else "base"
                event = {"type": "transition" if source == "meta" else "command",
                         "value": block[0], "source": source,
                         "coordinate_before": locator[0],
                         "coordinate_after": after_coord,
                         "universe_before": block[1],
                         "universe_after": after_universe,
                         "sequence": len(events)}
                if source == "meta":
                    event["from"] = "oais"
                    event["to"] = "base" if block[0] == "return" else "oais"
                events.append(event)
                if key == end_key:
                    if next_loc is not None:
                        raise ValueError("End event unexpectedly has a successor")
                    return note, events
                locator = next_loc
            raise ValueError("Saved path is incomplete or too long")

        if "last_event" in note:
            locator = note["last_event"]
            reverse_events = []
            seen = set()
            maximum = int(note.get("event_count", 0))
            if maximum < 1:
                raise ValueError("Saved Sticky Note has an invalid event count")
            for _ in range(maximum):
                if not isinstance(locator, dict):
                    raise ValueError("Saved Sticky Note has a broken event link")
                coordinate = self.data_manager.coordinate_string(locator["coordinate"])
                identity = (coordinate, str(locator["id"]))
                if identity in seen:
                    raise ValueError("Saved Sticky Note contains a cyclic event link")
                seen.add(identity)
                stored = self.data_manager.get_objects_at_coordinate(
                    coordinate, "command_event"
                )
                match = next((item for item in stored
                              if str(item.get("id")) == identity[1]), None)
                if match is None:
                    raise ValueError(f"Missing Sticky Note event {identity[1]} at {coordinate}")
                reverse_events.append(self._event_from_block(match))
                locator = match.get("previous")
                if locator is None:
                    break
            if len(reverse_events) != maximum or locator is not None:
                raise ValueError("Saved Sticky Note path is incomplete")
            reverse_events.reverse()
            for index, event in enumerate(reverse_events):
                event["sequence"] = index
            return note, reverse_events

        if "event_refs" in note:  # previous Meta Terminal implementation
            events = []
            for ref in note["event_refs"]:
                stored = self.data_manager.get_objects_at_coordinate(
                    ref["coordinate"], "command_event"
                )
                block = next((item for item in stored
                              if item.get("id") == ref["event_id"]), None)
                if block is None:
                    raise ValueError(f"Missing legacy event {ref['event_id']}")
                events.append(deepcopy(block.get("event", block)))
            return note, events

        if "events" in note:  # original embedded-path format
            return note, deepcopy(note["events"])
        raise ValueError("Saved Sticky Note has no readable event chain")

    @staticmethod
    def _event_from_block(block):
        """Adapt a minimal stored block for existing path display commands."""
        event = {
            "type": "transition" if "transition" in block else "command",
            "value": block.get("command", ""),
            "source": block.get("source", "oais"),
            "coordinate_before": block["coordinate"],
            "coordinate_after": block.get("after", block["coordinate"]),
            "universe_before": block.get("universe", 0),
            "universe_after": block.get("after_universe", block.get("universe", 0)),
            "success": not block.get("failed", False),
        }
        if "transition" in block:
            event.update(block["transition"])
        return event

    # ==========================================================
    # SAVED NOTES
    # ==========================================================

    def list_notes(self):
        collection = self.data_manager.load_terminal_data(self.terminal_id, "sticky_notes")
        notes = collection.get("notes", [])
        if not isinstance(notes, list):
            raise ValueError("Terminal Sticky Note collection is malformed.")
        # Legacy notes remain discoverable without rewriting their coordinate data.
        return (deepcopy(notes) + self.data_manager.list_sticky_pointers()
                + self.data_manager.list_objects(self.OBJECT_TYPE))

    def get_note(self, identifier):
        identifier = str(identifier).strip().lower()
        collection = self.data_manager.load_terminal_data(self.terminal_id, "sticky_notes")
        notes = collection.get("notes", [])
        if not isinstance(notes, list):
            raise ValueError("Terminal Sticky Note collection is malformed.")
        for note in notes:
            if isinstance(note, dict) and str(note.get("id", "")).lower() == identifier:
                return deepcopy(note)
        matches = [n for n in notes if isinstance(n, dict)
                   and str(n.get("title", "")).lower() == identifier]
        if len(matches) == 1:
            return deepcopy(matches[0])
        if len(matches) > 1:
            raise ValueError("Multiple Sticky Notes have that title; use an ID.")
        try:
            return self.data_manager.find_sticky_pointer(identifier)
        except KeyError:
            return self.data_manager.find_object(self.OBJECT_TYPE, identifier)

    def read(
        self,
        identifier,
    ):
        """
        Alias with clearer terminal-facing wording.
        """

        return self.get_note(
            identifier
        )


    # ==========================================================
    # STATE
    # ==========================================================

    def current_coordinate(self):
        """
        Return OAIS's current coordinate.

        This is OAIS state, not DEEP-specific state.
        """

        if self.counter is None:

            return (
                "0 0 0 0 0 0"
            )

        return (
            self.counter.get_counters()
        )


    def current_state(self):
        """
        Obtain optional host state.

        Sticky Note does not know how the state is produced.

        A connection may provide:

            connection.get_state

        or this may remain None.
        """

        if self.state_provider is None:

            return None

        try:

            return deepcopy(
                self.state_provider()
            )

        except Exception:

            return None


    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):

        with self._lock:

            return {
                "active": self.active,
                "paused": self.paused,
                "event_count": len(
                    self.path
                ),
                "start_coordinate": (
                    self.start_coordinate
                ),
                "current_coordinate": (
                    self.current_coordinate()
                ),
                "started_at": (
                    self.started_at
                ),
            }


    # ==========================================================
    # EVENT NORMALIZATION
    # ==========================================================

    def _normalize_event(self, event):
        """Cache only what can locate and replay the command's path.

        Deliberately discard host output, timestamps, and arbitrary state
        snapshots: those can be large and are not needed for this recorder.
        """
        if not isinstance(event, dict):
            event = {"type": "command", "value": str(event)}

        coordinate = self.current_coordinate()
        universe = self.counter.universes if self.counter is not None else 0
        before = event.get("coordinate_before", event.get("coordinate", coordinate))
        after = event.get("coordinate_after", before)
        before_universe = event.get("universe_before", universe)
        normalized = {
            "type": event.get("type", "command"),
            "value": str(event.get("value", "")),
            "source": event.get("source", "oais"),
            "coordinate_before": before,
            "coordinate_after": after,
            "universe_before": before_universe,
            "universe_after": event.get("universe_after", before_universe),
        }
        if event.get("success") is False:
            normalized["success"] = False
        if normalized["type"] == "transition":
            normalized["from"] = event.get("from")
            normalized["to"] = event.get("to")
        # Retain only navigator routing data, not arbitrary host payloads.
        for key in ("logical_before", "logical_after", "logical_counter_universe_before",
                    "logical_counter_universe_after", "logical_direction_before",
                    "logical_direction_after", "navigation", "host_after",
                    "host_universe_after", "follow_update"):
            if key in event:
                normalized[key] = deepcopy(event[key])
        return normalized

    # ==========================================================
    # HELPERS
    # ==========================================================

    @staticmethod
    def _timestamp():

        return (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )