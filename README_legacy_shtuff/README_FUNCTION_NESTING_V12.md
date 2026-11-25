# OAIS v12 — Function nesting without coordinate pole objects

## What was going wrong

In v11 the OAIS terminal registered every Navigator function activation as a `pole_function` object in `coordinate_data`. That was a leftover from the original four-part, pole-local function registry. It was no longer required: the current `virtual_coordinate.json` stores the live mathematical stack, while each new Sticky Note's `start_state` and private `plan` store the mathematical information needed for later reconstruction.

In the reported example, `oais function k**3` was **not a recognized BASE-to-OAIS command**; the accepted syntax was `oais navigator function k**3`. The cubic activation never occurred, so only the quadratic layer appeared. The BASE command `forward` (singular) was also unknown; BASE uses `forwards`.

## Changes

1. **Normal Navigator activation no longer saves `pole_function` objects** in shared coordinate files, at roots or nested poles. The `VirtualCounter` and `NavigatorEngine` remain in-memory authorities and persist their mathematical state to `virtual_coordinate.json`.
2. **`oais function <f(k)>` works directly from BASE**, as shorthand for `oais navigator function <f(k)>`. Standalone OAIS also accepts `function <f(k)>`. The existing `navigator` menu works as before. All these paths use `push_function`: if a layer is active, it stays frozen under the newly selected child, which starts at `k=0` at the current virtual coordinate. Selecting a function does not tick the virtual counter.
3. **The modern Sticky Note saver no longer looks up newly opened functions in coordinate objects.** In-memory navigation events carry the function expression and (for runtime checking only) the activation identity/root seed; the terminal-owned plan retains the portable expression and operation. Public saved `command_blocks` retain the old compact format, with no new event field.
4. **`navigator checkpoint` is now self-contained** in the terminal's local `Data/navigator_checkpoint.json`. Restore does not need coordinate pole objects for new checkpoints. The old pole-dependent checkpoint reader remains available for existing files.
5. **Cleaner display:** `oais virtual` and `Navigator` status display mathematical `f(k)` and each `k` layer, not internal `pi_...` activation references and path-history integers.
6. Existing historical pole objects **are NOT automatically deleted**. They may be needed by old v4 Sticky Notes. An optional dry-run cleanup tool is included. Older explicit v4-storage compatibility is retained for historical tests, but it is not enabled in ordinary OAIS use.

## Exact example

Start BASE at zero. In BASE:

```text
oais function k**2
help
help
help
```

BASE is at 3; virtual is at `3**2=9`. Then:

```text
oais function k**3
oais virtual
```

The function stack is now, from root to active layer:

```json
{
  "coordinate": "9 0 0 0 0 0",
  "functions": [
    {"f": "k**2", "k": 3, "direction": 1},
    {"f": "k**3", "k": 0, "direction": 1}
  ],
  "pole": "0 0 0 0 0 0"
}
```

The complete `virtual_coordinate.json` also stores `coordinate_list`, `universes`, `source`, `source_coordinate`, and `source_universes` (as in v11).

After one `forwards` from BASE, virtual reaches `10` (`9 + 1**3`). A subsequent BASE `backwards` closes the cubic layer at `k=0` and restores the quadratic parent at `k=3`, virtual `9`. Another `backwards` returns the parent to `k=2`, virtual `4`.

**Important timing detail:** if BASE has already run `backwards`, or an unknown command has affected automatic ticks, the saved parent `k` may no longer be `3`. Function selection freezes the actual state at that moment rather than an earlier state.

## Sticky Note / coordinate storage

After `sticky start` and a function selection, new notes contain a self-contained entry snapshot and ordered plan in `Data/terminal_data/<terminal_id>/sticky_notes.json`.

```json
{
  "start_state": {
    "coordinate": "9 0 0 0 0 0",
    "functions": [{"f": "k**2", "k": 3, "direction": 1}],
    "pole": "0 0 0 0 0 0"
  },
  "plan": [
    {"command": "function k**3", "source": "oais", "op": "push", "f": "k**3"},
    {"command": "forwards", "source": "base", "op": "auto_forward", "delta": 1}
  ]
}
```

This is an abbreviated illustration; actual `start_state` also includes the source coordinates and other relevant fields, and OAIS function-selection events can include the ordinary OAIS Counter `delta`. Shared coordinates store only compact command blocks. They no longer receive new function definitions or runtime pole objects through normal Navigator use.

## Old `pole_function` objects already on disk

**Do not remove them blindly** if you want to keep reading old **v4** Sticky Notes. The v12 code stops *new* writes, but deliberately leaves existing files untouched.

Optional report (no changes):

```bash
python3 tools/prune_legacy_poles.py --data-dir ./oais/Data
```

Only after deciding that older pole-dependent v4 paths are expendable (or backing up the entire Data directory), explicitly opt in:

```bash
python3 tools/prune_legacy_poles.py --data-dir ./oais/Data --apply --accept-legacy-breakage
```

The script removes only the `pole_function` object category and leaves all existing `command_blocks` and unrelated object categories intact. It makes a `.json.pole-backup` copy of every modified coordinate file. When a file contains nothing else, its JSON file is removed after backup. The script will not overwrite an existing per-file backup.

## Scope / testing

Replay for the new compact notes is still deferred. The existing BASE project organization is unchanged. `NavigatorEngine`'s legacy internal `pi_...` IDs and path history still exist **in memory** for historical readers and deterministic event processing; they are no longer written as pole objects during normal navigation.

Tests from the project root:

```bash
python3 -m unittest discover -s tests -q
```

The suite includes a real Meta Terminal test for the exact `oais function k**3` shorthand, a no-pole-file test, restart from compact virtual state, a private-JSON-only nested Sticky Note reconstruction, and a dry-run/prune safety test.
