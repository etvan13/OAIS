"""OAIS virtual coordinate projection, independent of the two linear Counters.

Four-part logical address: [real, imaginary, function, path_universe].
Counter.universes (base-60 overflow) is separately represented by `.universe`.
The path-universe transition is a pure helper here; Navigator decides when to apply it.
"""
from copy import deepcopy
import hashlib
import json
from threading import RLock

from .counter import Counter
from .data_manager import DataManager

BASE = 60
DIGITS = 6
SPACE = BASE ** DIGITS


def address_to_integer(coordinate, universe=0):
    """Convert little-endian base-60 coordinate + *counter* universe to integer."""
    digits = Counter.parse_coordinate(coordinate) if isinstance(coordinate, str) else list(coordinate)
    if not Counter._valid_coordinate_list(digits):
        raise ValueError("Expected six digits between 0 and 59.")
    if isinstance(universe, bool) or not isinstance(universe, int):
        raise ValueError("Counter universe must be an integer.")
    return universe * SPACE + sum(d * BASE ** i for i, d in enumerate(digits))


def integer_to_address(index):
    """Return (real coordinate, counter universe), including negative rollover."""
    if isinstance(index, bool) or not isinstance(index, int):
        raise ValueError("Absolute coordinate index must be an integer.")
    universe, remainder = divmod(index, SPACE)
    digits = []
    for _ in range(DIGITS):
        remainder, digit = divmod(remainder, BASE)
        digits.append(digit)
    return " ".join(map(str, digits)), universe


# Versioned, deterministic history identity. This does not move a coordinate.
# The function at the pole and the navigation plan remain Navigator concerns.
def _history_key(secret):
    if secret is None:
        return b""
    if not isinstance(secret, bytes) or not (1 <= len(secret) <= 64):
        raise ValueError("Secret must be 1–64 bytes when supplied.")
    return secret


def _history_digest(payload, secret=None):
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(
        serialized, digest_size=16, key=_history_key(secret),
        person=b"OAISPathU-v1").digest(), "big")


def seed_path_universe(start_coordinate, seed, *, counter_universe=0, secret=None):
    """Derive a 128-bit path history seed from its starting position and note seed.

    `seed` belongs to the traversal's entry descriptor, never every command.
    `secret` is optional and must stay outside public coordinate storage if used
    as an actual authentication/discovery barrier.
    """
    if not isinstance(seed, str) or not seed:
        raise ValueError("A nonempty traversal seed is required.")
    absolute_start = address_to_integer(start_coordinate, counter_universe)
    return _history_digest(["seed", 1, absolute_start, seed], secret)


def evolve_path_universe(previous_universe, before, after, operation, *,
                         counter_universe_before=0, counter_universe_after=0,
                         secret=None):
    """Compute next path universe from previous state and an ordered transition.

    `before` and `after` are [real, imaginary, function_ref] signatures,
    NOT four-part addresses: the prior path universe is supplied separately.
    The transition operation distinguishes a turn, return, hold, jump, etc.
    This routine is pure: it does not move VirtualCounter or persist a record.
    """
    if isinstance(previous_universe, bool) or not isinstance(previous_universe, int) or previous_universe < 0:
        raise ValueError("Previous path universe must be a nonnegative integer.")
    if not isinstance(operation, str) or not operation.strip():
        raise ValueError("Operation must be a nonempty string.")

    def normalize(signature, counter_universe):
        if not isinstance(signature, (list, tuple)) or len(signature) != 3:
            raise ValueError("State signature must be [real, imaginary, function].")
        address = DataManager.validate_logical_address([*signature, previous_universe])
        absolute = address_to_integer(address[0], counter_universe)
        return [absolute, address[1], address[2]]

    return _history_digest([
        "step", 1, previous_universe,
        normalize(before, counter_universe_before),
        normalize(after, counter_universe_after),
        operation.strip(),
    ], secret)


