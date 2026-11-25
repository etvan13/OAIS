import json
import tempfile
import unittest
from pathlib import Path
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.data_manager import DataManager
from oais.utils.counter import Counter


class VirtualPersistenceTests(unittest.TestCase):
    def make_terminal(self, directory):
        return OaisTerminal(counter=Counter(load_state=False, save_path=Path(directory)/"current_coordinate.json"), data_manager=DataManager(base_dir=directory))

    def test_saved_coordinate_and_nested_restore(self):
        with tempfile.TemporaryDirectory() as d:
            t = self.make_terminal(d)
            t.navigator_engine.open_pole("k**3")
            t.navigator_engine.away()
            t.navigator_engine.away()
            t.navigator_engine.push_function("k**2")
            t.navigator_engine.away()
            file = Path(d)/"virtual_coordinate.json"
            saved = json.loads(file.read_text())
            self.assertEqual(saved["coordinate"], "9 0 0 0 0 0")
            self.assertEqual(saved["coordinate_list"], [9,0,0,0,0,0])
            self.assertEqual(saved["functions"][0]["k"], 2)
            self.assertEqual(saved["functions"][1]["k"], 1)
            restored = self.make_terminal(d)
            self.assertEqual(restored.navigator_engine.compact_state()["functions"], saved["functions"])
            restored.navigator_engine.away()
            self.assertEqual(json.loads(file.read_text())["coordinate"], "12 0 0 0 0 0")

    def test_follow_updates_file(self):
        with tempfile.TemporaryDirectory() as d:
            t = self.make_terminal(d)
            t.attach_host("7 0 0 0 0 0", universes=2)
            data = json.loads((Path(d)/"virtual_coordinate.json").read_text())
            self.assertEqual((data["coordinate"], data["universes"], data["source"]), ("7 0 0 0 0 0", 2, "base"))
