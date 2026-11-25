"""Terminal-owned note definitions and compact function-selector regression tests."""
from pathlib import Path
import tempfile
import unittest

from oais.utils.data_manager import DataManager
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter


class TerminalStorageTests(unittest.TestCase):
    def test_terminal_namespaces_are_independent_and_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm = DataManager(base_dir=Path(tmp))
            dm.save_terminal_data('deep_base', 'sticky_notes_commands', {'notes': [{'id': 'a'}]})
            dm.save_terminal_data('oais_standalone', 'sticky_notes_commands', {'notes': [{'id': 'b'}]})
            self.assertEqual(dm.load_terminal_data('deep_base', 'sticky_notes_commands')['notes'][0]['id'], 'a')
            self.assertEqual(dm.load_terminal_data('oais_standalone', 'sticky_notes_commands')['notes'][0]['id'], 'b')
            self.assertTrue((Path(tmp)/'terminal_data'/'deep_base'/'sticky_notes_commands.json').exists())
            with self.assertRaises(ValueError):
                dm.save_terminal_data('../escape', 'sticky_notes_commands', {})

    def test_new_note_has_function_catalog_and_no_coordinate_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm = DataManager(base_dir=Path(tmp)/'Data')
            term = OaisTerminal(counter=Counter(load_state=False, save_path=Path(tmp)/'state.json'),
                                data_manager=dm, terminal_id='deep_base')
            term.attach_host('0 0 0 0 0 0')
            def command(value):
                result = term.process_command(value, connected=False)
                self.assertTrue(result.handled)
                self.assertNotIn('OAIS command error', result.output)
                return result.output
            command('navigator open cubic')
            command('sticky start')
            for _ in range(2):
                before = term.host_counter.get_counters()
                u = term.host_counter.universes
                term.host_counter.increment()
                term.observe_event({'type':'command','source':'base','value':'help',
                                    'coordinate_before':before,
                                    'coordinate_after':term.host_counter.get_counters(),
                                    'universe_before':u,
                                    'universe_after':term.host_counter.universes,
                                    'success':True})
            command('navigator turn')
            command('sticky stop')
            self.assertTrue(command('sticky save example').startswith('Saved '))
            note = term.sticky_note.get_note('example')
            self.assertEqual(note['functions'][0]['f'], 'k**3')
            self.assertEqual(note['functions'][0]['direction'], 1)
            self.assertEqual(note['blocks'], 5)
            self.assertEqual(len(note['functions']), 2)  # turn switches on that event
            self.assertEqual(dm.get_objects_at_coordinate('0 0 0 0 0 0', 'sticky_note'), [])
            records = dm.get_coordinate_node('0 0 0 0 0 0')['command_blocks']
            self.assertEqual(records[0]['function'], 0)
            self.assertEqual(set(records[0]), {'command', 'universe', 'function', 'step', 'source'})
            _, replayed = term.sticky_note.load_path(note['id'])
            self.assertEqual(len(replayed), 5)
            self.assertEqual(replayed[-2]['value'], 'navigator turn'
            )
            self.assertEqual(replayed[-1]['value'], 'sticky stop')

if __name__ == '__main__':
    unittest.main()
