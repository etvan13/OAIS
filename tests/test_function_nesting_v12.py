"""v12: no pole metadata in shared coordinates; CLI alias and nested private note."""
import json
from pathlib import Path
import tempfile
import unittest

from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager
import test_storage_preplay_v11


class FunctionNestingV12Tests(unittest.TestCase):
    def make(self, folder):
        base = Path(folder) / 'Data'
        return OaisTerminal(
            counter=Counter(load_state=False, save_path=base / 'current_coordinate.json'),
            data_manager=DataManager(base_dir=base), terminal_id='base')

    @staticmethod
    def tick(term, before, command='help'):
        # BASE physical coordinates belong to BASE, separate from virtual.
        after = before - 1 if command == 'backwards' else before + 1
        term.observe_event({'type': 'command', 'source': 'base', 'value': command,
                            'success': True,
                            'coordinate_before': f'{before} 0 0 0 0 0',
                            'coordinate_after': f'{after} 0 0 0 0 0',
                            'universe_before': 0, 'universe_after': 0})
        return after

    def test_function_alias_preserves_quadratic_parent_and_private_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            t = self.make(folder)
            t.attach_host('0 0 0 0 0 0')
            self.assertIn('Opened pole', t.process_command('oais function k**2').output)
            source = 0
            for _ in range(3):
                source = self.tick(t, source)
            self.assertEqual(t.virtual_counter.coordinate, '9 0 0 0 0 0')
            self.assertIn('Opened pole', t.process_command('oais function k**3').output)
            self.assertEqual(t.navigator_engine.compact_state()['functions'], [
                {'f': 'k**2', 'k': 3, 'direction': 1},
                {'f': 'k**3', 'k': 0, 'direction': 1}])
            source = self.tick(t, source, 'forwards')
            self.assertEqual(t.virtual_counter.coordinate, '10 0 0 0 0 0')
            state = json.loads(t.virtual_state_path.read_text())
            self.assertEqual(state['pole'], '0 0 0 0 0 0')
            self.assertEqual(state['coordinate'], '10 0 0 0 0 0')
            self.assertEqual(state['source_coordinate'], '4 0 0 0 0 0')
            self.assertEqual(state['functions'], [
                {'f': 'k**2', 'k': 3, 'direction': 1},
                {'f': 'k**3', 'k': 1, 'direction': 1}])
            self.assertEqual(list(t.data_manager.coordinate_dir.rglob('*.json')), [])
            self.assertEqual(t.data_manager.list_objects('pole_function'), [])
            # Restore from virtual_coordinate.json with no pole objects at all.
            restored = self.make(folder)
            restored.attach_host('4 0 0 0 0 0')
            self.assertEqual(restored.navigator_engine.compact_state()['functions'], state['functions'])
            self.assertEqual(restored.virtual_counter.coordinate, state['coordinate'])
            restored.observe_event({'type': 'command', 'source': 'base', 'value': 'backwards',
                'success': True, 'coordinate_before': '4 0 0 0 0 0',
                'coordinate_after': '3 0 0 0 0 0', 'universe_before': 0, 'universe_after': 0})
            self.assertEqual(restored.virtual_counter.coordinate, '9 0 0 0 0 0')
            # Landing at child k=0 keeps its pole available for rebound.
            self.assertEqual(restored.navigator_engine.compact_state()['functions'], [
                {'f': 'k**2', 'k': 3, 'direction': 1},
                {'f': 'k**3', 'k': 0, 'direction': -1}])

    def test_bad_function_does_not_change_parent_state(self):
        with tempfile.TemporaryDirectory() as folder:
            t = self.make(folder)
            t.attach_host('0 0 0 0 0 0')
            t.process_command('function k**2')
            self.tick(t, 0)
            before = t.navigation_context()
            result = t.process_command('function k/3')
            self.assertIn('OAIS command error:', result.output)
            self.assertEqual(t.navigation_context()['functions'], before['functions'])
            self.assertEqual(t.navigation_context()['coordinate'], before['coordinate'])
            self.assertEqual(t.data_manager.list_objects('pole_function'), [])

    def test_private_note_can_reconstruct_nested_function_alias_with_no_poles(self):
        with tempfile.TemporaryDirectory() as folder:
            t = self.make(folder)
            t.attach_host('0 0 0 0 0 0')
            t.process_command('function k**2')
            source = 0
            for _ in range(3):
                source = self.tick(t, source)
            t.process_command('sticky start')
            t.process_command('function k**3')
            source = self.tick(t, source, 'forwards')
            source = self.tick(t, source, 'backwards')
            source = self.tick(t, source, 'backwards')
            t.process_command('sticky stop')
            note = t.sticky_note.save_reference('nested_alias')
            self.assertEqual(note['start'], '9 0 0 0 0 0')
            self.assertEqual(note['end'], '4 0 0 0 0 0')
            self.assertEqual(note['start_state']['functions'], [{'f':'k**2', 'k':3, 'direction':1}])
            self.assertEqual(note['plan'][1]['command'], 'function k**3')
            self.assertEqual(note['plan'][1]['op'], 'push')
            self.assertEqual(note['plan'][1]['f'], 'k**3')
            self.assertEqual(t.data_manager.list_objects('pole_function'), [])
            saved = t.data_manager.load_terminal_data('base', 'sticky_notes_commands')['notes'][-1]
            self.assertEqual(saved, note)
            reconstructed = test_storage_preplay_v11.StorageReadinessV11Tests.reconstruct_math_from_private_note(saved)
            self.assertEqual(reconstructed['real'], note['end'])
            self.assertEqual(reconstructed['functions'], [{'f':'k**2','k':2,'direction':-1}])
            files = list(t.data_manager.coordinate_dir.rglob('*.json'))
            self.assertTrue(files)
            for path in files:
                payload = json.loads(path.read_text())
                for node in payload.values():
                    self.assertNotIn('objects', node)
                    for block in node.get('command_blocks', []):
                        self.assertEqual(set(block).intersection({'definition','pole_function','f','k','plan','title'}), set())


if __name__ == '__main__':
    unittest.main()
