# Replay coordinate data extension

The `oais replay data <six base-60 digits>` command reads all messages at the specified real coordinate via `DataManager.load_coordinate_messages`. It displays title, message, and structured JSON metadata without changing live navigation or replay cursor.

Example: `oais replay data 34 34 34 34 34 34`.

`oais replay load <note>` and `oais replay next` remain path-replay commands, not arbitrary data lookups. Data lookup does not traverse the four-part imaginary/path-universe address.
