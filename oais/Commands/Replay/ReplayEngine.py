"""Read-only playback of paths reconstructed from OAIS coordinate objects.

Never dispatches stored commands or mutates a live Navigator/Counter.  v4 path
reconstruction is delegated to StickyNoteEngine.load_path, which recalculates
addresses, retrieves DataManager objects, and verifies the endpoint.
"""

from copy import deepcopy

try:
    from ..StickyNote.StickyNoteEngine import StickyNoteEngine
    from ...utils.counter import Counter
except ImportError:
    from Commands.StickyNote.StickyNoteEngine import StickyNoteEngine
    from utils.counter import Counter


class ReplayEngine:
    def __init__(self, data_manager, terminal_id="oais_standalone"):
        self.data_manager = data_manager
        self.terminal_id = terminal_id
        self.note = None
        self.events = []
        self.cursor = 0
        self.view = "host"
        self.browser_type = None
        self.browser_query = ""
        self.browser_page = 1
        self.browser_limit = 20
        self.browser_result = None

    def _reader(self):
        # A persistent reader reuses cached collection metadata across pages.
        if not hasattr(self, "_note_reader"):
            self._note_reader = StickyNoteEngine(
                counter=Counter(load_state=False, persist=False),
                data_manager=self.data_manager, terminal_id=self.terminal_id)
        return self._note_reader

    def available(self, block_type="command"):
        """Compatibility API: full records, command-only by default."""
        return self._reader().list_notes(block_type=block_type)

    def browse(self, block_type=None, *, query="", page=1, limit=20):
        """Structured metadata for external callers; does not change menu state."""
        return self._reader().browse_notes(block_type, query=query, page=page, limit=limit)

    def read_note(self, identifier, *, block_type=None, include_legacy=False):
        """Return one verified (note, events) pair without changing playback state."""
        return self._reader().load_path(identifier, block_type=block_type,
                                        include_legacy=include_legacy)

    def list_notes(self, block_type="command", *, query="", page=1, limit=20):
        result = self.browse(block_type, query=query, page=page, limit=limit)
        self.browser_type, self.browser_query = block_type, query
        self.browser_page, self.browser_limit = page, limit
        self.browser_result = result
        if not result["total"]:
            return "No saved Sticky Notes matching this selection."
        label = block_type or "all types"
        lines = [f"SAVED STICKY NOTES — {self.terminal_id} | {label} | "
                 f"Page {page}/{result['pages']} | {result['total']} notes"]
        for note in result["items"]:
            count = note["blocks"] if note["blocks"] is not None else "?"
            lines.append(f"{note['number']}. {note['title']} [{note['id']}] — {count} {note['type']} blocks")
        if not result["items"]:
            lines.append("Page out of range; choose an earlier page.")
        lines.append("Choose a displayed number, title, or ID. 'page N', 'more', 'prev', 'search <title>', 'list <type>'.")
        return "\n".join(lines)

    def _resolve_selection(self, identifier, block_type=None):
        if isinstance(identifier, str) and identifier.strip().isdigit():
            index = int(identifier.strip())
            result = getattr(self, "browser_result", None)
            if result is None or (block_type is not None and result["type"] != block_type):
                result = self.browse(block_type if block_type is not None else self.browser_type)
            for item in result["items"]:
                if item["number"] == index:
                    return item["id"], item["type"]
            raise ValueError("Choose a number on the displayed page, or use a title or ID.")
        return identifier, block_type

    def load(self, identifier, *, view=None, block_type=None):
        """Reconstruct only the selected note; no command execution."""
        identifier, block_type = self._resolve_selection(identifier, block_type)
        if view is not None and view not in ("host", "full"):
            raise ValueError("Replay view must be host or full.")
        note, events = self.read_note(identifier, block_type=block_type)
        if not events:
            raise ValueError("Saved path contains no events.")
        self.note = deepcopy(note)
        self.events = deepcopy(events)
        self.cursor = 0
        if view is not None:
            self.view = view
        return self.summary()

    def clear(self):
        self.note, self.events, self.cursor = None, [], 0
        self.view = "host"

    def reset(self):
        self._require_loaded()
        self.cursor = 0
        return self.summary()

    def _require_loaded(self):
        if self.note is None:
            raise ValueError("No replay loaded. Use 'replay load <title>'.")

    def visible_events(self):
        """Filter presentation only; the full ordered plan remains intact."""
        return [e for e in self.events if self.view == "full" or
                e.get("type", "command") not in ("command", "transition") or
                e.get("source", "oais").lower() not in ("oais", "meta")]

    def set_view(self, view):
        if view not in ("host", "full"):
            raise ValueError("Replay view must be host or full.")
        self.view = view
        self.cursor = 0
        return self.summary() if self.note is not None else f"Replay view: {view}"

    def summary(self):
        self._require_loaded()
        source = "terminal-owned" if self.events[0].get("from_plan") else "coordinate-backed"
        count = len(self.visible_events())
        return (f"REPLAY: {self.note.get('title', 'Untitled')} "
                f"[{self.note.get('id', '?')}] | "
                f"{self.cursor}/{count} events | {self.view} view, "
                f"{len(self.events)} total | {source}, read-only")

    @staticmethod
    def format_step(event, index):
        kind = event.get("type", "command")
        if kind == "conversation":
            value = event["value"]
            text = (f"{index}. [CONVERSATION @ {event.get('coordinate_before', '?')}]\n"
                    f"User:\n{value['user']}\n\nAssistant:\n{value['assistant']}")
            if event.get("attachments"):
                text += "\nAttachments: " + ", ".join(event["attachments"])
            return text
        if kind in ("text", "file"):
            return f"{index}. [{kind.upper()} @ {event.get('coordinate_before', '?')}] {event['value']}"
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
        events = self.visible_events()
        end = min(len(events), self.cursor + count)
        lines = [self.format_step(events[i], i + 1)
                 for i in range(self.cursor, end)]
        self.cursor = end
        if not events:
            return "No host commands in this note. Use replay view full to see OAIS history."
        if not lines:
            return "End of replay. Use 'replay reset' to start again."
        return "\n".join(lines) + f"\n[{self.cursor}/{len(events)}]"

    def all(self):
        self._require_loaded()
        return self.next(max(1, len(self.visible_events()) - self.cursor))

    def trace(self, identifier):
        """Display a complete path without moving live navigation."""
        identifier, block_type = self._resolve_selection(identifier)
        note, events = self.read_note(identifier, block_type=block_type)
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
