import tempfile
import unittest
from pathlib import Path
from copy import deepcopy

from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager
from oais.utils.virtual_counter import VirtualCounter, address_to_integer, integer_to_address, SPACE
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.Commands.StickyNote.StickyNoteEngine import StickyNoteEngine


class FourPartFoundationTests(unittest.TestCase):
    def test_coordinate_roundtrip_with_counter_universe(self):
        self.assertEqual(integer_to_address(60), ('0 1 0 0 0 0', 0))
        self.assertEqual(integer_to_address(-1), ('59 59 59 59 59 59', -1))
        self.assertEqual(integer_to_address(SPACE), ('0 0 0 0 0 0', 1))
        self.assertEqual(address_to_integer('59 59 59 59 59 59', -1), -1)

    def test_virtual_follow_free_and_snapshot(self):
        v = VirtualCounter()
        v.observe_host('3 0 0 0 0 0')
        self.assertEqual(v.logical_address(), ['3 0 0 0 0 0', 0, 'linear_offset', 0])
        v.hold()
        v.observe_host('4 0 0 0 0 0')
        self.assertEqual(v.logical_address()[0], '3 0 0 0 0 0')
        v.set_projection('11 0 0 0 0 0', imaginary=2, function='cubic_offset',
                         direction='away', path_universe=827)
        self.assertEqual(v.logical_address(), ['11 0 0 0 0 0', 2, 'cubic_offset', 827])
        self.assertEqual(v.snapshot()['universe'], 0)
        self.assertEqual(v.snapshot()['path_universe'], 827)
        v.observe_host('5 0 0 0 0 0')
        self.assertEqual(v.logical_address()[-1], 827)
        v.sync_to_host()
        self.assertEqual(v.logical_address(), ['5 0 0 0 0 0', 0, 'linear_offset', 0])
        self.assertEqual(v.snapshot()['mode'], 'follow')
        v.sync_to_host(path_universe=42)
        v.observe_host('6 0 0 0 0 0')
        self.assertEqual(v.logical_address()[-1], 42)  # preserved, not auto-evolved

    def test_path_universe_and_overflow_are_independent(self):
        v = VirtualCounter()
        v.set_projection('11 0 0 0 0 0', universe=-2, imaginary=3,
                         function='cubic_offset', path_universe=12456)
        self.assertEqual(v.logical_address()[-1], 12456)
        self.assertEqual(v.snapshot()['counter_universe'], -2)
        v.set_projection('12 0 0 0 0 0', universe=1, imaginary=4,
                         function='cubic_offset')
        self.assertEqual(v.logical_address()[-1], 12456)
        self.assertEqual(v.snapshot()['counter_universe'], 1)

    def test_reject_invalid_four_part(self):
        with self.assertRaises(ValueError):
            DataManager.validate_logical_address(['11 0 0 0 0 0', 2, 'cubic'])
        with self.assertRaises(ValueError):
            DataManager.validate_logical_address(['11 0 0 0 0 0', 2, 'cubic', True])
        with self.assertRaises(ValueError):
            DataManager.validate_logical_address(['11 0 0 0 0 0', -1, 'cubic', 0])

    def test_logical_event_storage_no_recording_id_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm = DataManager(base_dir=Path(tmp))
            pole = dm.save_pole_function('3 0 0 0 0 0',
                {'name': 'cubic_offset', 'version': 1, 'params': {'scale': 1}})
            ref = pole['id']
            self.assertTrue(ref.startswith('pi_'))
            self.assertEqual(dm.load_pole_function('3 0 0 0 0 0', ref)['definition']['name'], 'cubic_offset')
            with self.assertRaises(KeyError):
                dm.load_pole_function('11 0 0 0 0 0', ref)
            outgoing = ['11 0 0 0 0 0', 2, ref, 180]
            incoming = ['11 0 0 0 0 0', 2, ref, 181]
            a = dm.save_logical_command(outgoing, 'outward', direction='away', counter_universe=2)
            b = dm.save_logical_command(incoming, 'inward', direction='toward', counter_universe=2)
            self.assertNotEqual(a['id'], b['id'])
            self.assertNotIn('recording_id', a)
            self.assertNotIn('definition', a)
            self.assertNotIn('cubic_offset', str(a))
            self.assertEqual(a['address'], outgoing)
            self.assertEqual(a['counter_universe'], 2)
            dm2 = DataManager(base_dir=Path(tmp))
            self.assertEqual(dm2.resolve_logical_command(
                outgoing, direction='away', counter_universe=2)['command'], 'outward')
            self.assertEqual(dm2.resolve_logical_command(
                incoming, direction='toward', counter_universe=2)['command'], 'inward')
            self.assertEqual(len(dm2.load_logical_commands('11 0 0 0 0 0')), 2)
            self.assertEqual(dm2.coordinate_location('11 0 0 0 0 0')[1].relative_to(tmp),
                             Path('coordinate_data/0/0/0/0/0.json'))

    def test_function_definition_only_at_pole(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm = DataManager(base_dir=Path(tmp))
            pole = dm.save_pole_function('3 0 0 0 0 0',
                    {'name': 'cubic_offset', 'version': 1, 'params': {'scale': 1}})
            ref = pole['id']
            with self.assertRaisesRegex(ValueError, 'opaque reference'):
                dm.save_logical_command(['4 0 0 0 0 0', 1, {'name':'cubic_offset'}, 5],
                                        'bad', direction='away')
            with self.assertRaisesRegex(ValueError, 'pole-local'):
                dm.save_logical_command(['4 0 0 0 0 0', 1, 'cubic_offset', 5],
                                        'bad', direction='away')
            dm.save_logical_command(['4 0 0 0 0 0', 1, ref, 5], 'first', direction='away')
            dm.save_logical_command(['11 0 0 0 0 0', 2, ref, 6], 'second', direction='away')
            self.assertFalse(dm.get_objects_at_coordinate('4 0 0 0 0 0', 'pole_function'))
            self.assertFalse(dm.get_objects_at_coordinate('11 0 0 0 0 0', 'pole_function'))
            self.assertEqual(len(dm.get_objects_at_coordinate('3 0 0 0 0 0', 'pole_function')), 1)
            self.assertEqual(dm.resolve_logical_command(
                ['11 0 0 0 0 0', 2, ref, 6], direction='away')['command'], 'second')

    def test_collision_detected_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm = DataManager(base_dir=Path(tmp))
            addr = ['6 0 0 0 0 0', 0, 'linear_offset', 0]
            dm.save_logical_command(addr, 'first', direction='linear')
            dm.save_logical_command(addr, 'second', direction='linear')
            with self.assertRaisesRegex(ValueError, 'Ambiguous'):
                dm.resolve_logical_command(addr)

    def test_nested_mutation_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm = DataManager(base_dir=Path(tmp))
            nested = [{'activation_id': 'L1', 'k': 2, 'leg': 'toward'}]
            pole = dm.save_pole_function('3 0 0 0 0 0', {'name': 'cubic_offset'})
            dm.save_logical_command(['11 0 0 0 0 0', nested, pole['id'], 99], 'x', direction='away')
            nested[0]['k'] = 8
            stored = dm.load_logical_commands('11 0 0 0 0 0', path_universe=99)
            self.assertEqual(stored[0]['address'][1][0]['k'], 2)

    def test_bridge_virtual_and_standalone_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            oais = OaisTerminal(
                counter=Counter(load_state=False, save_path=Path(tmp)/'standalone.json'),
                data_manager=DataManager(base_dir=Path(tmp)/'data'))
            oais.attach_host('3 0 0 0 0 0')
            oais.virtual_command('hold')
            oais.observe_event({'type':'command','source':'base','value':'help',
                'coordinate_before':'3 0 0 0 0 0', 'coordinate_after':'4 0 0 0 0 0',
                'universe_after':0})
            self.assertEqual(oais.virtual_counter.logical_address()[0], '3 0 0 0 0 0')
            oais.virtual_counter.set_projection('5 0 0 0 0 0', path_universe=123)
            self.assertIn('path_universe 123', oais.virtual_command('status'))
            oais.virtual_command('sync')
            self.assertEqual(oais.virtual_counter.logical_address()[-1], 0)
            self.assertEqual(oais.virtual_counter.logical_address()[0], '4 0 0 0 0 0')
            oais.detach_host()
            self.assertEqual(oais.counter, oais.standalone_counter)

    def test_old_sticky_note_readback_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm = DataManager(base_dir=Path(tmp))
            counter = Counter(load_state=False, save_path=Path(tmp)/'counter.json')
            rec = StickyNoteEngine(counter=counter, data_manager=dm)
            commands = [(0, 'forwards', 1), (1, 'one', 2), (2, 'two', 3),
                        (3, 'three', 4), (4, 'four', 5),
                        (5, 'backwards', 4), (4, 'help', 5)]
            rec.start(metadata={'scope': 'base'})
            for pos, cmd, nxt in commands:
                rec.record_event({'source':'base','value':cmd,
                    'coordinate_before':f'{pos} 0 0 0 0 0',
                    'coordinate_after':f'{nxt} 0 0 0 0 0'})
            note = rec.save_reference('legacy')
            read = StickyNoteEngine(counter=counter, data_manager=DataManager(base_dir=Path(tmp)))
            _, path = read.load_path(note['id'])
            self.assertEqual([e['value'] for e in path], [c[1] for c in commands])
            self.assertEqual(len(dm.get_coordinate_node('4 0 0 0 0 0')['commands']), 2)

    def test_existing_v2_records_still_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm = DataManager(base_dir=Path(tmp))
            dm.save_object('9 0 0 0 0 0', 'logical_command', 'legacy-v2', {
                'schema_version':2, 'command':'old',
                'address':['9 0 0 0 0 0', 1, 'linear_offset'],
                'universe':4, 'direction':'away', 'recording_id':'old-id',
            })
            self.assertEqual(dm.load_logical_commands('9 0 0 0 0 0', counter_universe=4)[0]['command'], 'old')
            self.assertEqual(dm.load_logical_commands('9 0 0 0 0 0', path_universe=4), [])

if __name__ == '__main__':
    unittest.main()
