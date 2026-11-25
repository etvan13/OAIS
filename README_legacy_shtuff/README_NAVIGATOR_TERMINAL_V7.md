# Navigator Terminal v7 — Implementation handoff

## Changes from imaginary-stack v6

1. The Navigator is now a full command subterminal (`Navigator>`). `navigator` without arguments enters the submenu, whereas `navigator open cubic` is still a one-command call. From connected BASE, `oais navigator` works through the Meta Terminal's PTY prompt recognizer; returning with `exit` restores BASE.
2. The canonical user-visible progression variable is **`k`** instead of `i`. Expressions, compact stack entries, and *new* Sticky Note function definitions all use `k`. The legacy syntax `i` remains a compatibility alias for reading old mathematical definitions; the engine normalizes it to `k`.
3. `functions`/`presets` lists the built-ins; `function <expression>` / `custom <expression>` creates a pole with a custom expression; `open <preset>` is still supported. Invalid expressions are rejected by the restricted AST evaluator and reported without modifying the Navigator.
4. OAIS's **normal Counter** is always independent from BASE, even when connected. Every OAIS input advances OAIS's own Counter. BASE's Counter is only updated by BASE. The virtual coordinate normally follows the host source (BASE while connected, OAIS when standalone).
5. Both OAIS normal and virtual counters are displayed together above the OAIS prompt. The Meta Terminal obtains a fresh *read-only* worker state when returning from BASE, so its visible coordinate display reflects BASE events that happened while OAIS was out of view.
6. A newly selected *root* function starts at the **current host-source coordinate**, even if an earlier functional excursion had ended at a different virtual pole. Nested function activations remain anchored to the current virtual position. After all layers pop, the next regular source command reestablishes linear following.
7. Saving from inside the Navigator menu records the actual `navigator <action>` operation when Sticky Note recording is active, without recording the outer submenu invocation later out of order. Synchronization / root-reanchor targets are included only when required for deterministic note writing.

## Counter behavior at a glance

| Input | BASE Counter | OAIS normal Counter | OAIS Virtual Counter |
| --- | --- | --- | --- |
| BASE `help`, no function | +1 | unchanged | mirror BASE |
| BASE `help`, cubic active | +1 | unchanged | `k += 1` (real `pole + k**3`) |
| OAIS `status` when connected | unchanged | +1 | no functional tick |
| `navigator function k**3` in OAIS | unchanged | +1 | opens at source, `k = 0` |
| OAIS `help` in standalone | no BASE | +1 | follows OAIS; if active, consumes 1 virtual tick |
| `navigator away` | unchanged | +1 if typed in OAIS | active `k += 1` |
| `navigator turn` | unchanged | +1 if typed in OAIS | active `k -= 1`; pop at zero |

All numeric coordinate operations retain the original six-digit least-significant-first base-60 representation and separate overflow universe. The imaginary coordinate list in historical four-part snapshots retains the legacy internal `step` key; it means `k` but is not rewritten to avoid breaking old stored logical addresses and v4 path records.

## Example connected test

Start `python3 main.py --start "3 0 0 0 0 0"`, then:

```text
oais navigator
functions
function k**3
stack
exit
help
help
oais navigator stack
```

The Navigator's virtual real coordinate will read `11 0 0 0 0 0`, with `k=2`. BASE will read `5 0 0 0 0 0`. OAIS's normal Counter advances with OAIS commands instead of copying BASE.

## Compatibility and exclusions

- Existing legacy v4 navigator/read-only Replay tests remain supported.
- New compact note **readback** and command replay remain the next phase, not part of v7.
- Legacy `i` expressions are accepted on input but emitted as `k` when saving new notes. For future Replay code, distinguish notes saved before this normalization if their path-history hashes were computed over the old `i` representation.
- All functions must yield exact bounded integer results; floating-point functions such as `sin` are intentionally not supported yet.
- PTY switching is designed for Linux/WSL; standalone OAIS works without it.
- `data_manager.py` did not require changes. `virtual_counter.py` retains its backwards-compatible four-part schema; its `imaginary` field means the stack of `k` layers.
