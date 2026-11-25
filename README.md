# OAIS — Onboard AI System

**A modular framework for observing, navigating, preserving, and reusing computational experiences.**

OAIS (pronounced *wise*) is an experimental architecture for onboard intelligence. Its long-term objective is to support autonomous systems, particularly spacecraft, operating under constraints on computation, energy, memory, communication, and human intervention.

Rather than beginning with a large AI model and building an environment around it, OAIS begins with the environment itself: a system that can observe interactions, establish where they occur, preserve their histories, and revisit useful sequences of actions. Intelligence can then operate over that structure instead of having to reconstruct the entire context from scratch at every interaction.

The present Python implementation explores how interactions with a program can be represented as traversals through a mathematical coordinate space. Commands, data, navigation functions, and ordered histories can be associated with positions and subsequently inspected or reorganized. The framework is not limited to spacecraft, artificial intelligence, or any particular terminal.

The current implementation supports standalone operation, connection to independent terminals, mathematical navigation, coordinate-based data storage, Sticky Note recording, and read-only Replay. This README describes the v14 architecture.

> OAIS is a research prototype, not spacecraft-qualified control software. Autonomous execution, general OS-level observation, and integrated AI reasoning are future work.

## Why OAIS exists

An intelligent system should be able to make use of what has already been learned. If a procedure has been discovered, performed, and verified, it should not necessarily require another generative inference to reproduce it. Likewise, information should remain useful beyond the conversation or program session in which it originated.

OAIS investigates an alternative to treating computational experience as a disposable sequence of inputs and outputs. It separates the information itself, the location at which it is accessible, the history through which it was reached, and the procedure that may be used to reach or reproduce it again.

The central question is whether a small, structured runtime can allow intelligence to allocate more of its limited resources to unfamiliar problems while relying on preserved, validated experience for familiar ones. Any reduction in inference cost, memory consumption, or energy use must ultimately be established through measurement.

In a future spacecraft setting, this could support mission observations, diagnostic histories, navigation assistance, resource-management procedures, and crew decision-making. Independent safety mechanisms and human oversight remain essential; the ability to remember a procedure is not evidence that executing it is safe.

## Architectural principles

- **Observation precedes intervention.** OAIS can be connected to a program without that program adopting OAIS's coordinate system. Observing an event does not authorize changing the observed system.
- **The host owns its authoritative state.** OAIS's mathematical representation is not a replacement for the actual state of an external program or spacecraft.
- **Position is not history.** Two traversals may occupy the same real coordinate while retaining distinct histories. Returning to a coordinate does not undo a command or its side effects.
- **Navigation is distinct from storage.** The Navigator determines traversal; DataManager preserves information; Sticky Notes establish ordered relationships; Replay inspects those relationships.
- **Preserve before interpreting.** A future AI layer should be able to interpret and summarize recorded experience without silently replacing the underlying evidence.
- **Intelligence is a layer, not a prerequisite.** The core should remain useful without a language model, network connection, or continuous inference.
- **Interfaces are replaceable.** A terminal, graphical cockpit, or future agent interface should observe and invoke backend behavior rather than own the mathematical state.

## Core architecture

| Component           | Responsibility                                                                                     |
| ------------------- | -------------------------------------------------------------------------------------------------- |
| **Meta Terminal**   | Selects connections, manages sessions, routes input, and forwards observations to OAIS.            |
| **OAIS Terminal**   | Provides the command interface and manages OAIS's independent Counter and observed source context. |
| **Virtual Counter** | Represents progression through an independent mathematical coordinate space.                       |
| **Navigator**       | Defines functional trajectories, nested layers, and forward/reverse traversal.                     |
| **Sticky Note**     | Preserves ordered paths and their navigation context.                                              |
| **Replay**          | Retrieves and inspects saved paths without executing them.                                         |
| **DataManager**     | Stores coordinate-associated information and terminal-owned records.                               |
| **BASE**            | An independent example terminal with native coordinates and data storage.                          |

Meta is not another interactive command prompt. It is organized like a command-based terminal, with connection classes exposing `run()` methods. Meta owns no Counter or DataManager; the connected program and OAIS retain their own responsibilities.

```text
main.py
   |
Meta Terminal --- selected connection --- Observed program
   |                                           |
   +---------- normalized observations <------+
   |
OAIS Terminal
   |-- Counter / Virtual Counter
   |-- Navigator
   |-- Sticky Note / Replay
   +-- DataManager
```

