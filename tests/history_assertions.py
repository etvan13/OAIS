"""Helpers for regression assertions against coordinate-backed events."""
def steps(engine, note):
    assert "plan" not in note and "functions" not in note
    _, events = engine.load_path(note["id"], block_type="command")
    result = []
    for event in events:
        item = {"command": event["value"], "source": event["source"], **event.get("navigation", {})}
        if not event.get("success", True):
            item["failed"] = True
        result.append(item)
    return result
