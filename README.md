# OAIS — Onboard AI System

**Experimental terminal architecture · Prototype v0.2**

OAIS (pronounced *wise*) is an experimental **Onboard AI System** intended to explore how a spacecraft-oriented intelligence could observe, navigate, record, and reason about its operating environment through a persistent, coordinate-addressed terminal.

The long-term vision is an onboard system that can assist with navigation, system monitoring, decision-making, resource management, and autonomous investigation. The current project is a **Python research prototype**, not a flight computer or spacecraft-qualified control system. Its working foundation is a navigable coordinate space in which commands, data, and traversal histories can be recorded and recovered.

> **Project principle:** The terminal owns the authoritative state. Navigation defines where operations occur; storage preserves what happened; replay reconstructs how a state was reached. Future AI layers should observe and propose actions without silently replacing or altering that state.

## What works today

Prototype v0.2 includes:

- A standalone OAIS terminal and a connected mode alongside the DEEP Base Terminal.
- Six-digit, least-significant-first base-60 coordinates with a separate universe counter.
- Virtual functional navigation, including turning and nested traversal poles.
- Four-part logical addresses that distinguish coordinate, navigation context, function, and path history.
- Coordinate-backed Sticky Note path recording and readback.
- Navigator tracing and deterministic **read-only** replay of saved traversal events.
- A `unittest` suite for the current implementation.

These features form a base for investigating persistent command histories and context-aware navigation. They do **not** yet constitute a functioning autonomous AI agent.

## Quick start

**Requirements:** Python 3 and a terminal. No third-party Python dependencies are specified for the supplied prototype. Linux/WSL is the primary environment for the connected subprocess/PTY bridge.

From the repository root:

```bash
python3 main.py
```

By default, this launches the Base Terminal with OAIS commands available through the `oais` prefix.

Other launch modes:

```bash
python3 main.py --mode oais                  # standalone OAIS terminal
python3 main.py --mode base                  # Base Terminal only
python3 main.py --start "0 0 0 0 0 0"       # choose initial coordinate
python3 main.py --data-dir ./Data/prototype  # use an isolated data directory
python3 main.py --help                       # show available launch options
```

The examples below assume the **connected Base Terminal** prompt. Commands may differ in standalone OAIS mode.

## Coordinate model

The Base Terminal represents position using six base-60 digits, each in the range `0–59`, ordered **least-significant first**:

```text
[1 0 0 0 0 0] = 1
[0 1 0 0 0 0] = 60
[0 0 1 0 0 0] = 3,600
```

For digits `c₁` through `c₆`, the displayed coordinate's integer index is:

```text
index = c₁ + 60*c₂ + 60²*c₃ + ... + 60⁵*c₆
```

A separate universe counter accommodates progression beyond the six-digit display range.

OAIS adds a logical address with four components:

```text
[real, imaginary, function, path_universe]
```

| Component | Role |
| --- | --- |
| `real` | The visible base-60 coordinate and associated universe state. |
| `imaginary` | Navigation context, such as active poles, local steps, and travel direction. |
| `function` | Reference to the rule governing the active traversal. |
| `path_universe` | Deterministic, history-dependent path identity, allowing different histories to visit the same real coordinate. |

These are **software-defined addressing and traversal structures**. The term *imaginary* describes the model's additional navigation context; it does not imply that the current software manipulates physical spacetime.

### Functional navigation

Instead of requiring every command to advance the virtual position by one, a Navigator pole can map a local step `k` to a displacement defined by a function `f(k)`:

```text
real_position = pole + f(k)
```

For a cubic pole at zero, three outward steps followed by a turn and three return steps produce:

```text
0 → 1 → 8 → 27 → 8 → 1 → 0
```

The function does not change on the return journey: the direction of the local step changes. Nested poles can temporarily suspend a parent navigation frame and resume it afterward.

The Base Terminal's displayed Counter and the Navigator's virtual real position are **distinct states**. Do not assume they always match.

## Try navigation, recording, and replay

Run the following from the **Base Terminal** prompt:

```text
oais navigator open cubic
oais sticky start
help
help
help
oais navigator turn
help
help
help
oais sticky stop
oais sticky save cubic_example

oais navigator trace cubic_example
oais replay load cubic_example
oais replay next 3
oais replay all
```

This records a six-event route and then reconstructs it from saved coordinate records. `replay next 3` displays the first three events; `replay all` displays the remaining events.

Additional replay commands:

```text
oais replay cubic_example       # load and display a saved route
oais replay load cubic_example  # validate/load a replay session
oais replay next                # show one event
oais replay next 2              # show two events
oais replay status              # report replay progress
oais replay all                 # show all remaining events
oais replay reset               # rewind the playback cursor
oais replay clear               # clear the playback session
```

You can also inspect a saved note using:

```text
oais sticky read cubic_example
```

Sticky Note `.txt` exports are convenient for inspection. The current v4 route reader uses **DataManager coordinate storage** as its source of truth and validates the reconstructed records. Missing or inconsistent records are errors; the text export is not the replay source.

**Important: Replay is currently read-only.** It displays recorded commands and traversal events but does not execute them, modify the live Counter or Navigator, or reproduce their original side effects.

## How the pieces fit together