OAIS can also operate without an external program. A connected program does not need to understand OAIS or implement its coordinate system.

The components form a basic observation-to-memory pipeline: Meta receives observations, OAIS interprets progression, the Navigator supplies the coordinate context, and Sticky Notes preserve selected sequences for Replay. This is the foundation on which future reasoning and action layers can be built.

## Getting started

Run from the project root with Python 3. Connected PTY sessions currently require a POSIX environment such as Linux or WSL. Install `pexpect` if you want to run the PTY integration tests.

```bash
python3 main.py                             # BASE connected to OAIS
python3 main.py --connection counterless    # Example host without coordinates
python3 main.py --connection standalone     # OAIS independently
python3 main.py --mode oais                  # Legacy standalone alias
python3 main.py --mode base                  # BASE independently
python3 main.py --start "3 0 0 0 0 0"        # Starting BASE coordinate
python3 main.py --data-dir ./test-data/oais --base-data-dir ./test-data/base
```

BASE may also be launched directly using `python3 Base/Base_Terminal.py`.

In a connected session, `oais` switches to OAIS, `return` resumes the host, and `oais <command>` invokes an OAIS command directly from the host. Host `exit` ends the connected session. OAIS `exit` at its top-level prompt returns to the host.

## Coordinate space

OAIS uses six base-60 digits, each ranging from 0 to 59. The first digit is the least significant:

```text
0  0 0 0 0 0
1  0 0 0 0 0
...
59 0 0 0 0 0
0  1 0 0 0 0
```

A coordinate `c0 c1 c2 c3 c4 c5` corresponds to the integer `c0 + 60*c1 + ... + 60^5*c5`. Each coordinate universe contains 46,656,000,000 real positions. Signed universe tracking supports progression across the boundaries of this range.

OAIS distinguishes three positions:

- **Source position:** the native position of a coordinate-aware host, or a synthetic position generated by OAIS from observed commands when a host has no Counter. In standalone mode, the source is OAIS's own Counter.
- **OAIS Counter:** the independent position associated with OAIS's own inputs. Host commands do not advance it.
- **Virtual Counter:** the position projected through the current navigation context. It can follow the source linearly, follow a function, or be held.

The broader logical address includes real position, imaginary/function-layer state, function reference, and universe context. Counter universes track numeric overflow; path universes distinguish traversal histories. They are not interchangeable.

The base-60 representation is an addressing convention, not a requirement to allocate all 46.656 billion positions in memory. It provides a large logical domain in which records can be associated with selected locations.

### Progression and observation

OAIS distinguishes a discrete interaction tick from physical elapsed time. A tick advances or updates the relevant computational state according to the active connection and navigation policy. The same number of observed interactions can therefore produce different projected paths.

This connects to the broader OAIS research on discrete progression, imaginary coordinates, and conditional alignment. These ideas motivate separating the progression parameter from observable position. The software implementation is an integer-coordinate model; it does not establish a physical correspondence with relativistic time, Minkowski geometry, or faster-than-light travel.

A future event-driven intelligence layer could respond selectively to observations, anomalies, or accumulated evidence rather than invoke a model at every tick. Physical timing, periodic monitoring, and safety deadlines would still need independent mechanisms.

## Mathematical navigation

A navigation function establishes a pole at the current virtual position (the source position when following linearly). Subsequent eligible ticks evaluate

```text
x(k) = pole + f(k) - f(0)
```

The local integer `k` measures progression within the function, independently of the projected real position. OAIS uses imaginary layers as a computational representation of functional traversal; this is not a claim of physical spacetime traversal.

For example, starting at position 3 with `f(k) = k**3`:

| k | Source position (forward traversal) | Virtual position |
| - | ----------------------------------- | ---------------- |
| 0 | 3                                   | 3                |
| 1 | 4                                   | 4                |
| 2 | 5                                   | 11               |
| 3 | 6                                   | 30               |

Reversing the function decreases `k` and evaluates the same expression, returning through 11, 4, and 3.

### Navigator commands

From a connected host:

```text
oais navigator
oais navigator functions
oais function k**2
oais navigator status
oais navigator stack
oais navigator function '2*k**3 + 5'
oais virtual hold
oais virtual sync
```

From OAIS, omit the `oais` prefix. Inside `Navigator>`, use `functions`, `function cubic`, `function k**3`, and `exit` without a prefix.

