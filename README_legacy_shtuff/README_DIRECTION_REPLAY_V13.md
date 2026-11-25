# OAIS v13 — signed BASE ticks and read-only Sticky Note Replay

This patch builds on v12 without moving BASE into its own project or rewriting shared coordinate block storage.

## Navigation correction

The latest BASE command, **not** the previous function direction, determines each tick:

- Exactly `backwards` from BASE: `k -> k - 1`.
- Any other BASE command (including `help`, `forwards`, `next`, and invalid `forward`): `k -> k + 1`.
- `oais ...` commands issued from BASE are routed to the OAIS worker and **do not** consume a BASE tick. Opening a function creates a nested layer at its current virtual pole with `k=0`.
- The `direction` in `virtual_coordinate.json` records the **last tick direction** for that layer. It does not dictate future BASE movement.

Example, `f(k) = k**2` at pole 0:

| Input | BASE | k | Virtual |
|---|---:|---:|---:|
| Open `k**2` | 0 | 0 | 0 |
| `help` | 1 | 1 | 1 |
| `help` | 2 | 2 | 4 |
| `help` | 3 | 3 | 9 |
| `backwards` | 2 | 2 | 4 |
| `forward` (invalid) | 3 | 3 | 9 |
| `help` | 4 | 4 | 16 |

**At k=0:** an active layer stays alive, allowing `backwards` followed by a normal command to cancel even when that return lands on its pole. An extra `backwards` from a **nested child already at k=0** exits the empty child, consumes the step in its parent, and keeps the parent state. The root is bounded at `k=0`: another backward tick while already at the root pole leaves its position unchanged. Explicit historical Navigator controls (`turn`, `toward`, `away`) remain separately callable; they do not change the sign rule for later BASE commands.

### Sticky Note recording operations

Every new BASE event saved into a modern terminal-private Sticky Note plan now uses `auto_forward` or `auto_back` rather than the old direction-dependent `auto`. New notes therefore record the actual sign, including unknown commands. The private `start_state` and ordered `plan` are unchanged in shape; the shared coordinate `command_blocks` format is unchanged.

Older notes containing `auto` remain readable as recorded command lists. The legacy v4 reader still uses its previously stored navigation operations and coordinate objects; no automatic rewrite/migration of old notes occurs.

## Replay — command-list browser

Run the project in Linux/WSL (`python3 main.py`) or standalone (`python3 main.py --mode oais`). From BASE:

```text
[4 0 0 0 0 0] BASE > oais replay
REPLAY — SAVED STICKY NOTES
SAVED STICKY NOTES — base
1. test_10 [6c6d4bb7ded8] — 7 commands
Choose a number, title, or note ID to view its commands.
Replay> 1
REPLAY: test_10 [6c6d4bb7ded8] | 0/7 events | terminal-owned, read-only
1. [OAIS] navigator function k**3
2. [BASE] forwards
3. [BASE] forwards
4. [BASE] help
5. [BASE] backwards
6. [BASE] backwards
7. [BASE] backwards
[7/7]
Replay> exit
[4 0 0 0 0 0] BASE >
```

The sample title/ID are illustrative. Actual contents and ordering depend on the terminal's saved notes.

One-line alternatives (from BASE, prefix each with `oais `):

```
replay list                 # numbered list of current terminal's saved notes
replay 1                    # show all commands of note #1
replay test_10              # show note named test_10
replay <id>                 # show note by ID
replay load test_10         # load for stepwise browsing
replay next 2               # show next two steps
replay all                  # remaining commands
replay reset                # rewind cursor
replay status               # cursor / count
replay trace test_10        # full command list + start/end
replay clear                # unload viewed note
replay data 0 0 0 0 0 0    # existing read-only coordinate-data inspection
```

### Data ownership and no-execution guarantee

Modern note plans are loaded from `oais/Data/terminal_data/<terminal_id>/sticky_notes.json` via `StickyNoteEngine.get_note()`/`load_path()`. BASE-connected notes use terminal ID `base`; standalone OAIS notes use `oais_standalone`. The command list is read from the **private ordered plan**, not reconstructed by guessing an order among public coordinate blocks. The complete `start_state` is retained for future mathematical playback.

Replay **does not dispatch or execute** the recorded commands. Its menu and inspection commands also do not advance BASE, OAIS's normal Counter, active functions, or the live virtual checkpoint. It only changes the Replay browser's in-memory selected note/cursor. Other OAIS commands still follow the existing Counter rules.

Historical v4 coordinate-backed notes retain their established read-only step and trace views. Older v5-format notes **without** a terminal-private `plan` still require a separate legacy reader and report an explicit error; v11/v12 modern notes **with** a plan are supported without migration.

A *future* Replay phase could use `start_state` plus `plan` to calculate and display the virtual position after every event or drive a detached Navigator simulator. This patch intentionally implements the requested **select-a-note and list its commands** first, not automatic execution or movement of the current terminals.

## Changed areas

- `NavigatorEngine.advance_host_direction`: signed ticks; preserve the layer on arrival at `k=0`; nested unwind only on subsequent backward tick.
- `OaisTerminal.observe_event`: all ordinary BASE commands use `+1` except `backwards`; new note operations always record `auto_forward` or `auto_back`.
- `OaisTerminal.process_command`: standalone automatic function tick is positive; Replay input does not increment the Counter or save a new virtual checkpoint.
- `StickyNoteEngine.load_path`: v11/v12 terminal-private plans can now be read directly without coordinate scans.
- `ReplayEngine`: choose/list/read local notes with its proper terminal ID and format modern plans as a concise numbered command list; keep v4 readers.
- `Replay`: interactive selector with `Replay>` and one-line `list`, numeric, title and ID selection, plus existing step controls.
- `meta_terminal._prompt`: recognizes the nested Replay prompt.

## Tests

```bash
python3 -m unittest discover -s tests -q
```

The suite includes PTY tests of the BASE-to-OAIS switch, invalid `forward` ticks, the Replay menu, byte-for-byte virtual checkpoint stability during browsing, nested pole preservation, restart at `k=0`, and private-only note reads.

## Installing safely

The full and patch ZIPs exclude `oais/Data/`, `Base_Data/`, caches, and other runtime state. **Back up your current Data directory** before copying any files into your working project. Older saved command blocks and pole objects are not silently modified or removed. The BASE source still lives inside this project for now; separating BASE into its own independently installable directory remains a later architectural task.
