# OAIS v16 — coordinate-backed command histories

Replace the four source files in this archive at their existing relative paths.
No Data directory or imported conversations are included or overwritten. The
archive also includes the new and updated regression tests from the v15 test
suite; merge them with any newer local tests as appropriate.

## Storage and replay

New command Sticky Notes (`storage: functional_commands_v1`) retain the note ID,
title, starting and ending coordinate, block count, starting navigation context,
and final history digest. Overflow universes are stored when nonzero. No `plan`,
function catalog, intermediate coordinate list, or text export is written.
The coordinate block contains the command, incoming universe, optional source
and failure flag, and only the local routing information needed to replay that
event (operation, source delta, function on activation, explicit sync target,
etc.). The block's `counter_universe` remains the coordinate overflow namespace.

Replay seeds the history from the note ID and start address, reads exactly the
expected number of blocks at their calculated coordinates/history keys, and
applies mathematical operations in a fresh Navigator, not the live terminal.
The new command-v1 history convention hashes canonical local block content and
before/after projections. The BLAKE2b implementation is unchanged, but new
command-history keys after the first block differ from the v15 convention.
The endpoint and final digest must agree. Hidden OAIS and Meta commands still
participate in reconstruction; host/full is a presentation filter only.

## Conversations

Existing `functional_data_v1` notes, block hashes, and storage remain unchanged.
Metadata browsing/search and pagination do not read conversation payloads.
Only a selected note is reconstructed; currently its entire selected path is
loaded before its first displayed block. Incremental per-block playback is a
possible later optimization, not part of this update.

## Old notes and exports

Old v11-v15 notes containing `plan` are read through the existing legacy reader;
new notes never use that fallback. Do not remove `plan` alone from an old note:
old blocks lack sufficient local transition data and use a different hash
convention. Since the old command notes are tests, you can simply record fresh
notes. If desired, after backing up Data, remove the old command-note entries
from their terminal's sticky_notes_commands.json (or the legacy sticky_notes.json).
This does not automatically delete their now-unreferenced coordinate blocks.
Do not delete the whole coordinate_data directory or conversation collections.
After backing up any text-only historical notes, you may delete oais/Exports/
manually; the save command no longer creates it.

## Manual test

From a fresh BASE session at zero:

    oais sticky start
    oais function k**2
    help
    help
    oais virtual
    oais function k**3
    help
    backwards
    backwards
    oais sticky save v16_test
    oais replay v16_test
    oais replay full v16_test
    oais replay trace v16_test

Expected: 10 stored blocks, 5 visible host commands; virtual position 1 at end.
Trace includes both function changes and the inspection, and neither replay
view moves the live Navigator. The note contains no plan. Inspect
`oais/Data/terminal_data/base/sticky_notes_commands.json` for the note, and the
coordinate files for actual commands. The output should say coordinate-backed.

Regression tests:

    python -m unittest discover -s tests -p 'test_coordinate_history_v16.py' -v
    python -m unittest discover -s tests -p 'test_*.py' -q

PTY tests require a POSIX terminal (Linux/WSL) and pexpect.