Functions use a restricted exact-integer evaluator supporting integer constants, `k`, `+ - * ** // %`, parentheses, `abs`, and `wave`. Arbitrary Python execution is not supported. Legacy expressions using `i` are normalized to `k`. Invalid expressions leave the current function unchanged.

### Nested functions and direction

Opening another function pushes a new layer at `k=0`, anchored at the current virtual position, without consuming a virtual tick. The parent layer remains frozen until resumed.

For BASE, `backwards` decrements the active layer's `k`; other ordinary commands, including invalid commands, advance it. Direction describes the most recent tick rather than the direction of the next input. Explicit Navigator operations such as `away`, `toward`, and `turn` also control progression; `turn` consumes its first reverse tick.

For example, a quadratic path with a cubic child at position 9 can traverse:

```text
0 -> 1 -> 4 -> 9 -> 10 -> 9 -> 4 -> 1 -> 0
```

A layer remains active at `k=0`. An additional reverse tick from an empty child unwinds to its parent; the root is bounded at zero. `virtual sync` or `navigator sync` discards the stack and returns to source-following mode. `virtual hold` freezes automatic navigation until sync or a new function.

Advanced commands such as `child`, `stack`, `turn`, and `sync` remain available even when not advertised in the minimal Navigator menu.

## Sticky Notes

A Sticky Note is an ordered record of a traversal, not simply a text message attached to a coordinate. It preserves the commands and navigation context needed to inspect a path, including paths that revisit the same real position.

```text
oais sticky start
oais function k**2
help
help
help
backwards
oais sticky save example_path
```

Recording does not reset navigation or create a pole. `sticky stop` stops recording, and `sticky save <title>` commits a temporary path to storage. Modern notes preserve a portable `start_state`, function definitions, ordered command plan, sources, and navigation operations. A text export is also generated under `oais/Exports/sticky_notes/`.

The current recording policy preserves host commands and relevant OAIS navigation operations according to recording scope; it does not yet preserve every informational OAIS command.

A planned extension is to record complete interaction histories while marking each event with a functional-path flag. Functional events would be displayed by default; users could reveal or reclassify other events without losing their original order. Display visibility and permission to execute an event must remain separate, especially for commands that save notes or control Replay.

### History and storage

Modern Sticky Notes use terminal-owned ordered plans alongside compact command blocks stored at coordinates. The public blocks do not contain the complete note plan or event numbering.

BLAKE2b-derived path universes distinguish different recorded histories, including repeated visits to the same coordinate. Each recorded event can produce a new history identity even when the real position does not change. This is a history-addressing mechanism, not a guarantee of confidentiality or encryption.

Function definitions are obtained from recorded in-memory events; new saves do not create legacy `pole_function` objects in shared coordinate data.

### From command paths to narrative paths (proposed)

The same abstraction can extend beyond executable commands. A conversation, scientific observation log, or collection of documents can be represented as addressable blocks. A Sticky Note could then preserve the ordered selection of blocks that forms a particular narrative or line of reasoning.

```text
Stored blocks:     A    B    C    D    E

Original path:    A -> B -> C -> D -> E
Alternative path: A -> C -> E
Research path:    D -> B -> D -> C
```text

These are different ordered paths through shared information, not necessarily separate copies of the information. Repeated visits remain meaningful. The original conversation order should remain recoverable even when new paths are created.

A future narrative builder could allow manual exploration, selection, and rearrangement of existing blocks into new Sticky Notes. Random or semantic navigation could help discover candidate relationships, but the chosen order and its provenance should be explicitly saved. This is a proposed extension, not a claim that the current command recorder already implements conversational memory.

## Replay

Replay currently provides **read-only inspection** of saved Sticky Notes. It does not re-execute commands or advance any Counter. Modern Replay reads the terminal-owned ordered plan, so repeated coordinates and zero-movement events remain in sequence.

From a connected host:

```
oais replay list
oais replay example_path
oais replay trace example_path
oais replay load example_path
oais replay next 3
oais replay all
oais replay reset
```text

`oais replay` opens the interactive note browser. Inside its `Replay>` prompt, omit both prefixes:

```
list
load example_path
next 3
status
all
reset
trace example_path
exit
```text

A title or note number displays that note's complete saved command sequence. `sticky read <title>` can also inspect modern plans, and `replay data <six digits>` reads coordinate-associated messages.

Executable Replay is a future objective. Reusing an existing procedure without another AI inference is one motivation for developing it, but safe execution will require explicit controls for side effects, external program state, and errors.

