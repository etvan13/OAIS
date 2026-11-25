# Virtual Coordinate Persistence (v9)

`oais/Data/virtual_coordinate.json` is written beside `current_coordinate.json`.

Top-level `coordinate`, `coordinate_list`, and `universes` mirror the regular Counter layout. `source` is `base` when connected and `oais` in standalone mode. `functions` is a compact, ordered stack of expressions (`f`), imaginary ticks (`k`), and directions (+1/-1).

The additional `navigation` object is an exact Navigator snapshot (including pole anchors, activation IDs, path-universe hash and automatic-progress state). It is needed to resume nested navigation correctly after restarting, not just display it. Sticky Notes can read the compact `functions` list or use the existing in-memory navigation provider.

Updates are atomic and occur after completed Navigator actions, BASE observations and OAIS commands. On startup, an existing snapshot is validated and restored. Invalid snapshots raise an error instead of silently destroying prior navigation. The file is terminal state, not a Sticky Note recording or a Replay implementation.
