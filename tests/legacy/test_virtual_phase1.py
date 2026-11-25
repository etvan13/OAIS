import tempfile
import unittest
from pathlib import Path

from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager
from oais.utils.virtual_counter import VirtualCounter, address_to_integer, integer_to_address, SPACE
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.Commands.StickyNote.StickyNoteEngine import StickyNoteEngine


class VirtualPhase1Tests(unittest.TestCase):
    def test_base60_round_trip_and_universe(self):
        self.assertEqual(integer_to_address(60), ("0 1 0 0 0 0", 0))
        self.assertEqual(integer_to_address(-1), ("59 59 59 59 59 59", -1))
        self.assertEqual(integer_to_address(SPACE), ("0 0 0 0 0 0", 1))
        self.assertEqual(address_to_integer("59 59 59 59 59 59", -1), -1)
        self.assertEqual(address_to_integer("0 1 0 0 0 0", 0), 60)
        with self.assertRaises(ValueError):
            address_to_integer("60 0 0 0 0 0", 0)

    def test_virtual_follow_free_sync_and_unchanged_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Counter(load_state=False, save_path=Path(tmp) / "base.json")
            host_before = base.get_counters()
            v = VirtualCounter()
            v.observe_host("3 0 0 0 0 0")
            self.assertEqual(v.snapshot()["coordinate"], "3 0 0 0 0 0")
            v.hold()
            v.observe_host("4 0 0 0 0 0")
            self.assertEqual(v.snapshot()["coordinate"], "3 0 0 0 0 0")
            v.set_projection("11 0 0 0 0 0", imaginary=2,
                             function="cubic_offset", direction="away")
            v.observe_host("5 0 0 0 0 0")
            self.assertEqual(v.logical_address(), ["11 0 0 0 0 0", 2, "cubic_offset"])
            self.assertEqual(v.snapshot()["direction"], "away")
            v.sync_to_host()
            self.assertEqual(v.snapshot()["coordinate"], "5 0 0 0 0 0")
            self.assertEqual(v.snapshot()["imaginary"], 0)
            self.assertEqual(v.snapshot()["mode"], "follow")
            self.assertEqual(base.get_counters(), host_before)

    def test_terminal_bridge_logic_and_standalone_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            oais = OaisTerminal(
                counter=Counter(load_state=False, save_path=Path(tmp) / "standalone.json"),
                data_manager=DataManager(base_dir=Path(tmp) / "oais_data"),
            )
            standalone_before = oais.standalone_counter.get_counters()
            oais.attach_host("3 0 0 0 0 0")
            self.assertEqual(oais.virtual_counter.snapshot()["coordinate"], "3 0 0 0 0 0")
            oais.virtual_command("hold")
            oais.observe_event({"type": "command", "source": "base", "value": "help",
                                "coordinate_before": "3 0 0 0 0 0",
                                "coordinate_after": "4 0 0 0 0 0", "universe_after": 0})
            self.assertEqual(oais.host_counter.get_counters(), "4 0 0 0 0 0")
            self.assertEqual(oais.virtual_counter.snapshot()["coordinate"], "3 0 0 0 0 0")
            oais.virtual_counter.set_projection("11 0 0 0 0 0", imaginary=2,
                                                function="cubic_offset", direction="away")
            self.assertIn("11 0 0 0 0 0", oais.virtual_command("status"))
            oais.virtual_command("sync")
            self.assertEqual(oais.virtual_counter.snapshot()["coordinate"], "4 0 0 0 0 0")
            oais.detach_host()
            self.assertEqual(oais.counter, oais.standalone_counter)
            self.assertEqual(oais.standalone_counter.get_counters(), standalone_before)

    def test_datamanager_v2_collision_and_nested_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = DataManager(base_dir=Path(tmp))
            a = ["11 0 0 0 0 0", 2, "cubic_offset"]
            first = manager.save_logical_command(a, "outgoing", recording_id="N1",
                                                 direction="away", event_id="E1")
            second = manager.save_logical_command(a, "incoming", recording_id="N1",
                                                  direction="toward", event_id="E2")
            stack = [{"activation_id": "L1", "pole": "3 0 0 0 0 0", "step": 2,
                      "leg": "away"}, {"activation_id": "L2", "step": 1,
                                        "leg": "away"}]
            manager.save_logical_command(["11 0 0 0 0 0", stack,
                                          {"name": "linear_offset", "version": 1}],
                                         "nested", universe=1, direction="away",
                                         recording_id="N2", event_id="E3")
            stack[0]["step"] = 999  # snapshots cannot share mutable state
            manager2 = DataManager(base_dir=Path(tmp))
            all_at_real = manager2.load_logical_commands("11 0 0 0 0 0")
            self.assertEqual(len(all_at_real), 3)
            self.assertEqual([e["command"] for e in manager2.load_logical_commands(
                "11 0 0 0 0 0", universe=0, recording_id="N1")],
                ["outgoing", "incoming"])
            self.assertEqual(manager2.load_logical_commands(
                "11 0 0 0 0 0", universe=1)[0]["address"][1][0]["step"], 2)
            self.assertEqual(first["id"], "E1")
            self.assertEqual(second["id"], "E2")
            self.assertEqual(manager2.coordinate_location("11 0 0 0 0 0")[1].relative_to(tmp),
                             Path("coordinate_data/0/0/0/0/0.json"))
            with self.assertRaises(ValueError):
                manager2.save_logical_command(["11 0 0 0 0 0", -1, "cubic"], "invalid")

    def test_old_sticky_note_reconstructs_with_new_manager(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = DataManager(base_dir=Path(tmp))
            counter = Counter(load_state=False, save_path=Path(tmp) / "counter.json")
            engine = StickyNoteEngine(counter=counter, data_manager=manager)
            history = [
                (0, "forwards", 1), (1, "one", 2), (2, "two", 3),
                (3, "three", 4), (4, "four", 5),
                (5, "backwards", 4), (4, "help", 5),
            ]
            engine.start(metadata={"scope": "base"})
            for pos, command, after in history:
                engine.record_event({"value": command, "source": "base",
                                     "coordinate_before": f"{pos} 0 0 0 0 0",
                                     "coordinate_after": f"{after} 0 0 0 0 0"})
            note = engine.save_reference("legacy")
            engine2 = StickyNoteEngine(counter=counter, data_manager=DataManager(base_dir=Path(tmp)))
            _, loaded = engine2.load_path(note["id"])
            self.assertEqual([e["value"] for e in loaded], [h[1] for h in history])
            self.assertEqual(len(manager.read_command(["4 0 0 0 0 0", 0])), 3)
            self.assertEqual(len(manager.get_coordinate_node("4 0 0 0 0 0")["commands"]), 2)


if __name__ == "__main__":
    unittest.main()
