# OAIS four-part logical address — foundation patch (before Navigator)

## Status

This patch revises the **previous Phase 1 virtual-counter patch**. It assumes Phase 1 is already installed. It does **not** implement the historical `DefaultPath` path-universe algorithm, functional movement, Navigator, or Sticky Note v3 writing. It **does include** pure, versioned BLAKE2b seed/evolution helpers inspired by the historic history-dependent universe concept, with no automatic movement or event capture.

## Exact address contract

```python
[real_coordinate, imaginary_state, function_key_or_descriptor, path_universe]
```

- **real_coordinate**: six base-60 digits, least-significant digit first.
- **imaginary_state**: nonnegative integer depth or a JSON-serializable ordered layer stack.
- **function**: in-memory function reference; **saved functional command events use only an opaque `pi_<16 hex digits>` activation label**, not a readable function name or formula. The actual named/versioned function definition is stored once at its opening pole.
- **path_universe**: nonnegative integer *history-derived* traversal state. Pure `seed_path_universe` and `evolve_path_universe` helpers calculate it from a starting seed and an ordered transition. The future Navigator decides when to apply each update; the VirtualCounter does not automatically advance it.
- **counter_universe**: **separate** integer for the existing Counter's six-digit base-60 overflow/underflow. It is stored beside the address on saved logical events, not as a fifth element of the array.
- **direction**: `linear`, `away`, or `toward`, stored with events and virtual snapshots (not as a fifth array element).

`path_universe` is **not** a note/recording ID. Version-3 logical-command records have no `recording_id`, `next` pointer, event-order field, or movement formula. Every event still has a random object ID to avoid overwriting two independent records. A collision at the same *complete* logical address and direction is detected during unique resolution; the code never guesses which event is correct.

## Changed files (relative to project root)

- `oais/utils/virtual_counter.py` — updated virtual state and four-part `logical_address()`, with FOLLOW/FREE/sync behavior; adds pure BLAKE2b history seed/evolution helpers (128-bit integer values).
- `oais/utils/data_manager.py` — four-part address validation is now local to DataManager; `save_pole_function` / `load_pole_function` register and read the movement rule **only at a pole**; `save_logical_command` produces schema version 3 without repeating the rule; `load_logical_commands` and `resolve_logical_command` support exact matching.
- `oais/Terminal/Oais_Terminal.py` — virtual status displays `counter_universe` and `path_universe` separately.

The old `oais/utils/logical_address.py` is **no longer imported** by these files. After checking that no other local code imports it, you may delete it.

Do not replace your actual `oais/Data/coordinate_data/` directory, `Base_Data/`, or existing saved data. **No Data directories are included in this ZIP.**

## Pole-local function rule

A functional layer is defined at the pole where it opens. The actual named/versioned definition, such as `cubic_offset` with `scale=1`, is stored as one `pole_function` object **at that pole only**. Commands elsewhere carry a neutral, automatically-generated alias like `pi_c57d35bc0a817e62` in the **third element** of their four-part address.

The alias identifies an activation, not a real pole coordinate, traversal order, name of the function, or a next-event pointer. A new activation at the same pole receives a new alias. To interpret a function's trajectory, the reader must be supplied with (or reconstruct) its actual pole and then load the function definition there.

```python
from oais.utils.data_manager import DataManager

manager = DataManager()
pole = manager.save_pole_function(
    "3 0 0 0 0 0",
    {"name": "cubic_offset", "version": 1, "params": {"scale": 1}}
)
ref = pole["id"]  # e.g. pi_c57d35bc0a817e62; auto-generated, nonsemantic
address = ["11 0 0 0 0 0", 2, ref, 8241]

saved = manager.save_logical_command(
    address, "help", counter_universe=0, direction="away"
)
assert "cubic_offset" not in str(saved)

found = manager.resolve_logical_command(
    address, counter_universe=0, direction="away"
)
assert found["command"] == "help"

# Resolve the actual function only when the original pole is known.
definition = manager.load_pole_function("3 0 0 0 0 0", ref)
assert definition["definition"]["name"] == "cubic_offset"
```

A saved `away` or `toward` command requires an opaque `pi_` alias, never an inline function descriptor or readable registry name. Default unlayered linear commands may use the `linear_offset` marker.

**Privacy / security limit:** Pole-local definitions and opaque aliases reduce disclosure in a single command record but do **not** make a raw JSON directory private. An observer with access to the whole coordinate tree could scan for poles, correlate repeated aliases, or inspect plaintext commands. Nor does an unkeyed evolving path-universe prove authenticity. For the stronger security objective, later work needs a secret-keyed derivation and/or encryption and access control. This patch establishes storage semantics, not a security guarantee.

**VirtualCounter usage:**

```python
v = VirtualCounter()
v.observe_host("3 0 0 0 0 0")  # FOLLOW
v.hold()                           # FREE; no automatic functional step
v.set_projection("11 0 0 0 0 0", imaginary=2,
                 function=ref, direction="away",
                 path_universe=8241)
assert v.logical_address() == ["11 0 0 0 0 0", 2, ref, 8241]
v.sync_to_host()                   # snap back to observed host; new seed=0
```

