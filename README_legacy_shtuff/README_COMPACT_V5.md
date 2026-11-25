# OAIS — compact coordinate storage (v5 write phase)

This patch builds on `OAIS_terminal_data_function_selector_patch.zip` and uses `Data/terminal_data/<terminal_id>/sticky_notes.json` for note definitions. **Navigation upgrades and v5 Replay are deliberately not implemented here.**

## New behavior

When `sticky start` / `sticky save TITLE` uses logical recording (default in OAIS), new notes are schema v5. `StickyNoteEngine` validates each cached before/after navigation event with the existing Navigator, then writes **compact** `command_blocks` under each real coordinate. No new `objects.logical_command`, no full four-part address, no host-after state, and no event UUID are written to the coordinate block.

A typical coordinate file contains:

```json
{
  "2 0 0 0 0 0": {
    "command_blocks": [
      {"command": "backwards", "universe": "0123456789abcdef0123456789abcdef", "function": 1},
      {"command": "hmm", "universe": "fedcba9876543210fedcba9876543210", "failed": true}
    ]
  }
}
```

The example keys are illustrative. `universe` is a **128-bit hexadecimal path-history key**, not the Counter rollover universe. `counter_universe` is written only if nonzero; it is part of the lookup key. The coordinate is the outer JSON key, so it is not repeated in the block. `function` is written at first appearance and whenever the selected mode changes. `step` is written only for non-unit movement (including `step: 0` for stationary linear events). `failed` is written only for failures. `source` is omitted for default `base`, and retained for other sources (e.g. `oais`).

The terminal's `sticky_notes.json` stores the stable note ID generated at recording start, starting state, starting path key, ordered function catalog (definition + direction), sparse Navigator control transitions, event count, and final state to check later. A linear `backwards` event can select a `linear_offset` entry with direction `backward`; the cubic return uses the same `cubic_offset` formula with `toward` direction. The function selector describes **the movement caused by that command**, not the incoming direction.

## History algorithm, v5

- `seed_path_universe(start_coordinate, note_id, counter_universe=...)` produces the first stored event's path-history key.
- For each event `index`, the key is stored **before** updating it. `evolve_path_universe(previous, before[:3], after[:3], f"event:{index}:{command}:{navigation_op}", counter_universe_before=..., counter_universe_after=...)` produces the next key, even for stationary/failed events.
- Serialization and BLAKE2b-128 remain in `virtual_counter.py`; this patch does not modify navigation's own existing path-universe semantics. The new v5 saved history is a distinct versioned recording history until Navigator and Replay are updated to consume it.
- Keys are deterministic **for a fixed note ID and event sequence**. Independent notes have different seeds. Collision resistance is probabilistic, not a mathematical guarantee.

## API additions to DataManager

- `save_command_block(coordinate, command, universe, *, counter_universe=0, function=None, step=None, failed=False, source=None)`
- `load_command_block(coordinate, universe, *, counter_universe=0)`
- `delete_command_block(coordinate, universe, *, counter_universe=0)` for failed-save rollback

These are generic coordinate-store methods, not Sticky Note-specific. The existing `save_logical_command`, pole-function storage, and legacy linked-command helpers remain unchanged. The engine writes the terminal-note index last and rolls back coordinate blocks if a save fails before that point. **Writes are not a transaction across files or processes**; crashes/concurrent writes need future journaling/locking.

## Deliberate limitations

1. **v5 `sticky read` and Replay are not available yet.** They display a clear message, rather than trying to misread compact blocks as v4. Existing v4 saved notes can still be read and replayed.
2. Existing Navigator behavior remains; it doesn't yet use the new function catalog or history identity to move. Custom functions such as sine are not implemented.
3. Nonlinear function transitions still rely on pole definitions stored by the current Navigator and their `pi_...` references. Moving these definitions entirely into terminal JSON can be done in the navigation phase.
4. Sparse transitions are a provisional contract for future v5 Replay, not a validated replay schema. `source` and `failed` are retained when needed to preserve command-event meaning. For stationary functional events, real displacement is zero but imaginary `k` may still advance.
5. The legacy v4 saver is retained internally and selected by setting the recording session metadata key `storage_version` to `4` (used in regression tests); ordinary terminal saves produce v5.

## Tests

Run from this directory:

```bash
python -m unittest discover -s tests -q
```

The v5 tests verify reverse linear modes, repeated positions with different history keys, stationary steps, minimal fields, terminal ownership, history uniqueness, and duplicate-key rejection. Legacy v4 readers and Replay are separately regression-tested. New v5 replay is intentionally deferred.
