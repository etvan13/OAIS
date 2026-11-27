from history_assertions import steps
"""Regression for portable imaginary-layer navigation + v5/v6 note saving."""
from pathlib import Path
import tempfile
import unittest
from oais.Commands.Navigator.NavigatorEngine import (
    NavigatorEngine, function_definition, evaluate_offset,
)
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager
from oais.utils.virtual_counter import VirtualCounter


class ImaginaryStackV6Tests(unittest.TestCase):
    def new_nav(self, start="3 0 0 0 0 0"):
        v=VirtualCounter(); v.observe_host(start)
        return NavigatorEngine(v)

    def test_custom_math_is_anchored_and_safe(self):
        f=function_definition("2*k**2+5")
        self.assertEqual(f["f"], "2*k**2+5")
        self.assertEqual([evaluate_offset(f, i) for i in range(4)], [0,2,8,18])
        self.assertEqual(evaluate_offset(function_definition("abs(k-3)"), 3), -3)
        for bad in ("__import__('os').system('x')", "i/2", "k**10000", "i.real",
                    "[i]", "lambda i:i", "open('hello')", "i + 1.4"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                function_definition(bad)

    def test_independent_layers_return_without_extra_ticks(self):
        n=self.new_nav()
        n.open_pole("k**3")
        for _ in range(3): n.advance_automatic()
        self.assertEqual(n.virtual.coordinate, "30 0 0 0 0 0")
        n.push_function("k**2")
        self.assertEqual(n.compact_state()["functions"], [
            {"f":"k**3", "k":3, "direction":1},
            {"f":"k**2", "k":0, "direction":1},
        ])
        n.advance_automatic(); n.advance_automatic()
        self.assertEqual(n.virtual.coordinate, "34 0 0 0 0 0")
        n.turn()
        self.assertEqual(n.virtual.coordinate, "31 0 0 0 0 0")
        n.advance_automatic()  # last reverse tick pops quadratic
        self.assertEqual(n.virtual.coordinate, "30 0 0 0 0 0")
        self.assertEqual(n.compact_state()["functions"],
                         [{"f":"k**3", "k":3,"direction":1}])
        n.turn()
        self.assertEqual(n.virtual.coordinate, "11 0 0 0 0 0")
        n.advance_automatic(); n.advance_automatic()
        self.assertEqual(n.virtual.coordinate, "3 0 0 0 0 0")
        self.assertFalse(n.active)
        n.advance_linear(1)
        self.assertEqual(n.virtual.coordinate, "4 0 0 0 0 0")

    def test_nested_snapshot_roundtrip(self):
        n=self.new_nav(); n.open_pole("2*k**2+5"); n.away(); n.push_function("k**3"); n.away()
        snapshot=n.snapshot()
        other=self.new_nav(); other.restore(snapshot)
        self.assertEqual(other.compact_state(), n.compact_state())
        other.turn(); n.turn()
        self.assertEqual(other.virtual.logical_address(), n.virtual.logical_address())

    @staticmethod
    def base_event(t, text="hello"):
        coord=t.host_counter.get_counters(); u=t.host_counter.universes
        t.host_counter.increment()
        t.observe_event({"type":"command", "source":"base", "value":text,
                         "coordinate_before":coord,
                         "coordinate_after":t.host_counter.get_counters(),
                         "universe_before":u, "universe_after":t.host_counter.universes,
                         "success":True})

    def make_terminal(self, tmp):
        dm=DataManager(base_dir=Path(tmp)/"Data")
        t=OaisTerminal(counter=Counter(load_state=False,save_path=Path(tmp)/"state.json"),
                       data_manager=dm,terminal_id="base")
        t.attach_host("3 0 0 0 0 0")
        return t,dm

    def test_note_begins_midway_into_custom_expression(self):
        with tempfile.TemporaryDirectory() as tmp:
            t,dm=self.make_terminal(tmp)
            self.assertIn("Opened pole",t.navigator_command("open k**3"))
            for _ in range(2): self.base_event(t)
            self.assertEqual(t.virtual_counter.coordinate, "11 0 0 0 0 0")
            t.process_command("sticky start")
            self.base_event(t,"one")
            t.process_command("navigator turn")
            t.process_command("sticky stop")
            self.assertIn("Saved",t.process_command("sticky save midway").output)
            note=t.sticky_note.get_note("midway")
            self.assertEqual(note["start"],"11 0 0 0 0 0")
            self.assertEqual(note["end"],"11 0 0 0 0 0")
            self.assertEqual(note['start_state']['functions'], [{"f":"k**3","direction":1,"k":2}])
            self.assertNotIn("origin",note)
            self.assertEqual(note["blocks"],4)
            self.assertEqual([step["op"] for step in steps(t.sticky_note, note)], ["none", "auto_forward", "turn", "none"])
            b=dm.get_coordinate_node("11 0 0 0 0 0")["command_blocks"]
            self.assertEqual(len(b),3)
            self.assertNotIn("function",b[0])
            self.assertNotIn("name",str(note))
            self.assertEqual(set(note),{"id","title","start","end","start_state","storage","blocks","end_history"})
            _, events = t.sticky_note.load_path(note["id"])
            self.assertEqual([e['value'] for e in events], ['sticky start', 'one', 'navigator turn', 'sticky stop'])

    def test_note_begins_midway_into_nested_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            t,dm=self.make_terminal(tmp)
            t.navigator_command("open k**3")
            for _ in range(3):self.base_event(t)
            t.navigator_command("open k**2")
            for _ in range(2):self.base_event(t)
            self.assertEqual(t.virtual_counter.coordinate,"34 0 0 0 0 0")
            t.process_command("sticky start")
            t.process_command("navigator turn")
            self.base_event(t)
            t.process_command("sticky stop")
            self.assertIn("Saved",t.process_command("sticky save nested").output)
            note=t.sticky_note.get_note("nested")
            self.assertEqual(note["start_state"]["functions"],[
                {"f":"k**3", "k":3,"direction":1},
                {"f":"k**2", "k":2,"direction":1}])
            # A BASE ordinary command is +1 even after a manual turn.
            self.assertEqual(note["end"],"34 0 0 0 0 0")
            self.assertEqual(steps(t.sticky_note, note)[1]["op"], "turn")

    def test_push_during_recording_creates_new_pole_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            t,dm=self.make_terminal(tmp)
            t.process_command("sticky start")
            self.base_event(t)
            t.process_command("navigator open k**3")
            self.base_event(t)
            t.process_command("navigator open k**2")
            self.base_event(t)
            t.process_command("sticky stop")
            self.assertIn("Saved",t.process_command("sticky save switching").output)
            note=t.sticky_note.get_note("switching")
            self.assertEqual([a["f"] for a in steps(t.sticky_note,note) if "f" in a], ["k**3","k**2"])
            self.assertEqual([(index, step["op"]) for index,step in
                              enumerate(steps(t.sticky_note, note)) if step["op"] in ("open","push")],
                             [(2,"open"),(4,"push")])
            self.assertEqual(t.navigator_engine.compact_state()["functions"],[
                {"f":"k**3","k":1,"direction":1},
                {"f":"k**2","k":1,"direction":1},
            ])


if __name__ == '__main__': unittest.main()


class PortableHistoryAndSafetyTests(unittest.TestCase):
    def test_portable_signature_does_not_contain_random_activation_ids(self):
        from oais.Commands.StickyNote.StickyNoteEngine import StickyNoteEngine
        from oais.utils.virtual_counter import evolve_path_universe
        v1=VirtualCounter();v1.observe_host("3 0 0 0 0 0")
        v2=VirtualCounter();v2.observe_host("3 0 0 0 0 0")
        n1=NavigatorEngine(v1);n2=NavigatorEngine(v2)
        n1.open_pole("k**3");n2.open_pole("k**3")
        self.assertNotEqual(n1.layers[0]["id"],n2.layers[0]["id"])
        a=StickyNoteEngine._portable_signature(n1.snapshot())
        b=StickyNoteEngine._portable_signature(n2.snapshot())
        self.assertEqual(a,b)
        n1.away();n2.away()
        ca=StickyNoteEngine._portable_signature(n1.snapshot())
        cb=StickyNoteEngine._portable_signature(n2.snapshot())
        self.assertEqual(ca,cb)
        self.assertEqual(evolve_path_universe(44,a,ca,"event:0:hello:auto"),
                         evolve_path_universe(44,b,cb,"event:0:hello:auto"))
        self.assertNotIn("pi_",str(ca))

    def test_turn_immediately_after_push_spends_tick_on_parent(self):
        v=VirtualCounter();v.observe_host("3 0 0 0 0 0")
        n=NavigatorEngine(v)
        n.open_pole("k**3");n.away();n.away();n.away()
        n.push_function("k**2")
        n.turn()
        self.assertEqual(n.compact_state()["functions"],
                         [{"f":"k**3","k":2,"direction":-1}])
        self.assertEqual(n.virtual.coordinate,"11 0 0 0 0 0")

    def test_coordinate_blocks_rollback_if_note_definition_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm=DataManager(base_dir=Path(tmp)/"Data")
            t=OaisTerminal(counter=Counter(load_state=False,save_path=Path(tmp)/"c.json"),
                           data_manager=dm,terminal_id="base")
            t.attach_host("0 0 0 0 0 0")
            t.process_command("sticky start")
            before=t.host_counter.get_counters(); t.host_counter.increment()
            t.observe_event({"type":"command","source":"base","value":"hello",
                            "coordinate_before":before,
                            "coordinate_after":t.host_counter.get_counters(),
                            "universe_after":0,"universe_before":0,"success":True})
            def fail(*args, **kwargs): raise OSError("Disk full")
            dm.save_terminal_data=fail
            with self.assertRaises(OSError):
                t.sticky_note.save_reference("fail")
            node=dm.get_coordinate_node("0 0 0 0 0 0") or {}
            self.assertEqual(node.get("command_blocks",[]),[])
            self.assertEqual(len(t.sticky_note.get_path()),2)

    def test_compact_note_stores_rollover_as_separate_counter_universe(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm=DataManager(base_dir=Path(tmp)/"Data")
            t=OaisTerminal(counter=Counter(load_state=False,save_path=Path(tmp)/"c.json"),
                           data_manager=dm,terminal_id="base")
            t.attach_host("59 59 59 59 59 59")
            t.process_command("sticky start")
            t.host_counter.increment()
            t.observe_event({"type":"command","source":"base","value":"forward",
                            "coordinate_before":"59 59 59 59 59 59",
                            "coordinate_after":"0 0 0 0 0 0",
                            "universe_before":0,"universe_after":1,"success":True})
            t.process_command("sticky stop")
            t.sticky_note.save_reference("overflow")
            note=t.sticky_note.get_note("overflow")
            self.assertNotIn("start_universe",note)
            self.assertEqual(note["end_universe"],1)
            self.assertEqual(note["start_state"]["functions"],[])
            block=dm.get_coordinate_node("59 59 59 59 59 59")["command_blocks"][0]
            self.assertNotIn("counter_universe",block)

    def test_stationary_function_advances_imaginary_i_and_histories(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm=DataManager(base_dir=Path(tmp)/"Data")
            t=OaisTerminal(counter=Counter(load_state=False,save_path=Path(tmp)/"c.json"),
                           data_manager=dm,terminal_id="base")
            t.attach_host("3 0 0 0 0 0")
            t.navigator_command("open constant")
            t.process_command("sticky start")
            for name in ("one","two","three"):
                before=t.host_counter.get_counters()
                t.host_counter.increment()
                t.observe_event({"type":"command","source":"base","value":name,
                                 "coordinate_before":before,
                                 "coordinate_after":t.host_counter.get_counters(),
                                 "universe_before":0,"universe_after":0,"success":True})
            t.process_command("sticky stop")
            note=t.sticky_note.save_reference("stationary")
            self.assertEqual(note["start_state"]["functions"],[{"f":"0","direction":1,"k":0}])
            self.assertEqual(note["end"],"3 0 0 0 0 0")
            blocks=dm.get_coordinate_node("3 0 0 0 0 0")["command_blocks"]
            self.assertEqual(len(blocks),5)
            self.assertEqual(len({b["universe"] for b in blocks}),5)
            self.assertTrue(all("step" not in b for b in blocks[1:-1])
            )
            self.assertEqual([blocks[0].get('delta',0), blocks[-1].get('delta',0)], [0, 0])