### From replay to reusable procedures (proposed)

Read-only inspection, simulation, and execution should be separate operations. A stored path is evidence of a previous traversal, not proof that its commands will have the same effects under changed conditions.

A future executable procedure should establish its required initial state, check permissions and relevant preconditions, execute only authorized events, observe outcomes, and stop or request intervention when assumptions fail. Commands that merely inspect a note, change recording scope, or manage Replay should not automatically become executable steps.

An AI model could help discover a procedure or adapt it to a new context, while a deterministic runtime handles approved execution and verification where possible. This is the intended route toward reducing repeated inference rather than eliminating reasoning altogether.

## Connecting other programs

The `meta/Connections/` directory contains the currently supported connection methods:

- `Base.py`: connects OAIS to the independent BASE terminal and forwards native coordinates.
- `Counterless.py`: connects OAIS to a simple demonstration host without coordinates or a DataManager.
- `Standalone.py`: launches OAIS without an external host.

A minimal counterless observation can look like:

```
{"type": "command", "source": "myprogram", "value": "help", "success": True}
```text

OAIS generates a source position from observed commands when native coordinates are absent. With `k**2` active, three observed commands from a fresh zero position advance the synthetic source to 3 and the Virtual Counter to 9. Connections may optionally supply signed `movement` or native coordinates.

To try this:

```
python3 main.py --connection counterless
```text

```
oais sticky start
oais function k**2
ping
help
echo testing
oais navigator status
oais sticky save counterless_test
oais replay trace counterless_test
```text

To add a connection, create a class in `meta/Connections/`, implement its `run()` method and the relevant host/event/prompt methods using an existing connection as a template, and register it in `MetaTerminal.__init__`:

```
self.register("myprogram", "meta.Connections.MyProgram:MyProgramConnection")
```text

Then select it using `python3 main.py --connection myprogram`. Connections are loaded only when selected. Observed-host connections currently use `self.meta.run_connected(self)` and supply a recognizable completion boundary. Meta forwards completed command events and waits for OAIS acknowledgement before displaying the next host prompt.

The counterless example is not a general shell or OS input monitor. OAIS currently observes inputs routed through its connection; arbitrary-process and keyboard-level observation remain future work.

## Project structure

```
main.py
meta/
    meta_terminal.py
    Connections/
        Base.py
        Counterless.py
        Standalone.py
Base/
    Base_Terminal.py
    utils/
    Base_Data/                 # Runtime data
oais/
    Terminal/Oais_Terminal.py
    Commands/
        Navigator/
        StickyNote/
        Replay/
    utils/
        counter.py
        virtual_counter.py
        data_manager.py
    Data/                      # Runtime data
    Exports/                   # Generated note exports
    runtime.py                 # Compatibility import
tests/
README_legacy_shtuff/          # Historical documentation
README.md
```text

The command interfaces and their corresponding engines are separated into files within each command directory. `Oais_Terminal.py` manages command dispatch and observation; `NavigatorEngine.py`, `StickyNoteEngine.py`, and `ReplayEngine.py` contain the respective core behavior.

## Persistence and migration

OAIS data belongs in `oais/Data/`; BASE data belongs in `Base/Base_Data/`. These directories are independent. Preserve runtime data separately when upgrading the source code.

Live `virtual_coordinate.json` retains the projected position, source, root pole, and nested `k` stack, with optional mode flags. Restoration reconstructs the navigation mathematics but begins a new deterministic runtime history segment. Counterless sessions can resume their synthetic source position and function context with the same data directory. Switching source types can rebase the live context. Saved notes are scoped by terminal ID under `terminal_data/`.

Older installations used `oais/Base_Data/`. The BASE connection attempts to migrate that directory if the new destination contains no data; it does not overwrite or merge populated destinations. Explicit `--base-data-dir` disables this migration. `oais/runtime.py` remains as a compatibility import for Meta.

Older v4 read-only paths and compact notes without modern private plans have separate legacy-reader requirements. Existing legacy pole objects are not automatically removed. If retained, `tools/prune_legacy_poles.py` is an optional migration utility, not a runtime dependency.

## Testing

```
python3 -m unittest discover -s tests -q
```text

The v14 distribution passed 114 tests before local cleanup or modifications. PTY integration tests require `pexpect` and POSIX support and are skipped where those prerequisites are unavailable. Manual testing should verify connection switching, independent Counters, nested navigation, root-boundary behavior, Sticky Note persistence, same-coordinate events, read-only Replay, and counterless observation. Terminal scrolling and command-history handling remain areas for improvement.

