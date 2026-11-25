# OAIS typed coordinate data

## Running the conversation importer

From the OAIS repository root (no extra packages required):

```sh
python helpers/conversation_importer.py "path/to/conversation.json"
python helpers/conversation_importer.py --directory "path/to/Sorted_Claude_Data"
```

The input must be full normalized JSON snapshots, not the staging/appending delta files. A single file is the recommended first test. Use `--data-dir` to isolate a test import, e.g. `--data-dir ./test_data` (do not commit that directory to Git). The default terminal ID is `base` to match `python main.py`; use `--terminal-id oais_standalone` with `python main.py --connection standalone`.

The same OAIS data directory must be used by both importer and terminal. For an isolated test:

```sh
python helpers/conversation_importer.py "conversation.json" --data-dir ./test_data
python main.py --data-dir ./test_data
```

From BASE, enter `oais`, then:

```text
sticky list conversations
sticky read <title or ID>
sticky list commands
replay list
```

## Storage

Coordinate files retain their existing base-60 geometry and command record format. DataManager's `save_block`, `load_block`, `delete_block`, `get_blocks_at_coordinate`, and `list_blocks` support `command`, `conversation`, `text`, and `file`. The `file` value is a JSON file reference, not a copied binary. The `universe` is the existing 128-bit path-history key; the separate optional `counter_universe` is the base-60 overflow namespace.

Per-terminal collections are named `sticky_notes_commands.json`, `sticky_notes_conversations.json`, `sticky_notes_text.json`, and `sticky_notes_files.json`. They are created only on first save. When the command collection is first loaded, an old `sticky_notes.json` is renamed if the new file does not exist. If both files exist, the new file takes precedence and the old file is left untouched. Existing legacy coordinate-backed command notes remain readable. Command replay is restricted to command collections.

Typed data notes use `functional_data_v1`: one outward step per event, with a portable starting navigation state, count, endpoint (one step after the final block), and terminal history check. The payload resides only in coordinate data. An imported conversation gets a deterministic note ID from its source, conversation ID, and version. Reimporting identical block contents is a no-op; a complete appended suffix extends the same note. Edited prefixes, shortened snapshots, or an appended response that completes a formerly unanswered final block are rejected under the existing version instead of overwriting information. Supply a new normalized conversation version to preserve both. Forks share the same geometric sequence but have separate note-seeded history keys. The original sorted JSON retains full metadata and attachment files; the import preserves text, paired roles and referenced attachment names, not timestamps, message IDs or file bytes. Unpaired messages are preserved using an empty counterpart. The archive is never modified or deleted.

## Narrative function

`narrative_v1(pole,imaginary,X,k)` is whitelisted by the existing integer expression evaluator. Its recurrence is the old NavigationHub math with OAIS's least-significant-digit-first geometry. `narrative_expression(key)` returns the deterministic pole and portable expression. Offsets are `R_k - R_0`. When initialized at the matching pole as the importer does, real positions remain within the same counter universe. Reverse traversal evaluates earlier k values, not an algebraic inverse. A bounded transient cache keeps repeated evaluations efficient. The original legacy Coordinate class was not included, so exact historical coordinate compatibility assumes that it uses OAIS's digit order and formatting.

## General typed events (programmatic API)

```python
from oais.Commands.Navigator.NavigatorEngine import NavigatorEngine
from oais.Commands.StickyNote.StickyNoteEngine import StickyNoteEngine
from oais.utils.data_manager import DataManager
from oais.utils.counter import Counter

nav = NavigatorEngine()
nav.open_pole("k")
engine = StickyNoteEngine(
    counter=Counter(load_state=False, persist=False),
    data_manager=DataManager(), terminal_id="base",
    navigation_provider=nav.snapshot,
)
engine.start(metadata={"storage": "data"})
engine.record_event({"type": "text", "value": "First observation"})
engine.record_event({"type": "text", "value": "Second observation"})
engine.stop()
engine.save("Research observations", clear=True)
```

The save operation reconstructs progression from the captured start using an independent Navigator; recording the data payload itself does not move the live Navigator. If supplied, logical before/after positions must match that progression. Current typed notes are homogeneous, single outward-function paths. Arbitrary mixed paths, selecting already-stored blocks, random-navigation UI, live terminal `store text` commands, binary file copying and PDF/image display remain future features. Use the block discovery API for experiments with existing data. Keep imports offline or avoid concurrent writers; coordinate and terminal writes are individually atomic, not a cross-process transaction.

## Tests

```sh
python -m pytest -q tests/test_typed_data_paths.py
python -m pytest -q tests --ignore=tests/legacy --ignore=tests/test_prune_legacy_poles_v12.py
```

The legacy directory targets outdated APIs, and `test_prune_legacy_poles_v12.py` imports a utility not present in the provided archive. Existing filename assertions and the rollback mock were updated for the requested command collection rename.
