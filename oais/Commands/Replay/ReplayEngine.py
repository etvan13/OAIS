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
    def __init__(self, data_manager, terminal_id="oais_standalone"):
        self.data_manager = data_manager
        self.terminal_id = terminal_id
        self.note = None
        self.events = []
        self.cursor = 0

    def _reader(self):
        return StickyNoteEngine(data_manager=self.data_manager,
                                terminal_id=self.terminal_id)

    def available(self):
        """Show saved notes belonging to the active terminal, in file order."""
        return self._reader().list_notes()

    def list_notes(self):
        notes = self.available()
        if not notes:
            return "No saved Sticky Notes for this terminal."
        lines = ["SAVED STICKY NOTES — " + self.terminal_id]
        for index, note in enumerate(notes, 1):
            count = note.get("blocks", note.get("event_count", "?"))
            lines.append(f"{index}. {note.get('title', 'Untitled')} "
                         f"[{note.get('id', '?')}] — {count} commands")
        lines.append("Choose a number, title, or note ID to view its commands.")
        return "\n".join(lines)

    def load(self, identifier):
        """Read private note plans first; legacy notes keep existing readers."""
        if isinstance(identifier, str) and identifier.strip().isdigit():
            index = int(identifier.strip())
            notes = self.available()
            if not 1 <= index <= len(notes):
                raise ValueError("Sticky Note selection is out of range.")
            identifier = notes[index - 1]["id"]
        reader = self._reader()
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
        source = "terminal-owned" if self.events[0].get("from_plan") else "coordinate-backed"
        return (f"REPLAY: {self.note.get('title', 'Untitled')} "
                f"[{self.note.get('id', '?')}] | "
                f"{self.cursor}/{len(self.events)} events | {source}, read-only")

    @staticmethod
    def format_step(event, index):
        before = event.get('logical_before')
        after = event.get('logical_after')
        source = event.get('source', 'oais').upper()
        command = event.get('value', '')
        flag = ' [failed]' if event.get('success') is False else ''
        if event.get("from_plan"):
            return f"{index}. [{source}] {command}{flag}"
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
        """Display a complete path without moving live navigation."""
        if isinstance(identifier, str) and identifier.strip().isdigit():
            index = int(identifier.strip())
            notes = self.available()
            if not 1 <= index <= len(notes):
                raise ValueError("Sticky Note selection is out of range.")
            identifier = notes[index - 1]["id"]
        reader = self._reader()
        note, events = reader.load_path(identifier)
        private = bool(events and events[0].get("from_plan"))
        if private:
            header = (f"STICKY NOTE TRACE: {note.get('title', identifier)}\n"
                      f"Start: {note.get('start', '?')} | End: {note.get('end', '?')}\n"
                      f"Events: {len(events)} | source: terminal data\n\n")
        else:
            header = (f"COORDINATE TRACE: {note.get('title', identifier)}\n"
                      f"Events: {len(events)} | source: OAIS DataManager\n\n")
        return header + "\n".join(self.format_step(e, i)
                                  for i, e in enumerate(events, 1))