class VirtualCounter:
    """Separate host-observing virtual position, not a navigation algorithm.

    FOLLOW mirrors the observed terminal position and resets proposed imaginary
    context. FREE keeps the virtual position while the host keeps moving.
    Navigator can later call set_projection with a calculated path universe.
    """

    def __init__(self, coordinate="0 0 0 0 0 0", universe=0, *, path_universe=0):
        self._lock = RLock()
        self.coordinate, self.universe = integer_to_address(
            address_to_integer(coordinate, universe)
        )
        self.mode = "follow"
        self.imaginary = 0
        self.function = "linear_offset"
        self.direction = "linear"
        self.path_universe = self._validate_path_universe(path_universe)
        self._observed_host = None

    @staticmethod
    def _validate_path_universe(value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Path universe must be an integer.")
        return value

    def observe_host(self, coordinate, universe=0):
        """Copy external state only while FOLLOW; never modify the host Counter."""
        normalized = integer_to_address(address_to_integer(coordinate, universe))
        with self._lock:
            self._observed_host = normalized
            if self.mode == "follow":
                self.coordinate, self.universe = normalized
                self._reset_context()
            return self.snapshot()

    def sync_to_host(self, coordinate=None, universe=None, *, path_universe=0):
        """Snap to observed linear state, start a new logical path origin.

        Until the legacy DefaultPath recurrence is available, the seed is an
        explicit integer (default zero), not a derived history identifier.
        """
        seed = self._validate_path_universe(path_universe)
        with self._lock:
            if coordinate is not None:
                self._observed_host = integer_to_address(
                    address_to_integer(coordinate, 0 if universe is None else universe)
                )
            if self._observed_host is None:
                raise ValueError("No host Counter has been observed yet.")
            self.coordinate, self.universe = self._observed_host
            self.mode = "follow"
            self._reset_context()
            self.path_universe = seed
            return self.snapshot()

    def hold(self):
        """Stop mirroring the host; Navigator may subsequently set projections."""
        with self._lock:
            self.mode = "free"
            return self.snapshot()

    def set_projection(self, coordinate, universe=0, *, imaginary=0,
                       function="linear_offset", direction="linear",
                       path_universe=None):
        """Accept a calculated virtual projection; do NOT derive path history.

        `universe` means Counter base-60 rollover; `path_universe` is the fourth
        address component. If omitted, retain the current path universe.
        """
        with self._lock:
            new_path_universe = (self.path_universe if path_universe is None
                                 else self._validate_path_universe(path_universe))
            address = DataManager.validate_logical_address(
                [coordinate, imaginary, function, new_path_universe],
                direction=direction,
            )
            position = integer_to_address(address_to_integer(address[0], universe))
            self.coordinate, self.universe = position
            self.imaginary = deepcopy(address[1])
            self.function = deepcopy(address[2])
            self.path_universe = address[3]
            self.direction = direction
            self.mode = "free"
            return self.snapshot()

    def logical_address(self):
        """Return [real, imaginary, function, path_universe] (not overflow universe)."""
        with self._lock:
            return [self.coordinate, deepcopy(self.imaginary),
                    deepcopy(self.function), self.path_universe]

    def snapshot(self):
        with self._lock:
            host = None if self._observed_host is None else {
                "coordinate": self._observed_host[0],
                "counter_universe": self._observed_host[1],
            }
            return {
                "coordinate": self.coordinate,
                "universe": self.universe,  # backwards-compatible: Counter overflow
                "counter_universe": self.universe,
                "path_universe": self.path_universe,
                "imaginary": deepcopy(self.imaginary),
                "function": deepcopy(self.function),
                "direction": self.direction,
                "mode": self.mode,
                "host": host,
            }

    def _reset_context(self):
        self.imaginary = 0
        self.function = "linear_offset"
        self.direction = "linear"
        # Never silently invent or reset a history-derived identity here.
        # sync_to_host explicitly seeds it, and Navigator will evolve it.
