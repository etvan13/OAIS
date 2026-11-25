> **Current connection architecture:** [README_META_CONNECTIONS_V14.md](README_META_CONNECTIONS_V14.md) — Meta moved to `meta/`, BASE moved to `Base/`, and OAIS supports counterless observed hosts.

# OAIS — Onboard AI System

**Navigator + Replay v13 · signed BASE ticks · terminal-private read-only note browser**

OAIS is an experimental Python terminal. It has two independent notions of position: OAIS's own **normal Counter**, which advances with OAIS inputs, and a **Virtual Counter**, whose source is BASE when connected and OAIS when standalone. Activating a navigation function creates a pole at that source coordinate; subsequent eligible ticks follow `x = pole + f(k) - f(0)` instead of ordinary linear distance.

> The software is a research prototype, not spacecraft-qualified control software.

## Start

Run from this project directory:

```bash
python3 main.py                          # connected BASE + OAIS (Linux/WSL PTY)
python3 main.py --mode oais             # standalone OAIS, no BASE required
python3 main.py --start "3 0 0 0 0 0"    # connected run with BASE starting at 3
python3 main.py --data-dir ./test-data  # use isolated runtime storage
```

## Open the Navigator menu

From BASE:

```text
oais navigator
```

From OAIS:

```text
navigator
```

The prompt changes to `Navigator>`. The basic function-selector interface is intentionally small:

```text
functions              # list presets
function cubic         # choose a cubic function, k=0
function k**3          # choose a custom function
exit                   # leave the selector
```

Older advanced Navigator commands, including `child`, `stack`, `turn`, and `sync`, remain callable for compatibility and focused tests; they are not advertised by the minimal menu. A new `function` while a function is active **pushes a nested layer at k=0** and freezes the existing function's current k. See [README_FUNCTION_NESTING_V12.md](README_FUNCTION_NESTING_V12.md). BASE `forwards` and `backwards` control the active imaginary progression.

**You can also run any command directly without entering the menu**, including from BASE:

```text
oais navigator functions
oais navigator function '2*k**3 + 5'
oais navigator stack
oais function k**3             # shortcut; preserves existing k layers
```

Invalid functions display an error and do not change the navigation function. The evaluator allows a restricted set of **exact integer** expressions (integer constants, `k`, `+ - * ** // %`, parentheses, `abs`, `wave`); it does not execute arbitrary Python. Historical `i` expressions are accepted as a compatibility input and normalized to `k` in all new storage.

## The three coordinates while connected

The BASE Counter is unchanged by OAIS input. OAIS's normal Counter is unchanged by BASE input. BASE events advance the *virtual* function when one is active. OAIS displays both of its coordinates under each normal prompt, e.g.:

```text
OAIS Counter:    5 0 0 0 0 0 (U=0)
Virtual Counter: 11 0 0 0 0 0 (U=0, source=BASE, FREE) | f(k)=k**3 | k=2
OAIS >
```

If BASE starts at 3 and activates `k**3`, the first three ordinary BASE commands produce virtual coordinates **4, 11, 30** (`k=1,2,3`), while BASE advances **4, 5, 6**. OAIS's normal Counter advances on ordinary OAIS inputs (including actions within Navigator's menu); read-only Replay inspection is an exception.

When standalone, the same Virtual Counter follows OAIS's own normal Counter in linear mode; starting a function anchors it there. For BASE input, **only `backwards` decrements k**; every other BASE command, including invalid commands, adds one. The previous `direction` describes the last tick, not the next command. An active layer **remains available when it reaches `k=0`** so a following ordinary command can go forward again. An extra reverse tick from an empty nested layer unwinds to its parent; the root is bounded at zero. To discard the stack and follow the source again, use `virtual sync` or `navigator sync`. `virtual hold` freezes automatic navigation until an explicit sync or newly started function.

## Nested function state

Each function maintains its own independent `k` while suspended layers remain frozen. `navigator stack` prints a compact state:

