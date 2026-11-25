# OAIS Navigator v8 — function selection cleanup

## Changes

- Opening OAIS from BASE now shows **one** fresh OAIS/Virtual Counter header. The Meta Terminal no longer pastes the old OAIS PTY transcript before the header.
- Startup message no longer repeats the coordinate header; the OAIS prompt displays it once.
- `navigator` now opens a function-selector interface with a short instruction rather than a large stack/status banner. `help` exposes just `functions`, `function`, and `exit`. Existing developer/legacy commands are still available internally for compatibility, but they are no longer part of the primary menu.
- `function cubic` and `function k**3` open a function anchored at the current virtual source coordinate. Invalid expressions are rejected.
- In connected mode, BASE `backwards` now consumes a **reverse imaginary tick**; BASE `forwards` consumes a forward imaginary tick. Other eligible BASE commands still advance automatically along the active leg. Reversing to `k=0` closes the active layer; the next BASE command returns to following BASE normally. `backwards`/`forwards` are captured as deterministic events for Sticky Note v5 writes.
- OAIS' real Counter continues to advance independently of BASE's Counter. Virtual Counter remains BASE-sourced in connected mode and OAIS-sourced standalone.
- Replay for v5 remains deferred; old v4 reading is unchanged.

## Usage

Run `python3 main.py`, then from BASE:

```
oais navigator
functions
function cubic
exit
help
help
backwards
forwards
oais
```

Example with root pole at 3:

```
BASE help     -> k=1, virtual 4
BASE help     -> k=2, virtual 11
BASE backwards -> k=1, virtual 4
BASE forwards  -> k=2, virtual 11
```

`oais navigator function k**3` also works as a one-line command from BASE.

## Test

Run `python3 -m unittest discover -s tests -q` from the project root. Verified 77 tests passing on the patched source.
