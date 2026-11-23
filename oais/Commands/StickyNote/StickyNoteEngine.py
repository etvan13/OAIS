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
    from ...utils.virtual_counter import VirtualCounter
    from ..Navigator.NavigatorEngine import NavigatorEngine
except ImportError:  # python main.py from the project root
    from utils.counter import Counter
    from utils.data_manager import DataManager
    from utils.virtual_counter import VirtualCounter
    from Commands.Navigator.NavigatorEngine import NavigatorEngine


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
        self.navigation_start = None
        self.route_seed = None

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
            self.route_seed = None
            if self.session_metadata.get("storage") == "logical":
                if self.navigation_provider is None:
                    raise ValueError("Logical Sticky Note requires a Navigator state provider.")
                self.navigation_start = deepcopy(self.navigation_provider())
                self.route_seed = uuid.uuid4().hex

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
        self.route_seed = None


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
                return self._save_logical_reference(title, storage_coordinate)
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
            return
        if op == "auto":
            if navigator.advance_automatic() is None:
                raise ValueError("Recorded automatic navigation has no active function.")
        elif op in ("open", "child"):
            ref = nav["ref"]
            state = navigator.virtual.snapshot()
            definition = self.data_manager.load_pole_function(
                state["coordinate"], ref,
                counter_universe=state["counter_universe"])
            spec = definition["definition"]
            if op == "open":
                navigator.open_pole(spec["name"], spec.get("params"),
                                    seed=definition["entry_seed"], activation_id=ref)
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
            if host_after is None:
                raise ValueError("Synchronization event has no host target.")
            navigator.reset_to_linear(
                host_after, block.get("host_universe_after", 0))
        else:
            raise ValueError("Unsupported recorded navigation operation: " + str(op))

    @staticmethod
    def _check_cursor(navigator, address, counter_universe, direction):
        v = navigator.virtual
        if (v.logical_address() != address or v.universe != counter_universe
                or v.direction != direction):
            raise ValueError("Saved Sticky Note traversal diverged from its logical address.")

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
                stored = self.data_manager.save_logical_command(
                    addr, event.get("value", ""), counter_universe=overflow,
                    direction=direction, event_id=event_id,
                    source=event.get("source", "oais"), navigation=navigation,
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
            note = self.data_manager.save_object(
                pointer_coordinate, self.OBJECT_TYPE, note_id, {
                    "schema_version": 4, "storage": "logical", "title": str(title),
                    "start": start, "start_counter_universe": first["logical_counter_universe_before"],
                    "start_direction": first["logical_direction_before"],
                    "initial_state": self._portable_navigation(self.navigation_start),
                    "route_seed": self.route_seed,
                    "event_count": len(self.path), "after": after,
                    "after_counter_universe": last["logical_counter_universe_after"],
                    "after_direction": last["logical_direction_after"],
                    "scope": self.session_metadata.get("scope", "all"),
                })
        except Exception:
            if pointer_coordinate is not None:
                self.data_manager.delete_object(pointer_coordinate, self.OBJECT_TYPE, note_id)
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
        return (self.data_manager.list_sticky_pointers()
                + self.data_manager.list_objects(self.OBJECT_TYPE))

    def get_note(self, identifier):
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