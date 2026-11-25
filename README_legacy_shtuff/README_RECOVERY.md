# OAIS v0.1 source recovery (2026-11-23)

Reconstructed from original source-file copies and four incremental implementation ZIPs. This is a **separate recovery copy**, not a modification of the damaged local Git directory.

## Layout
- `main.py`: entrypoint.
- `oais/meta_terminal.py`: Linux/WSL PTY launcher and connected BASE/OAIS bridge.
- `oais/runtime.py`: compatibility shim.
- `oais/Terminal/Base_Terminal.py`: original BASE terminal source.
- `oais/Terminal/Oais_Terminal.py`: latest Sticky Note-integrated terminal.
- `oais/utils/counter.py`: original Counter utility source.
- `oais/utils/data_manager.py`, `virtual_counter.py`, `logical_address.py`: latest implementations.
- `oais/Commands/Navigator/*`: latest Navigator implementation (with Sticky Note recovery fix).
- `oais/Commands/StickyNote/*`: latest logical-address recording implementation.
- `tests/*`: latest regression tests.

## Source precedence
Original files: `main(1).py`, `meta_terminal(1).py`, `runtime(1).py`, `Base_Terminal(1).py`, `Oais_Terminal(1).py`, `counter(1).py`, `data_manager(1).py`, `StickyNote.py`, and `StickyNoteEngine(1).py`.
Patches applied, in sequence: Virtual Counter Phase 1 -> Four-Part Address Foundation -> Navigator Implementation -> Sticky Note Navigator Integration. Later patch files supersede earlier ones.

## Tests
From the project root:

```bash
python3 -m unittest discover -s tests -v
```

The restored current-stage suite passed **47/47 tests** in this recovery environment, including PTY integration (requires `pexpect` on Linux/WSL). Python modules compiled successfully.

Original Phase 1 tests are preserved in `tests/legacy/test_virtual_phase1.py` but deliberately excluded from ordinary discovery. Two Phase 1 assertions are incompatible with the current design: they expect three address fields rather than four, and a `recording_id` argument intentionally removed from the newer storage API. They do **not** indicate current-stage runtime failures.

## Run

```bash
python3 main.py
python3 main.py --mode base
python3 main.py --mode oais
python3 main.py --data-dir ./Data/prototype
```

## Caveats
- `coordinate.py` is not in available source copies/patches. It is **not imported** by the recovered runtime or current test suite. If your own external commands import `oais.utils.coordinate`, restore that additional utility from your own source history rather than assuming it was recovered.
- Any custom commands or files not present in supplied source/patches are not included.
- Original private coordinate data, old Sticky Notes and checkpoints were not reconstructed; those are user-specific data and should be restored independently if available.
- The `oais/Data/` runtime state and generated exports are Git-ignored. This ZIP intentionally does not include that state.
- Review `git status` and `.gitignore` before the first commit; do not stage personal coordinates or secrets.
