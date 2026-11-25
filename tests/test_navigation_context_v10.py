"""v10: choose one source, restore k safely, and give Notes a full entry context."""
from pathlib import Path
import json
import tempfile
import unittest

from oais.Commands.Navigator.NavigatorEngine import NavigatorEngine
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager


class NavigationContextV10Tests(unittest.TestCase):
    def make(self, directory, *, persisted_counter=False, persist_virtual_state=True):
        directory = Path(directory)
        return OaisTerminal(
            counter=Counter(load_state=persisted_counter,
                            save_path=directory / 'Data' / 'current_coordinate.json'),
            data_manager=DataManager(base_dir=directory / 'Data'),
            terminal_id='base', persist_virtual_state=persist_virtual_state)

    @staticmethod
    def tick(t, command='help'):
        before, u = t.host_counter.get_counters(), t.host_counter.universes
        if command == 'backwards':
            t.host_counter.decrement()
        else:
            t.host_counter.increment()
        t.observe_event({'type': 'command', 'source': 'base', 'value': command,
                         'success': True, 'coordinate_before': before,
                         'coordinate_after': t.host_counter.get_counters(),
                         'universe_before': u,
                         'universe_after': t.host_counter.universes})

    @staticmethod
    def file(directory):
        return json.loads((Path(directory)/'Data'/'virtual_coordinate.json').read_text())

    def test_portable_derived_from_exact_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            t = self.make(d)
            t.attach_host('3 0 0 0 0 0')
            t.process_command('navigator function k**3')
            for _ in range(3): self.tick(t)
            t.process_command('navigator function k**2')
            for _ in range(2): self.tick(t)
            saved = self.file(d)
            self.assertEqual(saved['coordinate'], '34 0 0 0 0 0')
            self.assertEqual(saved['coordinate_list'], [34,0,0,0,0,0])
            self.assertEqual(saved['universes'], 0)
            self.assertEqual(saved['source'], 'base')
            self.assertEqual(saved['source_coordinate'], '8 0 0 0 0 0')
            self.assertEqual(saved['source_universes'], 0)
            self.assertEqual(saved['functions'], [
                {'f':'k**3','k':3,'direction':1},
                {'f':'k**2','k':2,'direction':1}])
            self.assertNotIn('navigation',saved)
            self.assertEqual(saved['pole'],'3 0 0 0 0 0')
            self.assertNotIn('mode',saved)  # active functions imply FREE
            self.assertNotIn('paused',saved)
            self.assertEqual(saved['functions'],
                NavigatorEngine.portable_state(
                    NavigatorEngine.snapshot_from_portable(saved))['functions'])

    def test_sticky_captures_full_functional_start_at_recording_start(self):
        with tempfile.TemporaryDirectory() as d:
            t = self.make(d)
            t.attach_host('3 0 0 0 0 0')
            t.process_command('navigator function k**3')
            for _ in range(3): self.tick(t)
            t.process_command('navigator function k**2')
            for _ in range(2): self.tick(t)
            snapshot_at_start=self.file(d)
            t.process_command('sticky start')
            self.assertEqual(t.sticky_note.navigation_context_start['functions'],
                             snapshot_at_start['functions'])
            self.tick(t, 'backwards')
            t.process_command('sticky stop')
            note = t.sticky_note.save_reference('midway nested')
            self.assertEqual(note['start'], '34 0 0 0 0 0')
            self.assertEqual(note['start_state']['coordinate'], '34 0 0 0 0 0')
            self.assertEqual(note['start_state']['functions'], [
                {'f':'k**3','k':3,'direction':1},
                {'f':'k**2','k':2,'direction':1}])
            self.assertEqual(note['start_state']['source'], 'base')
            self.assertEqual(note['start_state']['source_coordinate'],'8 0 0 0 0 0')
            self.assertEqual(note['start_state']['universes'], 0)
            self.assertNotIn('pi_', json.dumps(note))
            self.assertNotIn('navigation', note)  # no internal runtime snapshot
            stored = t.data_manager.load_terminal_data('base','sticky_notes')['notes'][0]
            self.assertEqual(stored['start_state'], note['start_state'])

    def test_restart_same_source_same_counter_retains_k_then_one_tick(self):
        with tempfile.TemporaryDirectory() as d:
            t = self.make(d)
            t.attach_host('3 0 0 0 0 0')
            t.process_command('navigator function k**2')
            for _ in range(3): self.tick(t)
            self.assertEqual(t.virtual_counter.coordinate,'12 0 0 0 0 0')
            restarted=self.make(d, persisted_counter=True)
            restarted.attach_host('6 0 0 0 0 0')
            self.assertEqual(restarted.navigator_engine.layers[-1]['k'],3)
            self.tick(restarted)
            self.assertEqual(restarted.navigator_engine.layers[-1]['k'],4)
            self.assertEqual(restarted.virtual_counter.coordinate,'19 0 0 0 0 0')
            self.assertEqual(self.file(d)['source_coordinate'],'7 0 0 0 0 0')

    def test_stale_base_position_rebases_without_phantom_tick(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make(d)
            t.attach_host('3 0 0 0 0 0')
            t.process_command('navigator function k**3')
            self.tick(t)
            restarted=self.make(d)
            restarted.attach_host('50 0 0 0 0 0')
            self.assertEqual(restarted.virtual_counter.coordinate,'50 0 0 0 0 0')
            self.assertFalse(restarted.navigator_engine.layers)
            saved=self.file(d)
            self.assertEqual(saved['source_coordinate'],'50 0 0 0 0 0')
            self.assertEqual(saved['suspended_context']['source'],'base')
            self.assertEqual(saved['suspended_context']['functions'][0]['k'],1)
            self.tick(restarted)
            self.assertEqual(restarted.virtual_counter.coordinate,'51 0 0 0 0 0')

    def test_switch_source_rebases_and_standalone_progress_uses_oais(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make(d)
            t.attach_host('3 0 0 0 0 0')
            t.process_command('navigator function k**3')
            self.tick(t)
            t.process_command('help')  # OAIS Counter progresses independently
            self.assertEqual(t.virtual_counter.coordinate,'4 0 0 0 0 0')
            t.detach_host()
            self.assertEqual(t.virtual_counter.coordinate, '2 0 0 0 0 0')
            self.assertEqual(self.file(d)['source'],'oais')
            self.assertEqual(self.file(d)['functions'],[])
            t.process_command('navigator function k**2')
            for _ in range(3): t.process_command('help')
            # Activating the function increments OAIS Counter, then 3 help ticks
            self.assertEqual(t.virtual_counter.coordinate,'12 0 0 0 0 0')
            self.assertEqual(self.file(d)['functions'][0]['k'],3)
            t.attach_host('4 0 0 0 0 0')
            self.assertEqual(t.virtual_counter.coordinate,'4 0 0 0 0 0')
            self.assertEqual(self.file(d)['source'],'base')
            self.assertFalse(t.navigator_engine.layers)

    def test_source_change_while_note_active_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make(d)
            t.attach_host('3 0 0 0 0 0')
            t.process_command('sticky start')
            with self.assertRaisesRegex(ValueError,'Save or clear'):
                t.detach_host()
            self.assertTrue(t.connected)
            self.assertEqual(self.file(d)['source'],'base')

    def test_meta_mirror_cannot_overwrite_worker_virtual_state(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make(d)
            t.attach_host('7 0 0 0 0 0')
            t.process_command('navigator function k**3')
            self.tick(t)
            path=Path(d)/'Data'/'virtual_coordinate.json'
            before=path.read_bytes()
            mirror=self.make(d,persist_virtual_state=False)
            mirror.attach_host('40 0 0 0 0 0')
            mirror.process_command('navigator function k**2')
            self.assertEqual(path.read_bytes(),before)

    def test_standalone_restart_restores_if_oais_counter_matches(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make(d,persisted_counter=True)
            t.detach_host()
            t.process_command('navigator function k**2')
            t.process_command('help')
            self.assertEqual(t.virtual_counter.coordinate,'2 0 0 0 0 0')
            restarted=self.make(d,persisted_counter=True)
            restarted.detach_host()
            self.assertEqual(restarted.navigator_engine.layers[0]['k'],1)
            restarted.process_command('help')
            self.assertEqual(restarted.navigator_engine.layers[0]['k'],2)
            self.assertEqual(restarted.virtual_counter.coordinate,'5 0 0 0 0 0')

if __name__=='__main__':
    unittest.main()
