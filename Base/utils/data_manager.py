# Base/utils/data_manager.py
# Formatting-only copy: original behavior and signatures preserved.

import json
import os
from copy import deepcopy
import uuid
from pathlib import Path



BASE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_ROOT / 'Base_Data'
COORDINATE_DIR = DATA_DIR / 'coordinate_data'
SHOW_LIST_PATH = DATA_DIR / 'show_list.json'


class DataManager:
    """
    OAIS-owned coordinate data manager.

    OAIS uses the same base-60 coordinate geometry as DEEP.

    Coordinate:

        p0 p1 p2 p3 p4 p5

    p0 is least significant.
    p5 is most significant.

    A coordinate such as:

        21 8 4 1 0 0

    maps to:

        OAIS/Data/coordinate_data/
            0/
              0/
                1/
                  4/
                    8.json

    The exact coordinate remains a key inside that file:

        {
            "21 8 4 1 0 0": {
                ...
            }
        }

    This manager owns OAIS data only.

    DEEP's DataManager and OAIS's DataManager may use
    the same coordinate geometry, but they maintain
    separate data spaces.
    """

    # --- Initialization ---
    def __init__(self, base_dir=None):
        if base_dir is None:
            self.base_dir = DATA_DIR
        else:
            self.base_dir = Path(base_dir)
        self.coordinate_dir = self.base_dir / 'coordinate_data'
        self.show_list_path = self.base_dir / 'show_list.json'
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.coordinate_dir.mkdir(parents=True, exist_ok=True)
        # No automatic show_list.json: coordinate_data is the storage index.

    # --- Terminal-scoped, coordinate-independent JSON collections ---
    @staticmethod
    def _safe_storage_name(value, label):
        import re
        if (not isinstance(value, str) or
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value)):
            raise ValueError(f"{label} must contain only letters, digits, _ or - (max 64).")
        return value

    def terminal_data_location(self, terminal_id, collection, *, create=False):
        """Path for a terminal-owned collection; never inside coordinate_data."""
        terminal_id = self._safe_storage_name(terminal_id, "Terminal ID")
        collection = self._safe_storage_name(collection, "Collection")
        directory = self.base_dir / 'terminal_data' / terminal_id
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        return directory / f'{collection}.json'

    def load_terminal_data(self, terminal_id, collection):
        """Return a detached collection dictionary, or {} when absent."""
        path = self.terminal_data_location(terminal_id, collection)
        data = self._load_json(path)
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError("Terminal collection must be a JSON object.")
        return deepcopy(data)

    def save_terminal_data(self, terminal_id, collection, data):
        """Replace one terminal collection with an atomic JSON write."""
        if not isinstance(data, dict):
            raise ValueError("Terminal collection must be a dictionary.")
        json.dumps(data, allow_nan=False)
        path = self.terminal_data_location(terminal_id, collection, create=True)
        self._write_json(path, deepcopy(data), sort_coordinates=False)
        return path

    # --- Coordinate validation ---
    @staticmethod
    def parse_coordinate(coordinate):
        """
        Convert:

            "21 8 4 1 0 0"

        into:

            [21, 8, 4, 1, 0, 0]

        Every value must be 0-59.
        """
        if isinstance(coordinate, (list, tuple)):
            parts = list(coordinate)
        elif isinstance(coordinate, str):
            parts = coordinate.strip().split()
        else:
            raise ValueError('Coordinate must be a string, list, or tuple.')
        if len(parts) != 6:
            raise ValueError(f'Expected 6 coordinate values, got {len(parts)}.')
        try:
            values = [int(value) for value in parts]
        except (ValueError, TypeError):
            raise ValueError('Coordinate values must be integers.')
        if not all((0 <= value < 60 for value in values)):
            raise ValueError('Coordinate values must be between 0 and 59.')
        return values

    @staticmethod
    def coordinate_string(coordinate):
        """
        Normalize a coordinate into:

            "21 8 4 1 0 0"
        """
        values = DataManager.parse_coordinate(coordinate)
        return ' '.join((str(value) for value in values))

    # --- Coordinate file location ---
    def coordinate_location(self, coordinate, create=False):
        """
        Resolve an OAIS coordinate to its storage file.

        Coordinate:

            p0 p1 p2 p3 p4 p5

        becomes:

            p5/
              p4/
                p3/
                  p2/
                    p1.json

        p0 remains represented by the full coordinate
        key inside the JSON file.

        Returns:

            directory,
            json_path
        """
        p0, p1, p2, p3, p4, p5 = self.parse_coordinate(coordinate)
        directory = self.coordinate_dir / str(p5) / str(p4) / str(p3) / str(p2)
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        json_path = directory / f'{p1}.json'
        return (directory, json_path)

    # --- Coordinate node ---
    def get_coordinate_node(self, coordinate):
        """
        Return the complete OAIS node stored at a coordinate.

        Returns None if the coordinate has no stored data.
        """
        coordinate = self.coordinate_string(coordinate)
        _, json_path = self.coordinate_location(coordinate)
        if not json_path.exists():
            return None
        json_data = self._load_json(json_path)
        if json_data is None:
            return None
        node = json_data.get(coordinate)
        if not isinstance(node, dict):
            return None
        return node

    def coordinate_exists(self, coordinate):
        return self.get_coordinate_node(coordinate) is not None

    # --- Generic object storage ---
    def save_object(self, coordinate, object_type, object_id, data):
        """
        Store an OAIS object at a coordinate.

        Example:

            save_object(
                coordinate="21 8 4 1 0 0",
                object_type="sticky_note",
                object_id="abc123",
                data={
                    "title": "Path1",
                    "path": [...]
                }
            )

        Result:

            {
                "21 8 4 1 0 0": {

                    "objects": {

                        "sticky_note": [
                            {...}
                        ]
                    }
                }
            }
        """
        coordinate = self.coordinate_string(coordinate)
        object_type = str(object_type).strip().lower()
        object_id = str(object_id).strip()
        if not object_type:
            raise ValueError('OAIS object type cannot be empty.')
        if not object_id:
            raise ValueError('OAIS object ID cannot be empty.')
        _, json_path = self.coordinate_location(coordinate, create=True)
        json_data = self._load_or_create_json(json_path)
        node = json_data.setdefault(coordinate, {})
        if not isinstance(node, dict):
            node = {}
            json_data[coordinate] = node
        objects = node.setdefault('objects', {})
        if not isinstance(objects, dict):
            objects = {}
            node['objects'] = objects
        bucket = objects.setdefault(object_type, [])
        if not isinstance(bucket, list):
            bucket = []
            objects[object_type] = bucket
        record = dict(data)
        record['id'] = object_id
        record['type'] = object_type
        record['coordinate'] = coordinate
        replaced = False
        for index, existing in enumerate(bucket):
            if isinstance(existing, dict) and str(existing.get('id', '')) == object_id:
                bucket[index] = record
                replaced = True
                break
        if not replaced:
            bucket.append(record)
        self._write_json(json_path, json_data)
        self.add_to_show_list(coordinate)
        return record

    # --- Object reading ---
    def get_objects_at_coordinate(self, coordinate, object_type=None):
        """
        Return OAIS objects stored at one coordinate.
        """
        node = self.get_coordinate_node(coordinate)
        if node is None:
            return []
        objects = node.get('objects', {})
        if not isinstance(objects, dict):
            return []
        if object_type is not None:
            object_type = str(object_type).strip().lower()
            bucket = objects.get(object_type, [])
            if not isinstance(bucket, list):
                return []
            return list(bucket)
        results = []
        for bucket in objects.values():
            if isinstance(bucket, list):
                results.extend(bucket)
        return results

    # --- Global object list ---
    def list_objects(self, object_type=None):
        """
        Search all OAIS coordinate files for objects.

        This is intentionally simple for now.

        Later OAIS can build indexes/references so this
        does not need to walk every coordinate file.
        """
        results = []
        if not self.coordinate_dir.exists():
            return results
        for json_path in self.coordinate_dir.rglob('*.json'):
            json_data = self._load_json(json_path)
            if not isinstance(json_data, dict):
                continue
            for coordinate, node in json_data.items():
                if not isinstance(node, dict):
                    continue
                objects = node.get('objects', {})
                if not isinstance(objects, dict):
                    continue
                if object_type is None:
                    buckets = objects.values()
                else:
                    normalized_type = str(object_type).strip().lower()
                    buckets = [objects.get(normalized_type, [])]
                for bucket in buckets:
                    if not isinstance(bucket, list):
                        continue
                    for obj in bucket:
                        if isinstance(obj, dict):
                            results.append(dict(obj))
        return results

    # --- Find object ---
    def find_object(self, object_type, identifier):
        """
        Find an OAIS object by:

            1. exact ID
            2. exact title

        Title matching is case-insensitive.
        """
        identifier = str(identifier).strip()
        if not identifier:
            raise ValueError('Object identifier cannot be empty.')
        objects = self.list_objects(object_type)
        identifier_lower = identifier.lower()
        for obj in objects:
            if str(obj.get('id', '')).lower() == identifier_lower:
                return obj
        title_matches = []
        for obj in objects:
            title = str(obj.get('title', ''))
            if title.lower() == identifier_lower:
                title_matches.append(obj)
        if len(title_matches) == 1:
            return title_matches[0]
        if len(title_matches) > 1:
            raise ValueError(f"Multiple OAIS objects have the title '{identifier}'. Use the object ID.")
        raise KeyError(f"No {object_type} found for '{identifier}'.")

    # --- Delete object ---
    def delete_object(self, coordinate, object_type, object_id):
        """
        Delete one OAIS object from one coordinate.
        """
        coordinate = self.coordinate_string(coordinate)
        object_type = str(object_type).strip().lower()
        object_id = str(object_id).strip()
        _, json_path = self.coordinate_location(coordinate)
        if not json_path.exists():
            return False
        json_data = self._load_json(json_path)
        if not isinstance(json_data, dict):
            return False
        node = json_data.get(coordinate)
        if not isinstance(node, dict):
            return False
        objects = node.get('objects')
        if not isinstance(objects, dict):
            return False
        bucket = objects.get(object_type)
        if not isinstance(bucket, list):
            return False
        original_length = len(bucket)
        bucket[:] = [obj for obj in bucket if not (isinstance(obj, dict) and str(obj.get('id', '')) == object_id)]
        if len(bucket) == original_length:
            return False
        if not bucket:
            objects.pop(object_type, None)
        if not objects:
            node.pop('objects', None)
        if not node:
            json_data.pop(coordinate, None)
        if json_data:
            self._write_json(json_path, json_data)
        else:
            try:
                json_path.unlink()
            except OSError:
                pass
        self._cleanup_empty_directories(json_path.parent)
        if not self.coordinate_exists(coordinate):
            self.remove_from_show_list(coordinate)
        return True

    # --- Pole-local function definitions (version 3) ---
    def save_pole_function(self, pole_coordinate, definition, *,
                           counter_universe=0, function_ref=None, entry_seed=None):
        """Register a traversal function *once* at the activation pole.

        Later logical events carry only the opaque `pi_...` reference in the
        third component of [real, imaginary, function_ref, path_universe].
        They do not repeat the movement rule or the pole's real coordinate.
        This is a storage-layout choice, not access control or encryption.
        """
        pole = self.coordinate_string(pole_coordinate)
        if isinstance(counter_universe, bool) or not isinstance(counter_universe, int):
            raise ValueError("Counter universe must be an integer.")
        if not isinstance(definition, dict):
            raise ValueError("Pole function definition must be a dictionary.")
        name = definition.get("name")
        version = definition.get("version", 1)
        params = definition.get("params", {})
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Pole function requires a named registry function.")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("Pole function version must be a positive integer.")
        if not isinstance(params, dict):
            raise ValueError("Pole function parameters must be a dictionary.")
        spec = {"name": name.strip(), "version": version, "params": deepcopy(params)}
        try:
            json.dumps(spec, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Pole function definition must be JSON-serializable.") from exc
        ref = function_ref if function_ref is not None else "pi_" + uuid.uuid4().hex[:16]
        if (not isinstance(ref, str) or not ref.startswith("pi_")
                or len(ref) != 19 or any(c not in "0123456789abcdef" for c in ref[3:])):
            raise ValueError("Function reference must be pi_ followed by 16 lowercase hex digits.")
        if any(str(obj.get("id")) == ref for obj in
               self.get_objects_at_coordinate(pole, "pole_function")):
            raise ValueError("Pole function reference is already registered at this coordinate.")
        record = {"schema_version": 3, "counter_universe": counter_universe,
                  "definition": spec}
        # Only a root pole may carry an entry seed; ordinary command events
        # and child poles do not duplicate it. Future Sticky Notes can refer
        # to this pole activation as their traversal start.
        if entry_seed is not None:
            if not isinstance(entry_seed, str) or not entry_seed:
                raise ValueError("Entry seed must be a nonempty string.")
            record["entry_seed"] = entry_seed
        return self.save_object(pole, "pole_function", ref, record)

    def load_pole_function(self, pole_coordinate, function_ref, *, counter_universe=0):
        """Resolve a function only when its original pole coordinate is known."""
        pole = self.coordinate_string(pole_coordinate)
        found = [obj for obj in self.get_objects_at_coordinate(pole, "pole_function")
                 if obj.get("id") == function_ref
                 and obj.get("counter_universe") == counter_universe]
        if not found:
            raise KeyError("No pole function with that reference at this pole.")
        if len(found) != 1:
            raise ValueError("Ambiguous pole function reference.")
        return deepcopy(found[0])

    # --- Logical command storage (version 3) ---
    @staticmethod
    def validate_logical_address(address, direction="linear"):
        """Normalize [real, imaginary, function, path_universe].

        Validation lives here so we do not need a logical_address.py module.
        This does not compute imaginary motion or evolve a path universe.
        """
        if not isinstance(address, (list, tuple)) or len(address) != 4:
            raise ValueError("Logical address must be [real, imaginary, function, path_universe].")
        real, imaginary, function, path_universe = address
        real = DataManager.coordinate_string(real)
        if isinstance(imaginary, bool) or not (
                (isinstance(imaginary, int) and imaginary >= 0)
                or isinstance(imaginary, list)):
            raise ValueError("Imaginary must be a nonnegative depth or layer stack.")
        if isinstance(function, str):
            if not function.strip():
                raise ValueError("Function registry key cannot be empty.")
        elif isinstance(function, dict):
            if not isinstance(function.get("name"), str) or not function["name"].strip():
                raise ValueError("Function descriptor requires a nonempty name.")
        else:
            raise ValueError("Function must be a registry key or descriptor.")
        if isinstance(path_universe, bool) or not isinstance(path_universe, int):
            raise ValueError("Path universe must be an integer.")
        if direction not in ("linear", "away", "toward"):
            raise ValueError("Direction must be linear, away, or toward.")
        normalized = [real, deepcopy(imaginary), deepcopy(function), path_universe]
        try:
            json.dumps(normalized, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Logical address must be JSON serializable.") from exc
        return normalized

    def save_logical_command(self, address, command, *, counter_universe=0,
                             direction="linear", event_id=None, source="oais",
                             navigation=None, host_after=None,
                             host_universe_after=None, follow_update=False,
                             success=True, event_type="command",
                             meta_transition=None, function_index=None):
        """Save a v3 command at its virtual *real* coordinate.

        No recording ID, next-event pointer, path order, or functional rule is
        written. The function field is only a pole-local activation reference.
        A random event ID prevents overwriting distinct stored objects.
        `counter_universe` is the base-60 overflow namespace, not the fourth
        array element (path universe). The path universe is supplied by caller.
        """
        address = self.validate_logical_address(address, direction=direction)
        # Only a pole may store a function definition; other events carry a
        # non-descriptive activation reference. Linear unlayered events retain
        # their default marker for compatibility with the existing terminal.
        if not isinstance(address[2], str):
            raise ValueError("Saved command function must be an opaque reference, not a definition.")
        if direction in ("away", "toward") and (
                not address[2].startswith("pi_") or len(address[2]) != 19
                or any(c not in "0123456789abcdef" for c in address[2][3:])):
            raise ValueError("Functional commands require a pole-local pi_<token> reference.")
        if isinstance(counter_universe, bool) or not isinstance(counter_universe, int):
            raise ValueError("Counter universe must be an integer.")
        event_id = uuid.uuid4().hex if event_id is None else str(event_id)
        if not event_id.strip():
            raise ValueError("Event ID cannot be empty.")
        if any(str(event.get("id")) == event_id for event in
               self.get_objects_at_coordinate(address[0], "logical_command")):
            raise ValueError("Logical event ID already exists at this coordinate.")
        if navigation is not None:
            if not isinstance(navigation, dict) or not isinstance(navigation.get("op"), str):
                raise ValueError("Navigation operation must have an op string.")
            try:
                json.dumps(navigation, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise ValueError("Navigation operation must be JSON-serializable.") from exc
        if host_after is not None:
            host_after = self.coordinate_string(host_after)
            if isinstance(host_universe_after, bool) or not isinstance(host_universe_after, int):
                raise ValueError("Host counter universe must be an integer.")
        if not isinstance(follow_update, bool):
            raise ValueError("follow_update must be a boolean.")
        if not isinstance(success, bool):
            raise ValueError("success must be a boolean.")
        if event_type not in ("command", "transition"):
            raise ValueError("Invalid event type.")
        if meta_transition is not None:
            if (event_type != "transition" or not isinstance(meta_transition, dict)
                    or set(meta_transition) != {"from", "to"}
                    or not all(isinstance(x, str) for x in meta_transition.values())):
                raise ValueError("Invalid Meta Terminal transition.")
        if function_index is not None and (isinstance(function_index, bool)
                or not isinstance(function_index, int) or function_index < 0):
            raise ValueError("Function index must be a nonnegative integer.")
        event = {
            "schema_version": 4 if navigation is not None else 3,
            "command": str(command),
            "address": address,
            "counter_universe": counter_universe,
            "direction": direction,
            "source": str(source),
        }
        if function_index is not None:
            event["function"] = function_index
        if navigation is not None:
            event["navigation"] = deepcopy(navigation)
            event["success"] = success
            event["event_type"] = event_type
            if host_after is not None:
                event["host_after"] = host_after
                event["host_universe_after"] = host_universe_after
                event["follow_update"] = follow_update
            if meta_transition is not None:
                event["meta_transition"] = deepcopy(meta_transition)
        return self.save_object(address[0], "logical_command", event_id, event)

    def load_logical_commands(self, real_coordinate, *, counter_universe=None,
                              path_universe=None, direction=None, address=None):
        """Read v3 and legacy v2 logical events from one coordinate node.

        A 4-part address filters v3 events exactly; old 3-part v2 records remain
        readable for compatibility but cannot match a v3 full-address query.
        """
        real = self.coordinate_string(real_coordinate)
        for value, name in ((counter_universe, "Counter universe"),
                            (path_universe, "Path universe")):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"{name} must be an integer.")
        if direction is not None and direction not in ("linear", "away", "toward"):
            raise ValueError("Invalid direction.")
        full_address = (self.validate_logical_address(address) if address is not None
                        else None)
        if full_address is not None and full_address[0] != real:
            raise ValueError("Full address and real coordinate must agree.")
        result = []
        for event in self.get_objects_at_coordinate(real, "logical_command"):
            event_address = event.get("address")
            # Version 2 used `universe` for base-60 overflow, *not* path history.
            overflow = event.get("counter_universe", event.get("universe"))
            if counter_universe is not None and overflow != counter_universe:
                continue
            if path_universe is not None and (not isinstance(event_address, list) or
                    len(event_address) != 4 or event_address[3] != path_universe):
                continue
            if direction is not None and event.get("direction") != direction:
                continue
            if full_address is not None and event_address != full_address:
                continue
            result.append(deepcopy(event))
        return result

    def resolve_logical_command(self, address, *, counter_universe=0,
                                direction="linear"):
        """Select only when the calculated full address identifies one event.

        Never choose the first event on an ambiguous match: Navigator / Replay
        must instead supply further deterministic state or a navigation rule.
        """
        full_address = self.validate_logical_address(address, direction=direction)
        matches = self.load_logical_commands(
            full_address[0], address=full_address,
            counter_universe=counter_universe, direction=direction,
        )
        if not matches:
            raise KeyError("No command at calculated logical address.")
        if len(matches) != 1:
            raise ValueError("Ambiguous logical address: multiple command events match.")
        return matches[0]

    # --- Compact, path-history-keyed command blocks (version 5) ---
    # The coordinate file provides the real position; counter_universe
    # disambiguates base-60 rollover; universe is the deterministic path key.
    def save_command_block(self, coordinate, command, universe, *,
                           counter_universe=0, function=None, step=None,
                           failed=False, source=None):
        coordinate = self.coordinate_string(coordinate)
        if not isinstance(universe, str) or len(universe) != 32 or any(
                c not in "0123456789abcdef" for c in universe):
            raise ValueError("Path universe must be 32 lowercase hexadecimal digits.")
        if isinstance(counter_universe, bool) or not isinstance(counter_universe, int):
            raise ValueError("Counter universe must be an integer.")
        if function is not None and (isinstance(function, bool) or
                not isinstance(function, int) or function < 0):
            raise ValueError("Function selector must be a nonnegative integer.")
        if step is not None and (isinstance(step, bool) or
                not isinstance(step, int) or step < 0):
            raise ValueError("Step magnitude must be a nonnegative integer.")
        _, path = self.coordinate_location(coordinate, create=True)
        data = self._load_or_create_json(path)
        node = data.setdefault(coordinate, {})
        blocks = node.setdefault("command_blocks", [])
        if not isinstance(blocks, list):
            raise ValueError("Coordinate command_blocks must be a list.")
        if any(isinstance(b, dict) and b.get("universe") == universe and
               b.get("counter_universe", 0) == counter_universe for b in blocks):
            raise ValueError("Command block already exists at this real/path universe.")
        block = {"command": str(command), "universe": universe}
        if counter_universe != 0:
            block["counter_universe"] = counter_universe
        if function is not None:
            block["function"] = function
        if step is not None and step != 1:
            block["step"] = step
        if failed:
            block["failed"] = True
        if source is not None and source != "base":
            block["source"] = str(source)
        blocks.append(block)
        self._write_json(path, data)
        return deepcopy(block)

    def load_command_block(self, coordinate, universe, *, counter_universe=0):
        node = self.get_coordinate_node(coordinate) or {}
        matches = [b for b in node.get("command_blocks", [])
                   if isinstance(b, dict) and b.get("universe") == universe and
                   b.get("counter_universe", 0) == counter_universe]
        if len(matches) != 1:
            raise KeyError("Missing or ambiguous v5 command block.")
        return deepcopy(matches[0])

    def delete_command_block(self, coordinate, universe, *, counter_universe=0):
        coordinate = self.coordinate_string(coordinate)
        _, path = self.coordinate_location(coordinate)
        data = self._load_json(path)
        if not isinstance(data, dict):
            return False
        node = data.get(coordinate)
        if not isinstance(node, dict):
            return False
        blocks = node.get("command_blocks", [])
        previous = len(blocks)
        blocks[:] = [b for b in blocks if not (isinstance(b, dict) and
                     b.get("universe") == universe and
                     b.get("counter_universe", 0) == counter_universe)]
        if len(blocks) == previous:
            return False
        if not blocks:
            node.pop("command_blocks", None)
        if not node:
            data.pop(coordinate, None)
        if data:
            self._write_json(path, data)
        else:
            path.unlink(missing_ok=True)
            self._cleanup_empty_directories(path.parent)
        return True

    # --- Compact command chain storage ---
    # Each command is [text, universe, next_locator, optional_source].
    # Locator is [six-digit coordinate, index within that coordinate's commands].
    # 'next' is None for the final event. No path array or event UUID is needed.
    def save_command(self, coordinate, command, universe=0, next_locator=None, source=None):
        coordinate = self.coordinate_string(coordinate)
        _, path = self.coordinate_location(coordinate, create=True)
        data = self._load_or_create_json(path)
        node = data.setdefault(coordinate, {})
        commands = node.setdefault('commands', [])
        if not isinstance(commands, list):
            raise ValueError('Coordinate commands must be a list')
        record = [str(command), int(universe), next_locator]
        if source is not None and source != 'base':
            record.append(str(source))
        index = len(commands)
        commands.append(record)
        self._write_json(path, data)
        return [coordinate, index]

    def read_command(self, locator):
        coordinate, index = locator
        node = self.get_coordinate_node(coordinate)
        if node is None:
            raise KeyError(f'Missing coordinate {coordinate}')
        commands = node.get('commands', [])
        if not isinstance(index, int) or index < 0 or index >= len(commands):
            raise KeyError(f'Missing command index {index} at {coordinate}')
        command = commands[index]
        if not isinstance(command, list) or len(command) < 3:
            raise ValueError('Malformed command block')
        return command

    def delete_last_command(self, locator):
        """Rollback only the last append; never shift surviving command indices."""
        coordinate, index = locator
        coordinate = self.coordinate_string(coordinate)
        _, path = self.coordinate_location(coordinate)
        data = self._load_or_create_json(path)
        node = data.get(coordinate, {})
        commands = node.get('commands', [])
        if index != len(commands) - 1:
            raise ValueError('Cannot remove a command referenced by newer entries')
        commands.pop()
        if not commands:
            node.pop('commands', None)
        if not node:
            data.pop(coordinate, None)
        if data:
            self._write_json(path, data)
        elif path.exists():
            path.unlink()
            self._cleanup_empty_directories(path.parent)

    def save_sticky_pointer(self, coordinate, title, start, end, after, scope='base'):
        """Small endpoint pointer at the first event's real coordinate."""
        coordinate = self.coordinate_string(coordinate)
        _, path = self.coordinate_location(coordinate, create=True)
        data = self._load_or_create_json(path)
        node = data.setdefault(coordinate, {})
        pointers = node.setdefault('sticky_notes', [])
        # A compact ID permits identical titles while keeping refs unambiguous.
        import uuid
        note = {'id': uuid.uuid4().hex[:12], 'title': str(title),
                'start': start, 'end': end, 'after': after, 'scope': scope}
        pointers.append(note)
        self._write_json(path, data)
        return note

    def list_sticky_pointers(self):
        notes = []
        for path in self.coordinate_dir.rglob('*.json'):
            data = self._load_json(path)
            if not isinstance(data, dict):
                continue
            for coordinate, node in data.items():
                if not isinstance(node, dict):
                    continue
                for note in node.get('sticky_notes', []):
                    if isinstance(note, dict):
                        notes.append(dict(note))
        return notes

    def find_sticky_pointer(self, identifier):
        identifier = str(identifier).lower()
        notes = self.list_sticky_pointers()
        found = [note for note in notes if str(note.get('id', '')).lower() == identifier]
        if found:
            return found[0]
        found = [note for note in notes if str(note.get('title', '')).lower() == identifier]
        if len(found) > 1:
            raise ValueError('Multiple notes have this title; use a note ID')
        if not found:
            raise KeyError(identifier)
        return found[0]

    # --- Message storage ---
    def create_coordinate_message(self, coordinate, title, message, on_list=False, display_coord=None, extra_data=None):
        """
        DEEP-like message storage retained for OAIS.

        This allows OAIS to attach descriptive information
        to a coordinate in addition to generic objects.
        """
        coordinate = self.coordinate_string(coordinate)
        if extra_data is None:
            extra_data = {}
        self._store_real_message(coordinate=coordinate, title=title, message=message, on_list=on_list, extra_data=extra_data)
        if display_coord is None:
            return
        if isinstance(display_coord, (list, tuple)):
            for display in display_coord:
                self._store_pointer_metadata(display_coord=display, real_coordinate=coordinate, real_title=title)
        else:
            self._store_pointer_metadata(display_coord=display_coord, real_coordinate=coordinate, real_title=title)

    def _store_real_message(self, coordinate, title, message, on_list, extra_data):
        _, json_path = self.coordinate_location(coordinate, create=True)
        json_data = self._load_or_create_json(json_path)
        node = json_data.setdefault(coordinate, {})
        if not isinstance(node, dict):
            node = {}
            json_data[coordinate] = node
        messages = node.setdefault('messages', [])
        if not isinstance(messages, list):
            messages = []
            node['messages'] = messages
        entry = {'coordinate': coordinate, 'title': title, 'message': message, 'on_list': on_list, 'data': extra_data}
        messages.append(entry)
        self._write_json(json_path, json_data)
        bury = extra_data.get('bury', False)
        if not bury:
            self.add_to_show_list(coordinate)

    # --- Pointer metadata ---
    def _store_pointer_metadata(self, display_coord, real_coordinate, real_title):
        """
        Store a DEEP-style coordinate pointer.

        OAIS can later generalize this into its broader
        reference system.
        """
        display_coord = self.coordinate_string(display_coord)
        real_coordinate = self.coordinate_string(real_coordinate)
        _, json_path = self.coordinate_location(display_coord, create=True)
        json_data = self._load_or_create_json(json_path)
        node = json_data.setdefault(display_coord, {})
        if not isinstance(node, dict):
            node = {}
            json_data[display_coord] = node
        pointers = node.setdefault('pointer_data', [])
        if not isinstance(pointers, list):
            pointers = []
            node['pointer_data'] = pointers
        pointer = {'to_coord': real_coordinate, 'to_title': real_title}
        if pointer not in pointers:
            pointers.append(pointer)
        self._write_json(json_path, json_data)
        self.add_to_show_list(display_coord)

    # --- Load messages ---
    def load_coordinate_messages(self, coordinate):
        """
        Load messages and pointer metadata at a coordinate.
        """
        coordinate = self.coordinate_string(coordinate)
        node = self.get_coordinate_node(coordinate)
        if node is None:
            return None
        results = []
        messages = node.get('messages', [])
        if isinstance(messages, list):
            results.extend(messages)
        pointers = node.get('pointer_data', [])
        if isinstance(pointers, dict):
            pointers = [pointers]
        if isinstance(pointers, list):
            for pointer in pointers:
                if not isinstance(pointer, dict):
                    continue
                real_coordinate = pointer.get('to_coord')
                real_title = pointer.get('to_title')
                results.append({'coordinate': coordinate, 'title': f'[Pointer to {real_coordinate}]', 'message': '', 'data': {'pointer_to_coord': real_coordinate, 'pointer_to_title': real_title}})
        return results if results else None

    # --- Compatibility with older callers (no dedicated index file) ---
    def add_to_show_list(self, coordinate):
        return None

    def remove_from_show_list(self, coordinate):
        return None

    def load_show_list(self):
        return self.list_stored_coordinates()

    # --- Stored coordinates ---
    def list_stored_coordinates(self):
        """
        Return every valid full coordinate currently stored
        anywhere in OAIS coordinate_data.
        """
        coordinates = []
        if not self.coordinate_dir.exists():
            return coordinates
        for json_path in self.coordinate_dir.rglob('*.json'):
            json_data = self._load_json(json_path)
            if not isinstance(json_data, dict):
                continue
            for key in json_data.keys():
                try:
                    normalized = self.coordinate_string(key)
                except ValueError:
                    continue
                coordinates.append(normalized)
        return sorted(set(coordinates), key=self._coordinate_sort_key)

    # --- Nearest coordinate ---
    def find_nearest_stored_coordinate(self, coordinate, direction='either'):
        """
        Find the nearest coordinate for which OAIS has
        stored coordinate data.

        direction:

            "either"
            "forward"
            "backward"

        Uses the DEEP base-60 convention:

            p0 is least significant.
        """
        coordinate = self.coordinate_string(coordinate)
        target_value = self._coordinate_to_base10(coordinate)
        stored = self.list_stored_coordinates()
        if not stored:
            return None
        candidates = []
        for stored_coordinate in stored:
            value = self._coordinate_to_base10(stored_coordinate)
            difference = value - target_value
            if direction == 'forward' and difference < 0:
                continue
            if direction == 'backward' and difference > 0:
                continue
            if direction not in ('either', 'forward', 'backward'):
                raise ValueError("direction must be 'either', 'forward', or 'backward'.")
            candidates.append((abs(difference), value, stored_coordinate))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    # --- Base-60 helpers ---
    def _coordinate_to_base10(self, coordinate):
        parts = self.parse_coordinate(coordinate)
        return sum((value * 60 ** index for index, value in enumerate(parts)))

    def _coordinate_sort_key(self, coordinate):
        return self._coordinate_to_base10(coordinate)

    # --- JSON helpers ---
    def _load_json(self, json_path):
        json_path = Path(json_path)
        if not json_path.exists():
            return None
        try:
            with json_path.open('r', encoding='utf-8') as source:
                return json.load(source)
        except (json.JSONDecodeError, OSError) as exc:
            print(f'Warning: could not read OAIS data file {json_path}: {exc}')
            return None

    def _load_or_create_json(self, json_path):
        data = self._load_json(json_path)
        if isinstance(data, dict):
            return data
        return {}

    def _write_json(self, json_path, json_data, sort_coordinates=True):
        """
        Atomically write JSON.

        This avoids leaving half-written OAIS data if
        DEEP exits or restarts during a write.
        """
        json_path = Path(json_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        if sort_coordinates and isinstance(json_data, dict):
            try:
                json_data = dict(sorted(json_data.items(), key=lambda item: self._coordinate_sort_key(item[0])))
            except (ValueError, TypeError):
                pass
        temporary = Path(str(json_path) + '.tmp')
        try:
            with temporary.open('w', encoding='utf-8') as output:
                json.dump(json_data, output, indent=4)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, json_path)
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass

    # --- Directory cleanup ---
    def _cleanup_empty_directories(self, start_directory):
        """
        Remove empty coordinate directories after deletion,
        stopping at coordinate_data itself.
        """
        current = Path(start_directory)
        root = self.coordinate_dir.resolve()
        while True:
            try:
                resolved = current.resolve()
            except OSError:
                break
            if resolved == root:
                break
            try:
                if any(current.iterdir()):
                    break
                current.rmdir()
            except OSError:
                break
            current = current.parent
