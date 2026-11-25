# OAIS Imaginary Function Stack — v6 Navigation + Sticky Note Storage

**Scope:** Navigation and compact Sticky Note saving only. Replay of v6 notes is intentionally **not implemented**; old v4 and legacy readers remain. No changes to DEEP source code.

## Install

Use the complete `OAIS_imaginary_stack_v6_full.zip` project or merge the paths from `OAIS_imaginary_stack_v6_changed_files.zip` into your existing OAIS checkout. Back up your existing `Data/` directory before testing; this package does not include any of your personal coordinate data. Run from the extracted project directory:

```bash
python3 -m unittest discover -s tests -q
python3 main.py
```

## Navigation behavior

The base Counter always keeps its own **linear**, six-digit base-60 coordinate. The OAIS virtual coordinate is a separate projection. Calling `navigator open cubic` or `navigator open i**3` activates an imaginary function and establishes the virtual position as the new pole. One eligible host command advances the **current** function's `i` by one, irrespective of the host's real displacement. The integer absolute coordinate is converted back into base-60 plus Counter overflow.

For independent nested function layers:

```
x_virtual = root_pole + Σ (g_j(i_j) - g_j(0))
```

The `g_j(0)` subtraction guarantees activation never teleports the virtual coordinate, even for `g(i) = i**2 + 5`. Parent `i` values freeze while a child runs. The top layer consumes every functional tick. `turn` changes the top layer to returning and takes its first reverse tick; subsequent host commands or `toward` reduce its `i`. The layer pops **on** the tick that reaches zero, restoring its parent. Turning immediately on an empty nested layer removes it and applies the reverse tick to its parent, with no wasted tick. Turning at an untraveled root (`i=0`) is rejected.

When there are no layers, the VirtualCounter follows the observed host in FOLLOW mode. If all layers unwind while the virtual state is FREE, subsequent ordinary ticks advance **linearly from that last virtual position**, not by snapping to the host. Use `navigator sync` to explicitly snap to the host.

**Commands:**

```
navigator open cubic             # root pole at current virtual position, i=0
navigator open '2*i + 1'        # another, independent layer, i=0
navigator child i**2            # equivalent independent nested push
navigator away                  # one outward tick
navigator turn                  # first reverse tick
navigator toward                # one further reverse tick
navigator stack                 # compact live JSON with f, i, direction
navigator status                # full position plus layer summary
navigator checkpoint            # save Navigator state only when requested
navigator restore               # restore pole references and frozen stack
navigator sync                  # abandon layers and follow host again
```

`navigator turn` while already returning retains the existing legacy behavior of opening an outward child of the same function with one immediate tick. To select a *new* function mid-return without consuming a tick, use `navigator child <function>` or `navigator open <function>`.

The supported expression evaluator uses a **restricted AST**, never Python `eval()`. Supported integer arithmetic: `i`, integer literals, `+`, `-`, `*`, `**` (small nonnegative integer powers), `//`, `%`, parentheses, `abs()`. The old wave preset is stored as a portable integer expression `2-abs((i+2)%8-4)`. Unsupported expressions such as `sin(i)`, true division, imports, attributes and arbitrary functions are refused pending a defined deterministic numerical policy. Depth, expression complexity and output magnitude are bounded.

## Minimal evolving coordinate example

From base pole 3, advance cubic to `i=3` -> real 30, open quadratic and advance to `i=2` -> real 34:

```json
{
  "real": "34 0 0 0 0 0",
  "counter_universe": 0,
  "direction": 1,
  "functions": [
    {"f": "i**3", "i": 3, "direction": 1},
    {"f": "i**2", "i": 2, "direction": 1}
  ]
}
```

This is returned by `navigator stack`, from `NavigatorEngine.compact_state()`. The internal version-1 Navigator `snapshot()` deliberately retains additional pole references and `k`/`step` aliases so checkpoint restore and historical v4 readback continue to work. The stack exists independently of Sticky Note recording.

## Compact Sticky Note format

The terminal-owned collection is `Data/terminal_data/<terminal_id>/sticky_notes.json`. The OAIS observation bridge uses `base`, while direct standalone OAIS uses `oais_standalone` by default. The collection is `version: 2` to permit older name-based v5 notes and new expression-based v6 notes in one file. Every new v6 note is recognized by function entries with **`f`**, instead of the old registry `name`.

A simple linear note stores only:

```json
{
  "id": "<note-id>",
  "title": "example",
  "start": "0 0 0 0 0 0",
  "end": "3 0 0 0 0 0",
  "functions": [{"f": "i", "direction": 1}, {"f": "i", "direction": -1}],
  "blocks": 5
}
```