```text
                     main.py
                        |
            +-----------+-----------+
            |                       |
     Base Terminal             OAIS Terminal
            |                       |
            +------ meta bridge ----+
                        |
                  OAIS commands
                        |
           +------------+------------+
           |            |            |
       Navigator    Sticky Note     Replay
           |            |            |
           +------------+------------+
                        |
                DataManager / storage
                        |
                Coordinate records
```

The diagram is a **conceptual overview**, not an assertion that every component has exactly this runtime call graph.

- **Navigator** determines virtual traversal and can reconstruct a route trace.
- **Sticky Note** captures and saves traversal events in coordinate-backed storage.
- **Replay** reads and validates saved events and presents them without executing them.
- **DataManager** validates logical addresses and coordinates data persistence.
- **Meta terminal / bridge** connects the OAIS commands to the Base Terminal while keeping a standalone mode available.

### Project layout

```text
main.py                          Entry point / launch-mode selection
oais/meta_terminal.py            Connected runtime / terminal bridge
oais/runtime.py                  Runtime compatibility entry
oais/Terminal/                   Base and OAIS terminal classes
oais/utils/counter.py            Base-60 counter
oais/utils/virtual_counter.py    Virtual coordinate progression
oais/utils/data_manager.py       Address validation / coordinate storage
oais/Commands/Navigator/         Functional navigation and tracing
oais/Commands/StickyNote/        Path capture and coordinate-backed notes
oais/Commands/Replay/            Read-only playback / command adapter
tests/                          Current automated tests
tests/legacy/                   Superseded early-architecture tests
```

Logical-address validation belongs in `DataManager`. An older three-part `logical_address.py` module is intentionally not part of the current design.

## Tests

From the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The supplied v0.2 checkpoint passed **50 current automated tests** in a recovery environment. This is a historical checkpoint, **not a claim that tests have been rerun on every subsequent revision**. Verify locally and complete at least one manual save → trace → replay cycle. Superseded Phase 1 tests remain in `tests/legacy/` and are not part of normal discovery.

## Data persistence and repository hygiene

Runtime records, checkpoints, and exports are generated under locations including:

```text
oais/Data/
oais/Exports/sticky_notes/
```

These paths are intended to remain outside version control via `.gitignore`. They may contain valuable local state. **Back them up before resetting, cleaning, replacing, or reorganizing the working directory.** Do not treat a Git clone as a backup of runtime data.

Before committing or pushing changes:

```bash
git status
git diff --cached
```

Review staged files for generated data, credentials, environment files, large artifacts, and other material not intended for publication. Verify that ignore rules are present in your actual checkout.

## Roadmap

### Next: strengthen the usable terminal foundation

1. **Verify the full integration path.** Run the current test suite and manually exercise the connected terminal, Navigator, Sticky Note capture, coordinate storage, tracing, and replay.
2. **Make Sticky Notes discoverable in DEEP.** Build a clear `sticky note` command or interface that lists available notes, reads them, and opens their saved paths; distinguish finding a note from recording one.
3. **Extend coordinate data operations.** Support straightforward inspection and addition of supported data values at specified coordinates, with validation and predictable persistence behavior.
4. **Define replay execution rules before enabling execution.** Keep read-only replay as the default; design explicit approval, command filtering, dry-run previews, state checks, and side-effect boundaries for any future executable replay.
5. **Add stronger recovery tests.** Test missing/corrupt records, interrupted saves, nested pole restoration, and compatibility between recorded route versions.

### Later: investigate intelligence and autonomy

- **Observation layer:** let a future AI interface inspect terminal state and coordinate histories without gaining implicit permission to mutate them.
- **Task orchestration:** represent goals as tasks with sub-tasks, event observations, queues, and resumable checkpoints.
- **Path simulation:** evaluate possible future command paths in a separate simulated state, then compare proposed routes against real terminal state before any approved execution.
- **Narrative interfaces:** connect saved command paths to graphical or manual traversal frontends while keeping backend coordinates authoritative.
- **Resource-aware operation:** investigate local models, bounded memory, event-triggered processing, and graceful degradation for constrained computing environments.

These are research directions and design intentions, **not implemented features**.

## Research perspective

OAIS investigates a distinction between **location** and **history**: two traversals can reach the same displayed coordinate while differing in the navigation rules, intermediate events, or stored path identity that led there. Preserving that context may support reconstruction, auditing, simulation, and future AI reasoning.

The broader project also explores discrete progression (`τ`), complex representations of traversal, and event-driven or *tick-based* operation. Those ideas motivate experiments, but the current repository should be evaluated by its actual code, tests, and observable terminal behavior. Connections to physical spacetime and spacecraft autonomy remain hypotheses, analogies, or future engineering work unless independently demonstrated.

## Documentation

Additional implementation details and recovery notes are described in the companion files (where present in the checkout):

- `README_COORDINATE_REPLAY.md`
- `README_NAVIGATOR_IMPLEMENTATION.md`
- `README_STICKYNOTE_NAVIGATOR_INTEGRATION.md`

**Current boundary:** OAIS provides a functional experimental terminal substrate. Reliable autonomous action, flight-critical safety, and spacecraft hardware integration remain outside this prototype.
