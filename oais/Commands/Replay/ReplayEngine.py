"""Read-only playback of paths reconstructed from OAIS coordinate objects.

Never dispatches stored commands or mutates a live Navigator/Counter.  v4 path
reconstruction is delegated to StickyNoteEngine.load_path, which recalculates
addresses, retrieves DataManager objects, and verifies the endpoint.
"""

from copy import deepcopy

try:
    from ..StickyNote.StickyNoteEngine import StickyNoteEngine
except ImportError:
    from Commands.StickyNote.StickyNoteEngine import StickyNoteEngine


class ReplayEngine:
    def __init__(self, data_manager):
        self.data_manager = data_manager
        self.note = None
        self.events = []
        self.cursor = 0

    def load(self, identifier):
        """Re-read the route from coordinate storage; commit state on success only."""
        reader = StickyNoteEngine(data_manager=self.data_manager)
        note, events = reader.load_path(identifier)
        if not events:
            raise ValueError("Saved path contains no events.")
        self.note = deepcopy(note)
        self.events = deepcopy(events)
        self.cursor = 0
        return self.summary()

    def clear(self):
        self.note, self.events, self.cursor = None, [], 0

    def reset(self):
        self._require_loaded()
        self.cursor = 0
        return self.summary()

    def _require_loaded(self):
        if self.note is None:
            raise ValueError("No replay loaded. Use 'replay load <title>'.")

    def summary(self):
        self._require_loaded()
        return (f"REPLAY: {self.note.get('title', 'Untitled')} "
                f"[{self.note.get('id', '?')}] | "
                f"{self.cursor}/{len(self.events)} events | "
                "coordinate-backed, read-only")

    @staticmethod
    def format_step(event, index):
        before = event.get('logical_before')
        after = event.get('logical_after')
        source = event.get('source', 'oais').upper()
        command = event.get('value', '')
        flag = ' [failed]' if event.get('success') is False else ''
        if before is not None and after is not None:
            op = event.get('navigation', {}).get('op', 'none')
            return (f"{index}. [{source}] {command}{flag} (op={op})\n"
                    f"   real: {before[0]} -> {after[0]}\n"
                    f"   i: {before[1]} -> {after[1]}\n"
                    f"   function: {before[2]} -> {after[2]}\n"
                    f"   path universe: {before[3]} -> {after[3]}")
        return (f"{index}. [{source}] {command}{flag}\n"
                f"   real: {event.get('coordinate_before', '?')} -> "
                f"{event.get('coordinate_after', '?')}")

    def next(self, count=1):
        self._require_loaded()
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("Step count must be a positive integer.")
        end = min(len(self.events), self.cursor + count)
        lines = [self.format_step(self.events[i], i + 1)
                 for i in range(self.cursor, end)]
        self.cursor = end
        if not lines:
            return "End of replay. Use 'replay reset' to start again."
        return "\n".join(lines) + f"\n[{self.cursor}/{len(self.events)}]"

    def all(self):
        self._require_loaded()
        return self.next(len(self.events) - self.cursor) if self.cursor < len(self.events) else self.next()

    def trace(self, identifier):
        """Read from coordinates and format an entire path without changing session."""
        reader = StickyNoteEngine(data_manager=self.data_manager)
        note, events = reader.load_path(identifier)
        return (f"COORDINATE TRACE: {note.get('title', identifier)}\n"
                f"Events: {len(events)} | source: OAIS DataManager\n\n" +
                "\n".join(self.format_step(e, i)
                          for i, e in enumerate(events, 1)))