An ordinary note beginning at cubic imaginary position `i=2` can store its first function as `{"f":"i**3","direction":1,"i":2}`. The original pole is then derivable from `start - (g(2)-g(0))`. If recording begins inside **multiple nested layers**, or the first saved event replaces the existing active function, the optional `origin` stores just the initial layers as `[ {"f", "i", "direction"}, ... ]`, without opaque pole references or full Navigator snapshots. Optional `transitions` preserve explicit `open`, `push`, `turn`, `toward`, `pause`, `sync`, etc. and their event indices. Optional `start_universe`/`end_universe` keep **base-60 Counter overflow** distinct from path history. An `auto:false` field retains an initially paused functional layer.

New coordinate blocks remain minimal; only the first command and function changes carry `function`:

```json
{"command":"backwards","universe":"<32-hex-path-history>","function":1}
```

Other fields are sparse: `step` for values other than 1 (including stationary zero), `failed`, non-base `source`, and nonzero Counter overflow. The coordinate file's containing key is the **real** coordinate.

### Path-history determinism

Each note begins with the existing BLAKE2b seed derived from `(start, note ID, Counter universe)`. On every event, its 128-bit universe evolves from its previous key, event text/index/op, and the **portable** pre/post position signature:

```
[real, [{f, i, direction}, ...], active_f]
```

Random Navigator `pi_...` activation IDs are **not** included in the saved note-path hash. This is necessary so later Replay can reconstruct keys using the note's function expressions, the initial imaginary state, and the command transitions. The separate live Navigator `path_universe` retains its existing meaning and does not have to match the note-local history key.

## Current compatibility boundaries

- Existing v4, linked-path and other historical Sticky Note readers still work.
- New compact notes intentionally raise `NotImplementedError` from `StickyNoteEngine.load_path()`; `sticky read` / `navigator trace` await the future Replay update.
- The historical `navigator child` UI has **changed** to establish a pole at `i=0` without moving. Its older engine API `NavigatorEngine.open_child()` and older v4 navigation op `child` remain available for compatibility.
- The base-terminal observation bridge is wired to `terminal_id='base'`; no DEEP terminal files are changed.
- `DataManager` needs no changes: it already contains `save_command_block`, `load_command_block`, `save_terminal_data`, `load_terminal_data`, and historical pole storage. Pole definitions still exist at their activation coordinates for **Navigator checkpoint/legacy compatibility**; the note also includes text math for portable route recovery. This duplication is intentional across different responsibilities, not per command.
- The base Counter implementation is unchanged. `virtual_counter.py` keeps its established four-part logical address and adds clarification of the per-layer imaginary count; Navigator owns the mathematical stack.
- A `turn`/`toward` chooses reverse traversal inside the **Navigator**. A generic host command named `backwards` does not implicitly change an already-active functional layer's leg; ordinary *linear* backward moves are recorded with direction `-1`. This can be refined later when integrating host commands as navigation controls.
- Storage uses atomic JSON replacement, but multiple concurrent writers to the **same** JSON collection are not transactionally serialized. Testing a single OAIS recording writer is supported.

## Files changed (from the eight supplied)

- `oais/Commands/Navigator/NavigatorEngine.py` — AST math, independent layer push, initial/return rules, compact evolving stack and free-mode linear tick
- `oais/Commands/Navigator/Navigator.py` — new `navigator stack`, open/child semantics, quoted math expressions, labels
- `oais/Commands/StickyNote/StickyNoteEngine.py` — portable `f` catalog, optional initial `i` or `origin`, sparse transitions, portable BLAKE2b history and legacy compatibility
- `oais/Commands/StickyNote/StickyNote.py` — read/help formatting updates
- `oais/Terminal/Oais_Terminal.py` — correct navigation event classification, function pushes, continued linear ticking, terminal ID support
- `oais/meta_terminal.py` — base-terminal recording namespace `base`
- `oais/utils/virtual_counter.py` — comment clarifies the per-function imaginary count; no behavioral changes required
- `oais/utils/data_manager.py` — unchanged; existing storage APIs suffice

## Testing

`python3 -m unittest discover -s tests -q` — **67 tests passed** in the supplied complete project on Python 3.13, including existing v4 readers, PTY bridge integration and new nested imaginary / compact v6 / failure-rollback tests. Tests whose old expectations assumed `navigator child` consumes an immediate tick or that FREE mode never advances linearly were updated to the new specified behavior.
