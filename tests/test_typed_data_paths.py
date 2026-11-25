"""Typed blocks and deterministic, coordinate-backed data Sticky Notes."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from tools.conversation_importer import import_conversation, pair_messages
except ModuleNotFoundError as exc:
    if exc.name not in ("tools", "tools.conversation_importer"):
        raise
    from helpers.conversation_importer import import_conversation, pair_messages
from oais.Commands.Navigator.NavigatorEngine import NavigatorEngine, narrative_expression, evaluate_offset, function_definition
from oais.Commands.Replay.ReplayEngine import ReplayEngine
from oais.Commands.StickyNote.StickyNoteEngine import StickyNoteEngine
from oais.Commands.StickyNote.StickyNote import StickyNote
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager
from oais.utils.virtual_counter import address_to_integer


def sample(n=2, version=1):
    return {"source": "claude", "id": "conversation-test", "title": "Test narrative", "version": version,
            "messages": [{"role": role, "content": f"{role} {i}"} for i in range(n) for role in ("user", "assistant")]}


class TypedDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dm = DataManager(self.temp.name)
        self.reader = StickyNoteEngine(counter=Counter(load_state=False, persist=False), data_manager=self.dm, terminal_id="base")

    def test_shared_storage_and_exact_command_shape(self):
        c, u = "0 0 0 0 0 0", "a" * 32
        self.assertEqual(self.dm.save_command_block(c, "help", u, source="base", step=1), {"command": "help", "universe": u})
        value = {"user": "question", "assistant": "answer"}
        self.assertEqual(self.dm.save_conversation_block(c, value, u), {"block": value, "universe": u})
        self.dm.save_block(c, "text", "note", u)
        self.dm.save_block(c, "file", {"path": "paper.pdf", "page": 2}, u)
        self.assertEqual(len(self.dm.get_blocks_at_coordinate(c)), 4)
        self.assertEqual(len(self.dm.list_blocks("conversation")), 1)
        self.assertEqual(self.dm.load_block(c, "conversation", u)["block"], value)
        with self.assertRaises(ValueError):
            self.dm.save_conversation_block(c, value, u)
        self.assertTrue(self.dm.delete_block(c, "conversation", u))
        self.assertEqual(self.dm.load_command_block(c, u)["command"], "help")
        self.assertEqual(len(self.dm.get_blocks_at_coordinate(c)), 3)

    def test_unreadable_file_not_overwritten(self):
        _, path = self.dm.coordinate_location("0 0 0 0 0 0", create=True)
        path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.dm.save_block("0 0 0 0 0 0", "text", "note", "a"*32)
        self.assertEqual(path.read_text(), "{broken")

    def test_legacy_recurrence_and_backward(self):
        key = "conversation-test"
        pole, expression = narrative_expression(key)
        def digest(text):
            return int.from_bytes(hashlib.blake2b(text.encode(), digest_size=8).digest(), "big")
        start = digest("v1|"+key) % 60**6
        real, imaginary = start, digest(pole+"|"+key) % 2**32
        x = digest(f"{start}|{key}") % 60**6
        def constant(n):
            return sum((n//60**i % 60)*w for i,w in enumerate((13,17,19,23,29,31))) & 0xffffffff
        nav = NavigatorEngine(); nav.reset_to_linear(pole); nav.open_pole(expression)
        expected = []
        for k in range(12):
            expected.append(real)
            self.assertEqual(address_to_integer(nav.virtual.snapshot()["coordinate"], nav.virtual.universe), real)
            self.assertEqual(evaluate_offset(function_definition(expression), k), real-start)
            next_real = (real**2-imaginary**2+x) % 60**6
            imaginary = ((imaginary^constant(real)^constant(next_real))*0x9e3779b9+1)&0xffffffff
            real = next_real
            if k != 11: nav.away()
        restored = NavigatorEngine(); restored.restore_portable(NavigatorEngine.portable_state(nav.snapshot()))
        restored.turn()
        self.assertEqual(address_to_integer(restored.virtual.snapshot()["coordinate"], restored.virtual.universe), expected[-2])
        for target in reversed(expected[:-2]):
            restored.toward()
            self.assertEqual(address_to_integer(restored.virtual.snapshot()["coordinate"], restored.virtual.universe), target)
        with self.assertRaises(ValueError):
            function_definition("narrative_v1(999999999999,0,0,k)")

    def test_import_roundtrip_reimport_append_and_fork(self):
        c = sample(); first = import_conversation(c, self.dm)
        self.assertEqual(first["blocks"], 2)
        self.assertNotIn("plan", first)
        file = Path(self.temp.name)/"terminal_data/base/sticky_notes_conversations.json"
        self.assertTrue(file.is_file())
        self.assertNotIn("user 0", file.read_text())
        self.assertEqual([e["value"] for e in self.reader.load_path(first["id"])[1]], list(pair_messages(c["messages"])))
        self.assertEqual(import_conversation(c, self.dm), first)
        self.assertEqual(len(self.dm.list_blocks("conversation")), 2)
        extended = import_conversation(sample(3), self.dm)
        self.assertEqual(extended["id"], first["id"])
        self.assertEqual(len(self.dm.list_blocks("conversation")), 3)
        self.assertEqual([e["value"] for e in self.reader.load_path(first["id"])[1]], list(pair_messages(sample(3)["messages"])))
        changed = sample(3); changed["messages"][0]["content"] = "new question"
        with self.assertRaises(ValueError): import_conversation(changed, self.dm)
        changed["version"] = 2
        fork = import_conversation(changed, self.dm)
        self.assertNotEqual(first["id"], fork["id"])
        self.assertEqual(len(self.dm.list_blocks("conversation")), 6)
        self.assertEqual(len(self.reader.list_notes("conversation")), 2)
        self.assertEqual(ReplayEngine(self.dm, "base").available(), [])
        with self.assertRaises(KeyError): ReplayEngine(self.dm, "base").load(fork["id"], block_type="command")
        replay = ReplayEngine(self.dm, "base")
        replay.load(fork["id"])
        self.assertIn("new question", replay.next())
        self.assertIn("User:", StickyNote.format_event(self.reader.load_path(fork["id"])[1][0], 1))

    def test_text_notes_stationary_and_rollback(self):
        navigator = NavigatorEngine(); navigator.open_pole("0")
        sticky = StickyNoteEngine(counter=Counter(load_state=False, persist=False), data_manager=self.dm,
                                  terminal_id="base", navigation_provider=navigator.snapshot)
        sticky.start(metadata={"storage":"data"})
        for text in ("first", "second"): sticky.record_event({"type":"text", "value":text})
        with patch.object(self.dm, "save_terminal_data", side_effect=OSError("disk")):
            with self.assertRaises(OSError): sticky.save("test")
        self.assertEqual(self.dm.list_blocks(), [])
        self.assertEqual(len(sticky.get_path()), 2)
        note = sticky.save("test")
        self.assertEqual([e["value"] for e in sticky.load_path(note["id"])[1]], ["first", "second"])
        self.assertEqual(len({b["universe"] for b in self.dm.list_blocks()}), 2)
        self.assertTrue((Path(self.temp.name)/"terminal_data/base/sticky_notes_text.json").is_file())

    def test_legacy_collection_renamed_without_losing_notes(self):
        old = Path(self.temp.name)/"terminal_data/base/sticky_notes.json"
        old.parent.mkdir(parents=True)
        old.write_text(json.dumps({"notes": [{"id":"legacy", "title":"Old command"}]}))
        self.assertEqual(self.reader.get_note("legacy")["title"], "Old command")
        self.assertFalse(old.exists())
        self.assertTrue(old.with_name("sticky_notes_commands.json").is_file())

    def test_file_reference_note(self):
        nav = NavigatorEngine(); nav.open_pole("k")
        sticky = StickyNoteEngine(counter=Counter(load_state=False, persist=False), data_manager=self.dm,
                                  terminal_id="base", navigation_provider=nav.snapshot)
        sticky.start(metadata={"storage":"data"})
        payload = {"path":"paper.pdf", "page":4}
        sticky.record_event({"type":"file", "value":payload})
        note = sticky.save("Paper")
        self.assertEqual(sticky.load_path(note["id"])[1][0]["value"], payload)
        self.assertTrue((Path(self.temp.name)/"terminal_data/base/sticky_notes_files.json").is_file())

    def test_pending_and_non_alternating_roles(self):
        self.assertEqual(list(pair_messages([{"role":"assistant","content":"hello"},{"role":"user","content":"pending"}])),
                         [{"user":"","assistant":"hello"},{"user":"pending","assistant":""}])

if __name__ == "__main__": unittest.main()