## Longer-term intelligence architecture (research direction)

OAIS is intended to develop from an observer and navigator into a system capable of using its own recorded experience. The following is a conceptual architecture, not a description of implemented modules:

```text
Observed programs / sensors / crew input
                  |
                  v
          Connection / observation
                  |
                  v
       Coordinate state + event records
                  |
                  v
       Sticky Notes / indexed memory
                  |
                  v
       Retrieval / reasoning / task state
                  |
                  v
       Proposed or simulated procedure
                  |
                  v
       Authorization / validation gate
                  |
                  v
       Controlled action + verification
                  |
                  +----> new observations
```

Three related research directions follow from this structure:

**Navigable memory.** Preserve raw blocks and their relationships, then build rolling windows and hierarchical checkpoints over long histories. Recent information can remain detailed while older information is summarized at progressively broader resolutions. Summaries should refer back to recoverable source records rather than become the only surviving representation.

**Task-directed observation.** A future task layer could maintain objectives, relevant observations, unresolved questions, and completion criteria. An anomaly may contribute to an existing task without requiring immediate action or a new inference. This would allow OAIS to accumulate evidence across interactions and prioritize work when resources permit.

**Counterfactual navigation.** A future reasoning layer could construct candidate paths in isolated state, compare their predicted outcomes, and retrieve related procedures before proposing real actions. Such paths must remain distinguishable from observed history. Simulated execution must not mutate the authoritative host state, and successful simulation alone must not authorize a real command.

Together these directions suggest a system in which memory, reasoning, and action share a common representation of experience, while retaining distinct responsibilities and safety boundaries.

## Development direction

OAIS is being developed incrementally. The next milestones should build on the current connection and recording architecture rather than replace it.

| Stage | Objective | Evidence of completion |
| --- | --- | --- |
| 1 | Stabilize v14 and connect DEEP | Existing behavior preserved; connection, counters, recording, and inspection tested end to end. |
| 2 | Generalize Sticky Notes | Complete interaction histories with configurable functional-path views; an intuitive note browser that does not own backend state. |
| 3 | Conversation and narrative paths | Existing conversation blocks can be preserved in their original order and selected into alternative saved paths without duplicating content unnecessarily. |
| 4 | Safe executable Replay | Authorized procedures execute with preconditions, observable outcomes, and explicit failure handling. |
| 5 | AI-assisted memory and navigation | Retrieval, candidate-path construction, and isolated simulation work without changing the live host state. |
| 6 | Broader observation and task management | Additional program connections and eventually OS-level observation support persistent task-directed collection. |
| 7 | Resource and reliability evaluation | Measure inference reuse, latency, memory, storage overhead, energy where practical, and recovery behavior against appropriate baselines. |

Stages are suggested priorities, not fixed release commitments. Conversation-path work and DEEP integration can proceed independently when their interfaces are stable. None of the proposed capabilities should be treated as implemented simply because it appears in this roadmap.

The immediate goal is to make the smallest working integration reliable before expanding the interface or refactoring core engines. Preserve standalone operation and test each new connection against the existing behavior.

## Repository and runtime data

Keep source code, tests, and documentation under version control. Treat generated coordinate records, terminal-owned note plans, and exports as potentially sensitive runtime data. Inspect `.gitignore` and staged files before publishing, and maintain separate backups of any local data that must survive upgrades. A path identifier or a terminal-private storage convention is not a substitute for access control or encryption.

## Historical documentation

Earlier implementation notes and version-specific design decisions are retained in [README_legacy_shtuff/](README_legacy_shtuff/).

- [Meta connections and independent BASE (v14)](README_legacy_shtuff/README_META_CONNECTIONS_V14.md)
- [Signed progression and read-only Replay (v13)](README_legacy_shtuff/README_DIRECTION_REPLAY_V13.md)
- [Nested functions (v12)](README_legacy_shtuff/README_FUNCTION_NESTING_V12.md)
- [Navigation storage and portable plans (v11)](README_legacy_shtuff/README_NAVIGATION_STORAGE_V11.md)
- [Source context (v10)](README_legacy_shtuff/README_NAVIGATION_CONTEXT_V10.md)
- [Four-part address foundation](README_legacy_shtuff/README_FOUR_PART_FOUNDATION.md)

The main README describes the current architecture and overall purpose of OAIS; historical documents may describe superseded interfaces or storage formats.