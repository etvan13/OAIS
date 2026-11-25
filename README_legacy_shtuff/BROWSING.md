# OAIS note browser

The saved Sticky Note collections are the index. Listing, title searching and
missing-note lookups never scan `coordinate_data`. They read the relevant
`terminal_data/<terminal_id>/sticky_notes_*.json` files. Collection contents
are cached per reader and refreshed when a file is replaced, modified or
removed. The existing storage format, importer and Navigator functions are
unchanged. No migration or re-import of existing typed notes is needed.

## Terminal

From OAIS (or with the `oais` prefix when attached to BASE):

```text
replay
list conversations
search spacecraft
more
prev
page 2
list commands
list all
load 1
next
next 5
all
reset
exit
```

The initial interactive menu lists all types. `list [type] [page]` changes the
filter and clears the search; `search <title>` searches the current type and
returns to page 1. A bare `search` clears it. `more`, `prev` and `page N` page
through the same filter/search. A page shows up to 20 notes, numbered globally
within the current result set. Choose a displayed number, exact title or ID.
Numbers resolve to the IDs on the displayed page, even if a collection changes.
Use IDs if titles are duplicated. Direct commands such as
`replay list conversations 2` and `replay search spacecraft` work as well.

`replay load <title or ID>` reconstructs one note and shows a summary; `next`
shows one event, `next N` shows N, and `all` shows the remaining events.
Selecting a conversation/data note directly shows its first block, while
selecting a command note retains the old display-all behavior. `view host/full`
continues to filter command history, not conversation or other data events.
`replay data <six base-60 digits>` inspects all typed blocks and legacy messages
at that coordinate only. Replay remains read-only: no command is dispatched and
no live Navigator is moved.

`sticky list [type] [page]` and `sticky search <title>` use the same metadata
browser. `sticky read <title or ID>` reads the selected note.

## External Python backend

```python
from oais.utils.data_manager import DataManager
from oais.Commands.Replay.ReplayEngine import ReplayEngine

reader = ReplayEngine(DataManager(), terminal_id="base")
page = reader.browse("conversation", query="spacecraft", page=1, limit=20)
print(page["total"], page["pages"])
for item in page["items"]:
    print(item["id"], item["title"], item["start"], item["end"])

if page["items"]:
    item = page["items"][0]
    note, events = reader.read_note(item["id"], block_type=item["type"])
    print(events[0]["value"])
```

Pass `None` to browse all types, or `"command"`, `"conversation"`, `"text"`,
`"file"` for one collection. The `terminal_id` must match the owner of the
imported/saved data (the conversation importer defaults to `base`). If you
use a custom data directory, pass `DataManager(base_dir=...)`.

`browse` returns a detached dictionary with `items`, `page`, `limit`, `total`,
`pages`, `query`, and `type`. Each item has `number`, `id`, `title`, `type`,
`start`, `end`, and `blocks`. It does not include the command plan or payloads.
The title search ranks exact title/ID matches first, then phrase matches, then
matches containing every query word. It is lexical, not embedding-based.

`read_note` returns the selected note and its ordered structured events; it
neither prints nor modifies the reader's playback cursor. The corresponding
recording-engine methods are `StickyNoteEngine.browse_notes`, `search_notes`,
`get_note` and `load_path`. Reuse a reader instance to benefit from its cache.
For direct location reads use `DataManager.get_blocks_at_coordinate`.

## Legacy records and limits

Old coordinate-only Sticky Notes (not terminal collection notes) are not
included in normal discovery. Recover them explicitly through
`StickyNoteEngine.list_notes(include_legacy=True)` or
`load_path(identifier, include_legacy=True)` / `ReplayEngine.read_note(...,
include_legacy=True)`. Those explicit legacy operations can scan the coordinate
space. The old terminal-owned `sticky_notes.json` filename migration still
works as before. No coordinate data is deleted by this update.

The first browse of a type parses its whole collection JSON. Later pages use
the cache; each selected conversation still reconstructs its complete path to
verify its endpoint and history before displaying the first block. This is
not yet a streaming reader, semantic similarity index, or random narrative
constructor.

## Tests

```bash
python3 -m pytest -q tests/test_note_browser.py tests/test_typed_data_paths.py
```

The tests check that browsing and unsuccessful lookups perform no coordinate
reads/scans, cache invalidation, page numbering, search ranking, selected-path
reads, typed display, explicit legacy recovery and stateless external reads.