`set_projection` is currently a controlled test hook, not a navigation command. `path_universe` remains constant unless supplied explicitly; **the pure history-update helper exists, but there is no wiring to apply it automatically yet**. In FOLLOW mode, new host observations update real position without inventing new history identity. `sync_to_host(path_universe=seed)` can establish an explicit seed.

## Legacy support

- `StickyNoteEngine` still writes/reads its original linked `commands` arrays unchanged.
- Old schema-v2 three-part `logical_command` objects remain readable. They are **not** interpreted as four-part addresses, and the old `universe` field is treated as `counter_universe`.
- New version-3 `save_logical_command` requires **four** address elements and calls its overflow parameter `counter_universe` rather than `universe`. Functional events must use an opaque alias, with one matching function definition saved at their pole by the caller; the storage layer does not attempt to discover that pole from a random event coordinate.
- The connected Meta Terminal bridge and Base Counter were not modified.

## Install and test

1. Back up the repo and its data directories.
2. Copy the three Python files from this ZIP to their matching locations, replacing their *Phase 1* versions.
3. If nothing else imports `oais.utils.logical_address`, remove the now-unused old file.
4. Optionally copy `tests/test_four_part_foundation.py` and `tests/test_bridge_integration.py` into the repo's `tests` directory.
5. From the project root run:

```bash
python -m unittest discover -s tests -p 'test_four_part_foundation.py' -v
python -m unittest discover -s tests -p 'test_path_universe_hash.py' -v
python -m unittest discover -s tests -p 'test_bridge_integration.py' -v
python main.py
```

Test coverage: base-60 roundtrip; FOLLOW/FREE/sync; independent path and overflow universes; four-element validation; pole-only function definitions; per-event opaque references; multi-event storage; exact and ambiguous logical lookup; restart/reload; nested data immutability; legacy Sticky Note reading; legacy schema-v2 reading; in-memory terminal bridge; real PTY connected Meta Terminal. In the supplied project snapshot **17 tests passed** (11 foundation + 5 path universe + 1 PTY bridge; PTY needs Linux/WSL and `pexpect`).

## Pure path-universe evolution (added after reviewing `DefaultPath`)

The supplied older `DefaultPath` seeds `imag` through BLAKE2b but evolves it using a custom 32-bit arithmetic mixer. Its separate `real_step()` chooses real coordinates using a quadratic mapping. This patch **intentionally does not reproduce that real movement law**: future Navigator's registered function `p+f(k)` owns virtual real positions. The old `imag` concept becomes `path_universe`.

The foundation now offers two pure helpers in `virtual_counter.py`:

```python
from oais.utils.virtual_counter import seed_path_universe, evolve_path_universe

ref = "pi_0123456789abcdef"  # example only; generated at actual pole
u0 = seed_path_universe("3 0 0 0 0 0", "example-traversal-seed")
u1 = evolve_path_universe(
    u0,
    ["3 0 0 0 0 0", 0, ref],
    ["4 0 0 0 0 0", 1, ref],
    "away",
)
u2 = evolve_path_universe(
    u1,
    ["4 0 0 0 0 0", 1, ref],
    ["3 0 0 0 0 0", 0, ref],
    "toward",
)
assert u2 != u0  # return does not erase historical progression
```

It includes ordered start/end state, function reference, movement operation, old universe, and both Counter-overflow namespaces where relevant. It uses canonical JSON serialization, BLAKE2b-128, and an explicit v1 personalization. The same inputs produce exactly the same 128-bit integer. It is not equivalent to the historical `DefaultPath` sequence (its constants `A` and `M` were not included); **do not use it to migrate historical data without an explicit conversion design**.

A `secret=b"..."` optional argument enables keyed BLAKE2b; a secret must be kept outside readable coordinate blocks. An unkeyed hash is for deterministic lookup, not concealment or authentication. Raw plaintext commands are not encrypted. **Repeated opaque `pi_...` aliases across command blocks still reveal grouping to someone scanning the entire directory**, even though the function formula is only at the pole. If unlinkability is a firm requirement, the future storage contract must replace repeated aliases with per-step derived tags or avoid persisting the function reference on ordinary command events. Do that before treating this schema as final.

## What remains before Navigator

- Decide where the traversal seed/capability is held (e.g., Sticky Note descriptor) and whether to enable keyed BLAKE2b for stronger resistance to scanning.
- Define which terminal events count as path-universe transitions: ordinary commands, explicit movement, paused/held events, switch commands, nested menus, and resynchronization.
- Navigator must call `evolve_path_universe()` **once per eligible event**, after computing the logical transition, and pass the result to `VirtualCounter.set_projection()`.
- Confirm the final on-disk policy for the function field: this interim patch has pole-local definitions and repeated opaque aliases; it is not yet unlinkable to a full-coordinate-tree reader.

These choices do not require changing DEEP's primary Counter or the legacy Sticky Note writer.