```json
{
  "real": "34 0 0 0 0 0",
  "counter_universe": 0,
  "direction": 1,
  "functions": [
    {"f": "k**3", "k": 3, "direction": 1},
    {"f": "k**2", "k": 2, "direction": 1}
  ]
}
```

Opening/setting a new function **does not consume a virtual tick**; `away`, `turn`, `toward`, and eligible BASE events do. `turn` consumes its first reverse tick. The same function is evaluated with decreasing `k` on the way back.

## Sticky Notes and Replay boundary

`sticky start`, `sticky stop`, and `sticky save <title>` still save compact coordinate blocks. New saves store expressions using `k` and **always capture a portable `start_state`**, including the root pole, full nested function stack, ticks, directions, and BASE/OAIS source context. The private terminal-owned note also includes an ordered `plan` of commands, sources, and navigation operations. Public coordinate command blocks are unchanged and carry no complete note metadata or event numbers. **New functions no longer create `pole_function` objects in shared coordinate data.** The modern note saver obtains function expressions from in-memory events, not coordinate-object lookup. A notebook/Sticky Note starts recording without creating a pole or resetting the Navigator.

Live `virtual_coordinate.json` no longer embeds a full `navigation` snapshot or runtime path-universe. It persists the projected coordinate, source, one root pole, and the `k` stack, with only optional flags for a paused/held/free state. Restoring from this file recreates the mathematics but begins a deterministic new runtime history segment. Meta Terminal no longer writes a redundant `host_coordinate.json`.

**Replay v13** now reads the modern terminal-owned note `plan` and displays every saved command in order. From BASE, use `oais replay` to open the list and choose a note, or `oais replay list`, `oais replay 1`, and `oais replay <title>`. In OAIS, omit the `oais` prefix. `replay load <title>`, `replay next`, `replay all`, `replay reset`, and `replay trace <title>` support read-only step inspection. Replay does not execute commands or move any Counter. `sticky read <title>` can also display modern private plans. The historical **v4 read-only path reader remains available**; older compact notes lacking a private `plan` still need a separate legacy reader. Existing pole objects are left in place for old v4 paths, and `tools/prune_legacy_poles.py` remains optional. See [README_DIRECTION_REPLAY_V13.md](README_DIRECTION_REPLAY_V13.md) for examples and limitations.

## Tests

```bash
python3 -m unittest discover -s tests -q
```

Connected PTY tests use `pexpect` and a POSIX environment (Linux/WSL). They are skipped when those prerequisites are missing. Run a manual BASE/virtual synchronization test in your WSL environment before installing into your working project. Source history is documented in the accompanying `README_*` files; see `README_NAVIGATOR_TERMINAL_V7.md` for a focused implementation handoff.

## Important files

- `oais/Commands/Navigator/Navigator.py` — interactive menu and one-line commands
- `oais/Commands/Navigator/NavigatorEngine.py` — function evaluator, `k` progression, nested stack
- `oais/Commands/StickyNote/StickyNoteEngine.py` — portable `k` function metadata and note saving
- `oais/Commands/StickyNote/StickyNote.py` — Sticky Note display
- `oais/Commands/Replay/Replay.py` — interactive read-only note chooser
- `oais/Commands/Replay/ReplayEngine.py` — private-plan reader and stepping cursor
- `oais/Terminal/Oais_Terminal.py` — OAIS real/virtual displays, connected/standalone source policy
- `oais/meta_terminal.py` — PTY subterminal prompts and current-coordinate display upon switching
- `oais/utils/virtual_counter.py` — independent four-part virtual coordinate and history utilities
- `oais/utils/data_manager.py` — generic coordinate and terminal-owned JSON storage

For the compact v11 state, self-contained note plan, old-file migration, and examples, see `README_NAVIGATION_STORAGE_V11.md`. For the earlier source policy, see `README_NAVIGATION_CONTEXT_V10.md`.

Keep your existing `oais/Data/` separately when installing an update. Data files and previously saved notes are not part of the code patch.

For the v13 tick correction and Replay commands, see `README_DIRECTION_REPLAY_V13.md`.
