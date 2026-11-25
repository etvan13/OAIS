# OAIS v14 — Meta connections and independent BASE

This is the v13 Navigator / Sticky Note / read-only Replay code, with its connection architecture separated. **The mathematical engines and the shared coordinate-block format are unchanged.**

## Start

On Linux or WSL, run from the project root:

```bash
python main.py                             # Meta: BASE + OAIS, same default workflow
python main.py --connection counterless    # Meta: example host without a Counter
python main.py --connection standalone     # OAIS alone, no Meta PTY session
python main.py --mode oais                 # Legacy alias for OAIS alone
python main.py --mode base                 # Legacy alias for BASE alone
python main.py --start '59 0 0 0 0 0'      # Starting BASE coordinate
python main.py --data-dir /path/to/oais    # Isolate OAIS data
python main.py --base-data-dir /path/to/base # Isolate BASE data
```

BASE can also run on its own without importing OAIS or Meta:

```bash
python Base/Base_Terminal.py
```

The default connected workflow is unchanged: commands go to BASE; `oais` switches to the OAIS view, `return` goes back, and `oais function k**2`, `oais sticky start`, `oais replay` work directly from BASE. OAIS's `exit` is handled by Meta as a return; BASE's `exit` closes the combined session. For `--connection counterless`, the host prompt is `DEMO >` and accepts `help`, `ping`, `echo TEXT`, and `exit`.

## Structure

```text
main.py                         Chooses connection via CLI
meta/
  meta_terminal.py              Registry, PTY helper, command routing, observation/ACK
  Connections/
    Base.py                     BASE connection: native host coordinates
    Standalone.py               OAIS without an external host
    Counterless.py              Test connection: no Counter, no DataManager
Base/
  Base_Terminal.py              Host commands
  utils/counter.py              BASE-owned Counter
  utils/data_manager.py         BASE-owned data model (copied for compatibility)
  Base_Data/                     BASE's own data, created at runtime
oais/
  Terminal/Oais_Terminal.py     OAIS command dispatcher, observation and Navigator bridge
  Commands/                     Navigator, Sticky Note, Replay (unchanged)
  utils/                        OAIS-owned Counter, virtual math, storage
  Data/                         OAIS data, created at runtime
  runtime.py                    Compatibility import for MetaTerminal
```

`oais/meta_terminal.py` and `oais/Terminal/Base_Terminal.py` have been **moved**. `oais/runtime.py` is the small compatibility import that now points to `meta.meta_terminal`.

BASE's independent DataManager is currently a local copy of the old DataManager, deliberately retaining its JSON layout and methods. It can be narrowed down after the separation is proven, without changing storage during this migration.

## Add a connection

1. Create `meta/Connections/MyProgram.py` with a class such as `MyProgramConnection`.
2. Implement `run()` to call `self.meta.run_connected(self)` (for observed hosts). Add a class `name`, `terminal_id`, `has_coordinates`, `prompt_pattern`, and `display_name`, plus methods `create_host()`, `prompt()`, `resume_prompt()`, `event()`, and `initial_event()` matching `Base.py` or `Counterless.py`.
3. In `MetaTerminal.__init__`, register it: `self.register("myprogram", "meta.Connections.MyProgram:MyProgramConnection")`. Connections are loaded only when selected, so standalone OAIS does not need to import BASE.
4. Launch: `python main.py --connection myprogram`.

The connection only translates the host's *completed commands* into normalized observation events. Meta delivers them to the OAIS worker and waits for its acknowledgement. OAIS owns the virtual navigation, Sticky Note save, and replay. Meta does not own a Counter or DataManager.

Example event from a host without a native Counter:

```python
{"type": "command", "source": "myprogram", "value": "help", "success": True}
```

OAIS synthesizes a six-digit base-60 **source position** for each observed command: 0 -> 1 -> 2 ... . The OAIS independent Counter and the mathematical Virtual Counter remain separate. With `k**2` open, three host events advance the source to 3 but project the Virtual Counter to 9. With a native coordinate host like BASE, the native position remains authoritative. A connection can optionally report signed integer `movement`; no coordinate is required.

A source name persists in `virtual_coordinate.json`. If a counterless host restarts with the same OAIS data directory, its synthetic source position and functional navigation context resume. Separate terminals may use separate OAIS data directories, or a source change will rebase the live context as before. Notes are stored by `terminal_id` under OAIS's `terminal_data/`.

## Existing BASE data

Older versions stored BASE data in `oais/Base_Data/`. The BASE connection attempts a **one-time move** to `Base/Base_Data/` if the new destination does not contain data. If both locations contain files it does not overwrite or merge them; a warning is issued and the operator must reconcile the two directories. OAIS's `oais/Data/` remains separate and is not moved. When passing `--base-data-dir`, no automatic migration is performed.

## Important scope and limitations

- This release only observes commands issued **through Meta's connection**. It does not intercept external programs' keystrokes, terminal emulators, or OS input. Those mechanisms can be implemented as new connection methods later.
- The counterless example is a deliberately simple Python host, **not a real OS shell integration**.
- BASE event semantics and existing nested-function navigation are retained. Event ordering is still protected by the Meta-to-OAIS acknowledgement before the host prompt is displayed.
- Private Sticky Note plans, BLAKE2b path universes, and compact public command blocks are unchanged. Replay remains **read-only**.
- Connection plugins currently run in Python subprocesses behind PTYs. Each must provide a recognizable prompt or completion boundary; generic arbitrary-process observation is future work.
- Meta does not expose a separate interactive `META >` prompt. Its connection commands are Python classes selected by `main.py`.

## Tests

From the project root:

```bash
python -m unittest discover -s tests -p 'test_*.py' -q
```

The v13 suite (108 cases including the universe-chain audit) is retained, plus v14 checks for independent BASE, dispatcher ownership, counterless function progression, recording, read-only Replay, and PTY restart persistence.
