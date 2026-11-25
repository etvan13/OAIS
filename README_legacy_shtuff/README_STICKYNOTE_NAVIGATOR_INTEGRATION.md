# OAIS — Sticky Note + Navigator Integration (v4)

This patch builds on the **already-installed OAIS Navigator implementation**. It is an **overlay**: do not delete the `oais/Data/` directory or replace the other terminal modules. It does not modify `meta_terminal.py`, `Base_Terminal.py`, `main.py`, `counter.py`, or the standalone runtime.

## Install

From your DEEP/OAIS project root, back up the five files listed below. Unzip `OAIS_StickyNote_Navigator_Integration.zip` **into that root**, preserving its `oais/...` paths. Do not unzip as a new `oais/oais/...` folder.

Changed files:

- `oais/Commands/StickyNote/StickyNoteEngine.py`
- `oais/Commands/StickyNote/StickyNote.py`
- `oais/Terminal/Oais_Terminal.py`
- `oais/utils/data_manager.py`
- `oais/Commands/Navigator/NavigatorEngine.py` (FOLLOW/no-layer checkpoint restoration edge-case fix)

The ZIP also contains the new integration tests and this README.

**Dependency:** The Navigator patch already installed must provide `oais/Commands/Navigator/Navigator.py`, `oais/utils/virtual_counter.py`, and existing Meta Terminal infrastructure. The current ZIP does not repackage those unchanged files.

## Start and use

```bash
python3 main.py
```

Start a new cubic excursion, then begin a Sticky Note. Record both ordinary Base commands and Navigator operations:

```text
oais navigator open cubic
oais sticky start
help
help
help
oais navigator turn
help
help
oais sticky path
oais sticky stop
oais sticky save cubic_example
oais sticky read cubic_example
```

Expected virtual positions **before** each saved event: `0, 1, 8, 27, 8, 1`. Afterward: `1, 8, 27, 8, 1, 0`. A direct `oais sticky start` normally selects BASE-only scope, but necessary Navigator movement commands (like `turn`) are still recorded to allow correct reconstruction. In the full interactive Sticky Note menu, use `start`, `path`, `stop`, `save <title>`, `read <title>`, `list`, and `exit`.

Another test for nested layers:

```text
oais virtual sync
oais navigator open cubic
oais sticky start
help
help
help
oais navigator turn
oais navigator child backward
help
help
oais navigator turn
help
help
help
oais sticky stop
oais sticky save nested_example
oais sticky read nested_example
```

**Note:** `child backward` advances one imaginary step immediately when the child pole is created (`8 -> 7`). The parent remains suspended at `k=2,toward`. The virtual sequence through this example is `0 -> 1 -> 8 -> 27 -> 8 -> 7 -> 6 -> 5 -> 6 -> 7 -> 8 -> 1`.

For a zero-real-movement test, open `constant` instead of `cubic`: ordinary commands all occupy the same **real** coordinate, but imaginary state and path universe evolve. A paused function can also hold the entire four-part address fixed for several commands; distinct event keys prevent overwrites.

Restart the program and run `oais sticky read cubic_example` to verify the path can be reconstructed without any active Navigator state.

## Logical storage behavior

Full virtual address:

```text
[real, imaginary, function, path_universe]
```

`counter_universe` (base-60 overflow) is a separate field, not the fourth component. Commands are stored at the virtual **pre-command** real coordinate. The `logical_command` record contains the four-part pre-address, the command text, a movement operation (e.g. `auto`, `turn`, `child`), and minimal information needed for special host-follow/sync transitions. **It has no next-coordinate pointer, no command-path array, no function definition, and no per-event recording_id field.** No result/output text is stored in coordinate objects.

An opaque `pi_<hex>` reference identifies a function activated at its pole. The actual function definition (and a root navigator seed) is stored only as a `pole_function` object at the corresponding pole. Each child pole stores its own definition at its own opening coordinate.

The `sticky_note` entry object is stored at the note's **first virtual real coordinate**. It contains the compact initial Navigator frame references, an independent random route lookup seed, an event count, and endpoint verification information. It does not contain a list of commands or coordinates. For each step, the reader calculates an event ID from the note seed + step number + calculated four-part address, loads the matching command at the calculated real coordinate, then applies its stored Navigator operation **without executing the terminal command**. The note seed lives only at its starting coordinate and is not repeated in event records.

This lookup seed resolves multiple Sticky Notes starting in identical logical states, and repeated or stationary addresses. It is not an extra universe and does not replace the evolving Navigator `path_universe` value. It is **not** an encryption key or an access-control mechanism: readers with filesystem access can still enumerate objects and pole definitions.

Legacy coordinate-linked Sticky Notes and text-only `.txt` exports remain readable. New Terminal-driven Sticky Notes use v4 logical format; standalone `StickyNoteEngine` instances without a Navigator provider retain their earlier save format by default. `replay` is still a future command; `sticky read` reconstructs/display the path but does not execute it.

## Testing

From the project root:

```bash
python3 -m unittest tests.test_sticky_logical_v4 -v
python3 -m unittest tests.test_sticky_logical_bridge -v
python3 -m unittest tests.test_navigator -v
python3 -m unittest tests.test_navigator_bridge -v
```

The tests cover cubic and nested routes, a note begun **mid-child**, no-real-movement routes, paused commands at an identical full address, duplicate starting points in separate notes, failed Base commands, Meta transitions, rollover into the next base-60 Counter universe, pre-pole recording, manual pause/away/turn/toward/sync, rollback after a failed save, missing-event detection, and recovery from a fresh PTY process.

The **old Phase 1 test file** `test_virtual_phase1.py` describes the superseded *three-part* logical address and `recording_id` API; its old assertions are intentionally incompatible with the four-part foundation. Use the tests above and the four-part foundation tests instead. Do not remove existing data simply to make obsolete test expectations pass.

## Intentional limits

- `navigator restore` is disallowed while a Sticky Note is active **or has an unsaved temporary path**, because reloading a checkpoint mid-recording would introduce an unrecorded branch. Save or clear the note first.
- A sudden process crash in the middle of saving could leave orphan coordinate events before the note entry is written. Normal Python exceptions roll back partial event writes and retain the temporary path.
- This implementation does not execute stored commands on read, encrypt command content, or support arbitrary externally injected virtual projections outside the Navigator event stream.
- An optional future secret passed into the Navigator's history hash would need to be provided to the route reader as well; this patch follows the current default unkeyed BLAKE2b setup.
