# OAIS terminal_data / function-selector patch

## What this patch does

- Adds generic `DataManager.load_terminal_data(terminal_id, collection)` and `save_terminal_data(...)` with atomic JSON writes and safe path components. Storage is `oais/Data/terminal_data/<terminal_id>/<collection>.json` (or under a custom `DataManager.base_dir`).
- New **logical** Sticky Note definitions live in the terminal's `sticky_notes.json`, not at the starting coordinate. `StickyNoteEngine.list_notes`, `get_note`, and `load_path` read new notes and retain coordinate-backed legacy fallback.
- The saved note includes a `functions` catalog, indexed in first-appearance order. Each entry contains the existing Navigator registry definition and the progression direction (`away`, `toward`, or `linear`). This is a **mode selector**, not a negated polynomial. The imaginary `k` is still maintained by Navigator.
- New v4 logical command records carry an integer `function` selector on the **first command and whenever the active mode changes**. Unchanged commands omit it. Existing navigation operations, addresses, and history remain in place for compatibility.
- `OaisTerminal(..., terminal_id='deep_base')` allows a caller to select the namespace; default is `oais_standalone`. `StickyNoteEngine` also accepts `terminal_id`.

## What this patch deliberately does NOT do

- It does not yet replace v4 command records with the compact v5 command format or change the BLAKE2b recurrence. In particular, ordinary linear events still use the existing history behavior.
- It does not make function selectors drive Navigator; Replay still uses the v4 navigation operations, while the selector and function catalog establish a stable format to build on.
- It does not move pole function definitions out of coordinate storage. These still exist for existing Navigator hydration and replay; moving them into the terminal's function catalog as the authoritative source requires a separate compatible change.
- It does not add a general expression parser for arbitrary sine/cubic formulas. Existing `wave_offset` is a deterministic integer lookup, not a floating-point sine.
- It does not encrypt terminal JSON or provide security isolation beyond separate files.
- `save_terminal_data` is an atomic **whole-collection replacement**, not a concurrent multi-process transaction. Multiple processes writing the same collection require a lock/transaction strategy.

## Example

```json
{
  "version": 1,
  "terminal_id": "deep_base",
  "notes": [
    {
      "id": "...",
      "title": "cubic",
      "functions": [
        {"definition": {"name": "cubic_offset", "version": 1, "params": {"scale": 1}}, "direction": "away"},
        {"definition": {"name": "cubic_offset", "version": 1, "params": {"scale": 1}}, "direction": "toward"}
      ],
      "initial_state": {"...": "existing v4 portable state"},
      "...": "other existing v4 replay fields"
    }
  ]
}
```

`function: 0` on the first command means use the first catalog entry; `function: 1` on the first command after a turn means switch to the second. The evaluator uses the same `f(k)` on return; it decrements `k`, rather than evaluating `-f(k)`.

## Tests

`python -m unittest discover -s tests -q`

53 tests passed on the patched project. One existing rollback test was updated to inject failure into terminal collection saving rather than the now-removed coordinate `sticky_note` write. New tests cover terminal namespace separation, path validation, note ownership, function catalog, and round-trip replay.
