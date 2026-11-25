"""Import normalized Claude/GPT JSON as OAIS functional conversation Sticky Notes.

Run from the project root: python helpers/conversation_importer.py PATH
PATH may be one full conversation JSON or a sorted directory (not staging deltas).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oais.Commands.Navigator.NavigatorEngine import NavigatorEngine, narrative_expression
from oais.Commands.StickyNote.StickyNoteEngine import StickyNoteEngine
from oais.utils.data_manager import DataManager
from oais.utils.counter import Counter


def pair_messages(messages):
    """Pair adjacent user/assistant messages by role, preserving unmatched turns."""
    if not isinstance(messages, list):
        raise ValueError("Expected an ordered messages list.")
    index = 0
    while index < len(messages):
        message = messages[index]
        if not isinstance(message, dict) or message.get("role") not in ("user", "assistant") or not isinstance(message.get("content"), str):
            raise ValueError(f"Invalid normalized message at index {index}.")
        role = message["role"]
        block = {"user": "", "assistant": ""}
        block[role] = message["content"]
        index += 1
        if role == "user" and index < len(messages):
            following = messages[index]
            if isinstance(following, dict) and following.get("role") == "assistant":
                if not isinstance(following.get("content"), str):
                    raise ValueError(f"Invalid assistant content at index {index}.")
                block["assistant"] = following["content"]
                index += 1
        yield block


def import_conversation(conversation, data_manager, *, terminal_id="base"):
    """Import a full normalized snapshot; exact repeat is a no-op, clean tail extends."""
    cid = conversation.get("id")
    source = conversation.get("source", "gpt")
    version = conversation.get("version", 1)
    if not isinstance(cid, str) or not cid or not isinstance(source, str) or not source or type(version) is not int or version < 1:
        raise ValueError("Conversation needs a source, stable ID and positive version.")
    messages = conversation.get("messages")
    blocks = list(pair_messages(messages))
    if not blocks:
        raise ValueError("Conversation contains no messages.")
    if len(messages) != conversation.get("message_count", len(messages)):
        raise ValueError("Message count differs from the normalized snapshot.")
    attachments = conversation.get("attachments", [])
    if not isinstance(attachments, list) or not all(isinstance(a, str) for a in attachments):
        raise ValueError("Conversation attachments must be filenames.")
    # Separate namespaces for source/version; keep same ID across clean appends.
    identity = json.dumps([source, cid, version], separators=(",", ":"), ensure_ascii=False)
    note_id = hashlib.blake2b(identity.encode(), digest_size=16, person=b"OAISConvNote-v1").hexdigest()
    # v1 uses the historical conversation UUID as the dispersion seed.
    # Forks of the same conversation retain their geometric prefix but have separate histories.
    pole, expression = narrative_expression(cid)
    navigator = NavigatorEngine()
    navigator.reset_to_linear(pole)
    navigator.open_pole(expression)
    sticky = StickyNoteEngine(counter=Counter(load_state=False, persist=False),
                              data_manager=data_manager, terminal_id=terminal_id,
                              navigation_provider=navigator.snapshot)
    sticky.start(metadata={"storage": "data", "note_id": note_id})
    for block in blocks:
        names = [name for name in attachments if any(
            f"[File]: {name}" in text or f"[Image]: {name}" in text for text in block.values())]
        sticky.record_event({"type": "conversation", "value": block,
                             "source": source, "attachments": names})
    sticky.stop()
    return sticky.save(conversation.get("title") or "Untitled", metadata={
        "conversation_id": cid, "source": source, "version": version}, clear=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--directory", type=Path, help="Sorted archive directory, not staging")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--terminal-id", default="base", help="Use base for normal main.py, oais_standalone for standalone")
    args = parser.parse_args(argv)
    if bool(args.path) == bool(args.directory):
        parser.error("Provide one input path or --directory.")
    path = args.path or args.directory
    if not path.exists():
        parser.error(f"Input does not exist: {path}")
    paths = sorted(path.rglob("*.json")) if path.is_dir() else [path]
    dm = DataManager(base_dir=args.data_dir)
    successful = failed = 0
    for file in paths:
        try:
            conversation = json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(conversation, dict) or not {"id", "messages"} <= conversation.keys():
                if path.is_dir():
                    continue  # other JSON attachments
                raise ValueError("Expected a normalized conversation object.")
            note = import_conversation(conversation, dm, terminal_id=args.terminal_id)
            print(f"{note['title']} [{note['id']}]: {note['blocks']} blocks | {note['start']} -> {note['end']}")
            successful += 1
        except (ValueError, TypeError, KeyError, OSError) as exc:
            print(f"ERROR {file}: {exc}", file=sys.stderr)
            failed += 1
    print(f"{successful} conversation(s) saved or already present; {failed} failed.")
    return 1 if failed or not successful else 0


if __name__ == "__main__":
    raise SystemExit(main())
