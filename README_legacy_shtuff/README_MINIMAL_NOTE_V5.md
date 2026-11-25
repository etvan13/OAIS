# Minimal Sticky Note v5 metadata patch

## Main changes

- `oais/meta_terminal.py`: the base-terminal observation bridge now explicitly opens `OaisTerminal(..., terminal_id="base")`, writing base recordings to `oais/Data/terminal_data/base/sticky_notes.json`. Standalone OAIS retains its separate `oais_standalone` default.
- `oais/Commands/StickyNote/StickyNoteEngine.py`: newly saved v5 note records now store `id`, `title`, `start`, `end`, `functions`, and `blocks`. They omit duplicated full logical addresses, route seed, redundant hash version, directions, scope, stored terminal ID, event type and initial state for simple linear recordings.
- Function catalog entries store flat `name` and `direction`, with optional `params` and non-default function `version`; default `linear_offset` slope `1` is implicit.
- Optional `start_universe` and `end_universe` retain real Counter overflow when nonzero; **do not confuse these with the deterministic BLAKE2b path-history universe**.
- Optional `transitions` are present only for explicit Navigator operations such as turn/open/child/sync.
- Optional `origin` retains the existing Navigator snapshot when recording begins mid-function or from nondefault Navigator state; this is required for possible future lossless reconstruction. Ordinary linear recordings starting at the default state omit it.
- Hash initialization is already derived from starting real coordinate, Counter universe and stable note ID, so the `path_seed` string was redundant. The coordinate command blocks are unchanged.
- `load_path` still explicitly reports v5 Replay as unimplemented for both the former verbose v5 record and the new minimal v5 record. Existing v4 and legacy reading remains intact.

## Example linear note

```json
{
  "notes": [{
    "id": "e235737f95b8",
    "title": "test",
    "start": "0 0 0 0 0 0",
    "end": "4 0 0 0 0 0",
    "functions": [
      {"name": "linear_offset", "direction": "forward"},
      {"name": "linear_offset", "direction": "backward"}
    ],
    "blocks": 6
  }],
  "version": 1
}
```

## Constraints before Replay

The storage changes do not make v5 replay functional. Future Replay must regenerate identical history keys using note ID and start position, adopt the compact function catalog, honor the `step` stored on command blocks, and apply any sparse `transitions` / `origin`. Historical verbose v5 notes remain listable, but migration to the compact note schema should be done separately after a reader exists.

## Tests

`cd OAIS_compact_coordinate_v5 && python -m unittest discover -s tests -q` — 56 passed.
