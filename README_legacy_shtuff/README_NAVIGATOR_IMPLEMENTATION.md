# OAIS Navigator — functional virtual navigation

**Implementation snapshot:** November 23, 2026  
**Scope:** Navigator and virtual Counter only. **Sticky Note v2 and Replay are NOT implemented in this patch.** The existing linked-pointer Sticky Note remains operational.

## Install

Back up your working repository, especially `oais/Data/coordinate_data/`, `oais/Data/current_coordinate.json`, and the Base terminal's data.

Unzip the archive **at your project root** (the folder containing `main.py`). The archive is built against the **four-part-address foundation** from our preceding implementation and contains the necessary `virtual_counter.py` as well. Only replace the listed code files; no stored data directories are shipped.

```
oais/Commands/Navigator/__init__.py       (NEW)
oais/Commands/Navigator/NavigatorEngine.py (NEW)
oais/Commands/Navigator/Navigator.py       (NEW)
oais/Terminal/Oais_Terminal.py             (UPDATED)
oais/utils/data_manager.py                (UPDATED)
oais/utils/virtual_counter.py             (FOUNDATION INCLUDED, unchanged)
tests/test_navigator.py                   (NEW)
tests/test_navigator_bridge.py            (NEW)
```

There are **no changes** to `Base_Terminal.py`, `meta_terminal.py`, `runtime.py`, `counter.py`, `main.py`, `StickyNote.py`, or `StickyNoteEngine.py`. An old `utils/logical_address.py` is unused by this version; make sure nothing else imports it before removing it.

### Quick test from the root

```bash
python -m unittest tests.test_navigator -v
python -m unittest tests.test_navigator_bridge -v
python main.py
```

The first test group needs only Python's standard library. The bridge tests use **pexpect** and Linux/WSL POSIX pseudo-terminals; they skip if not available. If your repository has a `tests/` directory already, ensure it is importable; alternatively run `python -m unittest discover -s tests -p 'test_navigator*.py' -v`.

The supplied project snapshot passed **35 current-stage tests** (16 Navigator tests, 2 Navigator PTY tests, 11 four-part foundation tests, 5 history-hash tests, and 1 original bridge test). Some older Phase 1 tests embedded in a previous development directory expect the obsolete three-part address and cannot be run against the newer schema without updating them.

## Core mental model

- Base Terminal Counter — authoritative host position and original movement rules.
- OAIS standalone Counter — an independent linear Counter in standalone mode.
- OAIS Virtual Counter — follows the authoritative linear Counter until a Navigator pole opens, then becomes FREE and follows its active mathematical projection.
- A virtual logical address is **`[real_coordinate, imaginary_stack, function_ref, path_universe]`**. Base-60 overflow `counter_universe` stays separate.
- Each outward step increments local imaginary depth by exactly 1. Real projection comes from the position-offset function `X = pole + f(k)`.
- `turn` from an outward leg immediately consumes the first return step (`k -= 1`); the apex is not duplicated. `turn` during an unfinished return opens a nested child pole and consumes its first outward step.
- The BLAKE2b-derived `path_universe` evolves from the previous path universe, before/after logical states and a movement operation. Returning to the same real coordinate does **not** reset path history.
- Function definitions are written **only at activation poles**, as version-3 `pole_function` objects. All other records may refer to `pi_<16hex>` aliases, but Navigator does not yet write command records.
- Ordinary BASE commands (including unknown, `backwards`, or `set_coord`) each advance the *active* virtual layer by one step in its current leg. Base-specific real movement does **not** determine the imaginary leg. Command return/turn is explicit through Navigator.
- In OAIS standalone mode, ordinary non-control commands are also eligible to advance the virtual layer. `navigator`, `virtual`, `sticky`, `replay`, `exit` controls, and META switches are excluded. Inputs inside a Sticky Note menu are excluded until Sticky Note v2 sets the recording policy.
- An excursion finishing at the root keeps the Virtual Counter FREE at its final pole, with the evolved path universe. The virtual coordinate will not snap to the host unless requested with `virtual sync` or `navigator sync`.

## Fixed function catalog

| CLI alias | Registered function | Real offset `f(k)` |
|---|---|---|
| `linear` | `linear_offset` | `k` |
| `backward` | `linear_offset` | `-k` |
| `cubic` | `cubic_offset` | `k**3` |
| `constant` | `constant_offset` | `0` |
| `wave` | `wave_offset` | `amplitude * (0,1,2,1,0,-1,-2,-1)[k % 8]` |

`linear` takes `slope=<integer>`, `cubic` takes `scale=<integer>`, and `wave` takes `amplitude=<integer>`. Scale/slope/amplitude are bounded integers. All functions satisfy `f(0)=0`. The wave example is a repeatable **sine-like lookup**, not continuous trigonometric sine. No arbitrary Python expressions or `eval` are allowed.

