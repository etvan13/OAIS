# OAIS v11 — Compact Virtual Checkpoints and Replay-Ready Sticky Notes

**Scope:** navigation persistence and Sticky Note storage only. This update **does not implement Replay**, execute saved commands, or separate BASE into an independent repository (both are future work).

## Changes at a glance

1. `virtual_coordinate.json` now stores a **portable mathematical checkpoint**, not a duplicate of `NavigatorEngine.snapshot()`.
2. The checkpoint retains its projected coordinate, source identity and last observed source Counter, **one root pole**, and the ordered functions with their own `k` and direction. `paused`, `free`, and `held` appear only when their behavior matters.
3. Navigating with the same source after restart uses the saved root pole and function ticks. The reconstructed functions are mathematically equivalent; runtime `pi_...` identifiers and the old `path_universe` are **not** persisted. A deterministic *checkpoint seed* establishes a new runtime path history on restoration. **History identity does not continue byte-for-byte across restarts.** Sticky Notes retain their separate note-seeded deterministic universe history, which does not rely on runtime activation IDs.
4. When a source switches (BASE ↔ standalone OAIS), virtual navigation rebases as before; an interrupted function is kept as a **compact `suspended_context`** instead of an additional full Navigator snapshot.
5. `host_coordinate.json` is no longer written by the Meta Terminal. OAIS' current observed source already appears as `source_coordinate` in its virtual checkpoint. An old `host_coordinate.json` is left untouched rather than deleted.
6. New Sticky Notes keep a **complete ordered `plan` in their private terminal collection** while coordinate `command_blocks` remain in the existing compact public format. No public event-number field is added.

## Example virtual checkpoint

A function anchored at BASE coordinate 3, cubic at `k=3`, then a nested quadratic at `k=2`:

```json
{
  "coordinate": "34 0 0 0 0 0",
  "coordinate_list": [34, 0, 0, 0, 0, 0],
  "universes": 0,
  "source": "base",
  "functions": [
    {"f": "k**3", "k": 3, "direction": 1},
    {"f": "k**2", "k": 2, "direction": 1}
  ],
  "pole": "3 0 0 0 0 0",
  "source_coordinate": "8 0 0 0 0 0",
  "source_universes": 0
}
```

For nonzero root-pole overflow, `pole_universes` is included. When a stack is paused, `paused: true` is included. When the stack is empty but the virtual position hasn't yet rejoined the source, `free: true` is included. `held: true` preserves an explicit virtual hold across restart. An optional `suspended_context` may be present after switching navigation sources.

The next real coordinate follows the existing rule

`x = pole + Σ (f_j(k_j) − f_j(0))`

with each child anchored at its parent's current projection. The live Navigator is still the authority while running; this file is its persisted mathematical state, not a source of additional ticks.

## Example new Sticky Note metadata

The private collection is `Data/terminal_data/<terminal_id>/sticky_notes.json`, now `version: 3` for new entries. Previous v2 note entries are left intact in the same collection.

```json
{
  "id": "example",
  "title": "cubic out and back",
  "start": "7 0 0 0 0 0",
  "end": "7 0 0 0 0 0",
  "start_state": {
    "coordinate": "7 0 0 0 0 0",
    "coordinate_list": [7, 0, 0, 0, 0, 0],
    "universes": 0,
    "source": "base",
    "functions": [],
    "source_coordinate": "7 0 0 0 0 0",
    "source_universes": 0
  },
  "functions": [
    {"f": "k**3", "direction": 1},
    {"f": "k**3", "direction": -1}
  ],
  "blocks": 3,
  "plan": [
    {"command": "navigator function k**3", "source": "oais", "op": "open", "delta": 1, "f": "k**3"},
    {"command": "forwards", "source": "base", "op": "auto_forward", "delta": 1},
    {"command": "backwards", "source": "base", "op": "auto_back", "delta": -1}
  ]
}
```

This is a **format illustration** (the shown end coordinate returns to 7). New notes include every actual recorded command, its source, its Navigator operation, any source movement `delta`, any newly selected expression `f`, and optional synchronization target/anchor/failure markers. They do not duplicate all intermediate virtual coordinates. The start state is captured *when recording starts*, including preexisting nested functions, directions, and the root pole.

`plan` provides ordering so Replay can simulate the math without having to discover the next command block by scanning public storage or depending on transient `pi_...` IDs. The legacy `functions` catalog remains because existing coordinate-block `function` selectors refer to it. Older redundant `origin`, `auto`, and `transitions` fields are omitted for **new v11 notes**; older saved notes are not rewritten.

### Shared coordinate blocks are unchanged

```json
{
  "command": "backwards",
  "universe": "b5796cc1ad9f9646a35f3c03ed369865",
  "function": 1
}
```

Blocks can include sparse `step`, `source`, `failed`, and overflow information as needed. They **do not** contain the note title, complete plan, root stack, event number, or a copy of `start_state`.

## File ownership / safety

- BASE owns its own physical Counter file; OAIS owns its own `current_coordinate.json`.
- Only the OAIS worker persists the virtual JSON in connected Meta Terminal mode (no parent/worker write race).
- The virtual file is written atomically and is never itself treated as a tick event.
- Sticky Note definitions live under the appropriate terminal ID (`base` when connected, `oais_standalone` when running alone).
- Previously persisted v9/v10 `navigation` snapshots can still be loaded. The next save converts them to the compact format. Do not manually edit a checkpoint while either terminal is running.
- **Replay is still not implemented for these new compact notes**: `StickyNoteEngine.load_path` intentionally raises `NotImplementedError` for them. A test-only mathematical reconstruction proves that the saved plan has enough information to recover the final virtual position, without interpreting/re-executing the commands.

## Quick WSL test

```bash
python3 main.py --start "7 0 0 0 0 0" --data-dir ./scratch-data
```

1. `oais sticky start`
2. `oais navigator function k**3`
3. `forwards` three times, then `backwards` three times.
4. `oais sticky stop` and `oais sticky save test_11`.
5. Inspect `scratch-data/virtual_coordinate.json` and `scratch-data/terminal_data/base/sticky_notes.json`. The latter should include `plan` and `start_state`, while shared `coordinate_data` should retain only the compact command blocks.
6. Verify no new `scratch-data/host_coordinate.json` was created.

Run the full suite with `python3 -m unittest discover -s tests -q` from the project root. PTY tests run on POSIX/WSL when `pexpect` is present.
