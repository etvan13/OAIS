# OAIS virtual counter + logical command storage — Phase 1

This is a **drop-in version of the nine Python files supplied** plus two new
utility modules and automated tests. It does not contain the user's existing
`oais/Data/coordinate_data` contents: **do not replace or delete that directory**.

## New modules

- `oais/utils/virtual_counter.py`: virtual position, FOLLOW/FREE mode, host
  observation, sync, explicit projection hook, snapshots, and exact signed
  universe/base-60 conversion.
- `oais/utils/logical_address.py`: validates the proposed three-part logical
  address `[real_coordinate, imaginary_state, function]` without interpreting
  imaginary movement.

## Updated existing modules

- `oais/Terminal/Oais_Terminal.py`: holds a separate `virtual_counter` object,
  mirrors DEEP observations only in FOLLOW mode, and exposes `virtual` commands.
- `oais/utils/data_manager.py`: adds `save_logical_command`,
  `load_logical_commands`, and the shared validation contract; all existing
  storage methods and the nested coordinate directory structure remain.

**No modifications** were needed to `main.py`, `runtime.py`,
`meta_terminal.py`, `Base_Terminal.py`, `counter.py`, `StickyNote.py`, or
`StickyNoteEngine.py` in this phase.

## Why FOLLOW and FREE?

- FOLLOW: each observed host position updates virtual position; active imaginary
  metadata is cleared, since there is no Navigator yet.
- FREE: observed host movements still update the host snapshot and host Counter,
  but no longer update the virtual projection.
- `sync`: copy the latest authoritative linear counter to the virtual counter,
  clear imaginary metadata, return to FOLLOW.

OAIS standalone Counter remains independent. No movement instructions are
interpreted as imaginary steps yet; only Navigator will do that.

## Terminal commands to try

Run the same `python main.py` as before (Linux/WSL, connected mode).

```text
[0 0 0 0 0 0] BASE > oais virtual status
Virtual [FOLLOW]: 0 0 0 0 0 0 ...
[0 0 0 0 0 0] BASE > help
[1 0 0 0 0 0] BASE > oais virtual status
Virtual [FOLLOW]: 1 0 0 0 0 0 ...
[1 0 0 0 0 0] BASE > oais virtual hold
Virtual [FREE]: 1 0 0 0 0 0 ...
[1 0 0 0 0 0] BASE > greetings
[2 0 0 0 0 0] BASE > oais virtual status
Virtual [FREE]: 1 0 0 0 0 0 ...
[2 0 0 0 0 0] BASE > oais virtual sync
Virtual [FOLLOW]: 2 0 0 0 0 0 ...
```

For direct code use, Navigator will later call:

```python
terminal.virtual_counter.set_projection(
    "11 0 0 0 0 0", universe=0, imaginary=2,
    function="cubic_offset", direction="away"
)
address = terminal.virtual_counter.logical_address()
# address == ["11 0 0 0 0 0", 2, "cubic_offset"]
```

The virtual counter does not compute cubic functions yet. It stores a projected
position supplied by a later Navigator.

## DataManager usage

```python
from oais.utils.data_manager import DataManager
manager = DataManager()

# Pass the PRE-COMMAND virtual address, NOT the post-command position.
record = manager.save_logical_command(
    ["11 0 0 0 0 0", 2, "cubic_offset"],
    "help", universe=0, direction="away", recording_id="N001"
)

commands = manager.load_logical_commands(
    "11 0 0 0 0 0", universe=0, recording_id="N001"
)
```

This saves a `logical_command` object with `schema_version: 2` at the **real
projection** in the preexisting nested coordinate tree. The record contains
its own immutable event `id`, `address` triple, universe, direction,
`recording_id`, and `occurrence`. A second command at the same projected real
coordinate does not overwrite the first. In future, `imaginary_state` can be a
list of nested activation frames, and `function` can be a versioned descriptor.

**Important:** the v2 method is an available storage API only. The current
Sticky Note **still saves and reads v1 linked-command records**. Do not feed
v2 records to the old reader yet. Navigator and Sticky Note integration are
separate future phases.

## Install

1. Back up your repository, especially `oais/Data/` and `Base_Data/`.
2. Copy these **four files** into the corresponding project paths:
   - `oais/utils/virtual_counter.py` (new)
   - `oais/utils/logical_address.py` (new)
   - `oais/utils/data_manager.py` (updated)
   - `oais/Terminal/Oais_Terminal.py` (updated)
3. The ZIP contains unchanged input modules so the package can be tested in
   isolation. You do **not** need to overwrite unchanged files in your project.
4. Optionally copy the `tests/` folder to your project root.
5. Run: `python -m unittest discover -s tests -v` from the project root.

Tests cover legacy Sticky Note behavior, base-60 wrapping, virtual state modes,
logical-event collisions and reload, and a real Meta Terminal PTY session.
The PTY test requires `pexpect` on Linux/WSL and skips where unavailable.