## Try the cubic example in connected mode

```text
$ python main.py --start "3 0 0 0 0 0"
[3 0 0 0 0 0] BASE > oais navigator open cubic
    Opened pole. ... virtual=3; imaginary k=0
[3 0 0 0 0 0] BASE > help
    BASE is now 4; virtual is 4 (k=1)
[4 0 0 0 0 0] BASE > greetings
    BASE is now 5; virtual is 11 (k=2)
[5 0 0 0 0 0] BASE > abc
    BASE is now 6; virtual is 30 (k=3)
[6 0 0 0 0 0] BASE > oais navigator turn
    virtual is 11 (k=2, toward); BASE is still 6
[6 0 0 0 0 0] BASE > help
    BASE is now 7; virtual is 4 (k=1, toward)
[7 0 0 0 0 0] BASE > help
    BASE is now 8; virtual is 3 (root closed)
[8 0 0 0 0 0] BASE > oais virtual status
    FREE at 3
[8 0 0 0 0 0] BASE > oais virtual sync
    FOLLOW at 8
```

The text after each command above is an **explanation** rather than verbatim terminal output. `oais navigator status` and `oais navigator inspect` show actual full logical states.

For explicit (nonautomatic) navigation:

```text
oais navigator open cubic
oais navigator pause
oais navigator away
oais navigator away
oais navigator away
oais navigator turn
oais navigator toward
oais navigator toward
```

Pause disables **automatic host event stepping** only; manual `away`, `turn`, `toward` remain available.

## Nested example

```text
oais navigator open backward
oais navigator pause
oais navigator away     # 3 -> 2
oais navigator away     # 2 -> 1
oais navigator turn     # 1 -> 2, parent k=1 toward
oais navigator child cubic scale=2  # new pole at 2, child k=1 -> 4
oais navigator away     # child k=2 -> 18
oais navigator turn     # child k=1 -> 4
oais navigator toward   # child closes at 2, parent resumes k=1 toward
oais navigator toward   # parent closes at 3
```

`navigator turn` again while already returning automatically opens a child using the parent's function. Or use `navigator child <function>` to select a different one.

## Status, synchronization, and checkpoints

```text
oais navigator help
oais navigator functions
oais navigator status
oais navigator inspect
oais navigator pause
oais navigator resume
oais navigator checkpoint
oais navigator restore
oais navigator sync
oais virtual status
oais virtual hold
oais virtual sync
```

- `virtual hold` freezes automatic movement, preserving the imaginary state. `navigator resume` re-enables it.
- `navigator sync` / `virtual sync` discard the active imaginary stack and reset the virtual projection to the host or standalone linear Counter. These commands are intentionally destructive of the **active traversal**; use a checkpoint first if you plan to restore it.
- `navigator checkpoint` explicitly writes `oais/Data/navigator_checkpoint.json`. This checkpoint contains *only* the active state and pole references, **not duplicate function definitions**. `navigator restore` reloads each active function from its original pole and validates the reconstructed real projection. This is not a Sticky Note history or full trajectory plan.
- Root poles store a fresh entry seed **only at their pole**. Do not share or overwrite existing coordinate data with this patch. The root seed makes the initial history state reproducible when we later build Sticky Note v2.
- Automatic progression does not write command events; **Sticky Note still uses its original coordinate-based, linked-pointer format**. Updating it is the next project phase.

## Important constraints / not yet implemented

1. **Sticky Note v2:** capturing pre-command logical addresses, recording compact traversal plans, saving logical command events, and replay/reconstruction are future work. The older Sticky Note save/read workflow is preserved.
2. **User-driven virtual jumps while a functional layer is active:** not yet supported. A Base Terminal `set_coord` only moves Base; it counts as one eligible virtual *functional* step while Navigator is active. Explicit virtual exceptional jumps will require an operation in the future traversal plan.
3. **Checkpoint is not historical verification:** it restores a consistent active state, but does not prove the complete sequence by traversing it. That belongs to Sticky Note/Replay.
4. **No cryptographic secrecy:** path universes are deterministic fingerprints, not authorization. The pole-only function rule prevents an arbitrary command block from containing its entire movement formula but is not encryption.
5. **One checkpoint file:** a later multi-note archive should not be implemented by accumulating per-command checkpoints. This is explicitly a single active navigation snapshot.
6. **Function versions are fixed at v1**. When adding custom functions later, registry validation and version compatibility must be preserved for old notes.

## Files you do not need to modify

The terminal currently delegates all navigation to `Navigator(self).run(arguments)`, using the existing command-dispatch class pattern. Meta Terminal already forwards Base observations through the event bridge, which is enough for eligible command stepping. No modification to Base's movement rules or the Meta Terminal process architecture was necessary.
