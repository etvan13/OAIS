# OAIS Coordinate Readback + Read-only Replay (v0.2 checkpoint)

This version extends the recovered OAIS v0.1 source.  It retains the existing
v4 Sticky Note coordinate storage system, four-part logical addresses, and
Navigator functions. `oais/utils/logical_address.py` was removed because the
current validator lives in `oais/utils/data_manager.py`.

## Start

```bash
python3 main.py
```

From the DEEP/Base Terminal, prefix OAIS commands with `oais`.

## Record a path

```text
oais navigator open cubic
oais sticky start
help
help
help
oais navigator turn
help
help
oais sticky stop
oais sticky save cubic_example
```

## Read coordinates and replay

```text
oais navigator trace cubic_example
oais replay cubic_example
```

Or step through a replay session:

```text
oais replay load cubic_example
oais replay next
oais replay next 2
oais replay status
oais replay all
oais replay reset
oais replay clear
```

- The path is reconstructed from the **stored coordinate records**, not the
  optional Sticky Note `.txt` export. In v4, the reader starts from the note's
  entry state, computes each four-part address, loads the matching logical
  command object at the real coordinate, then advances a private Navigator
  simulator using its recorded operation. Missing records or incorrect final
  coordinates cause an error.
- `navigator trace` is stateless and leaves a loaded Replay session intact.
- `replay load` validates the entire saved route, and the Replay session holds a
  read-only reconstruction in memory. For changes to the underlying stored
  data, load again to re-read and re-validate.
- Replay **never executes recorded terminal commands** and does not alter the
  live Counter, Navigator, Sticky Note recorder, or DataManager contents.
- The interface supports existing legacy note storage via `load_path()`.
- Text output includes the real coordinate, imaginary frame, function
  reference, and path universe before/after each event. Normal `.txt` exports
  remain optional and continue to be written on `sticky save`.

## Files added

- `oais/Commands/Replay/ReplayEngine.py` — stored path reader + playback cursor
- `oais/Commands/Replay/Replay.py` — terminal command adapter
- `oais/Commands/Replay/__init__.py`
- `tests/test_coordinate_replay.py`

## Files changed

- `oais/Terminal/Oais_Terminal.py` — attach Replay engine and command
- `oais/Commands/Navigator/Navigator.py` — `trace <note>`
- Removed `oais/utils/logical_address.py` (unused legacy three-part validator)

## Verification

```bash
python3 -m unittest discover -s tests -v
```

50 tests passed in the supplied build. Run the tests locally, perform one
manual record/save/trace/replay cycle, then make the first Git commit. Do not
copy your old damaged `.git` directory into this recovered source directory.

## Remaining future milestone

An executable replay that intentionally re-runs commands needs a separate
permissions and side-effect policy, transactional handling, and a sandbox or
simulated terminal state. This checkpoint provides coordinate reconstruction
and read-only navigation playback only.
