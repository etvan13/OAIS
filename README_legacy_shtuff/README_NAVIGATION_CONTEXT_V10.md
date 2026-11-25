# OAIS v10 — Navigation Source and Sticky Note Entry Context

This update builds on the v9 virtual-coordinate file. It does **not** implement Replay or change BASE's own command dispatch.

## One source for virtual progression

- **Connected:** BASE's normal Counter is the virtual source. OAIS's own Counter still advances independently when OAIS receives input. While a function is active, each eligible BASE command advances `k` once; `backwards` reduces it, including unwinding nested layers.
- **Standalone (`python3 main.py --mode oais`):** OAIS's normal Counter is the virtual source. Eligible OAIS commands advance `k` while the normal Counter continues linearly.
- Switching source or reconnecting after the source coordinate has changed **rebases** the virtual projection to that source and clears the active function stack. This avoids accidentally resuming a BASE function as an OAIS function, or interpreting an offline jump as imaginary ticks. An interrupted active function is retained in optional `suspended_context` for inspection, **not automatically resumed**.
- Restarting with the **same source and same source-coordinate** preserves and restores the function stack and its current ticks. Neither opening a new function nor restoring a state advances `k`.
- Switching source while a temporary Sticky Note is active or contains unsaved events is rejected; first save or clear the note so its starting state remains meaningful.

## Live coordinate checkpoint

`oais/Data/virtual_coordinate.json` (or `<--data-dir>/virtual_coordinate.json`) is saved atomically alongside `current_coordinate.json`.

A typical example after starting at BASE coordinate 3, advancing cubic to `k=3`, then nesting quadratic to `k=2`:

```json
{
  "coordinate": "34 0 0 0 0 0",
  "coordinate_list": [34, 0, 0, 0, 0, 0],
  "universes": 0,
  "functions": [
    {"f": "k**3", "k": 3, "direction": 1},
    {"f": "k**2", "k": 2, "direction": 1}
  ],
  "mode": "free",
  "automatic": true,
  "source": "base",
  "source_coordinate": "8 0 0 0 0 0",
  "source_universes": 0,
  "navigation": {"...": "full, validated Navigator snapshot"}
}
```

Here `coordinate` is the **projected virtual real coordinate**, and `source_coordinate` is BASE's actual latest coordinate. The first three fields intentionally resemble `current_coordinate.json`. The `functions` list describes the minimal mathematical continuation state (expression, tick, direction), ordered oldest-to-newest. `navigation` holds the extra pole anchors and path history necessary for **exact runtime restoration**. The `"..."` object above is abbreviated for illustration; the actual file contains the complete Navigator snapshot.

## Sticky Note starting state

When `sticky start` is executed, StickyNoteEngine captures both an exact in-memory Navigator snapshot (for its current save-time simulation) and a **portable `start_state`** derived from that very snapshot. It does not separately reread the JSON file, which could change mid-recording. The saved note in `Data/terminal_data/<terminal_id>/sticky_notes.json` includes:

```json
"start_state": {
  "coordinate": "34 0 0 0 0 0",
  "coordinate_list": [34, 0, 0, 0, 0, 0],
  "universes": 0,
  "functions": [
    {"f": "k**3", "k": 3, "direction": 1},
    {"f": "k**2", "k": 2, "direction": 1}
  ],
  "mode": "free",
  "automatic": true,
  "source": "base",
  "source_coordinate": "8 0 0 0 0 0",
  "source_universes": 0
}
```

The complete starting stack is now saved **on every new compact note**, not only when recording starts inside multiple layers. This distinguishes two notes at the same real coordinate with different future steps. The existing `start`, `end`, `functions` catalog, optional `origin`, sparse `transitions`, and coordinate-level command blocks are retained for compatibility. New note entries are still **not replayable**; Replay is a separate future implementation.

## Process ownership and prompt acknowledgment

Only the OAIS worker writes the virtual checkpoint in connected Meta Terminal mode. The parent mirror no longer races that worker's `virtual_coordinate.json` writes. In standalone mode, the OAIS process is the writer. BASE output is withheld until the OAIS worker has acknowledged its new virtual state; when the next BASE prompt appears, the checkpoint is up-to-date for that command.

## Try it

1. Run `python3 main.py --start "3 0 0 0 0 0"` in connected mode.
2. Enter `oais navigator`, then `function k**2`, then `exit`.
3. Run `help` three times in BASE. The virtual counter should reach **12** (`3 + 3²`) with `k=3`, while BASE reaches **6**.
4. Open `oais sticky start`, run `help` once in BASE, then `oais sticky stop` and `oais sticky save test`. The note's `start_state` should capture `k=3`, not `k=4`; the virtual coordinate should advance to **19** (`3 + 4²`).
5. Inspect `virtual_coordinate.json` and `terminal_data/base/sticky_notes.json`. Try standalone mode with a separate `--data-dir` and confirm the source reads `oais`.

Run `python3 -m unittest discover -s tests -q` from the project root. The suite includes real PTY integration checks on POSIX/WSL when `pexpect` is available.
