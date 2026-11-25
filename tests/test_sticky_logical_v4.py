"""Saved four-part Sticky Notes reconstruct by math, without next pointers."""
from pathlib import Path
import tempfile
import unittest

from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.Commands.StickyNote.StickyNoteEngine import StickyNoteEngine
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager


def setup(directory, start='0 0 0 0 0 0'):
    dm = DataManager(base_dir=Path(directory)/'data')
    term = OaisTerminal(counter=Counter(load_state=False, save_path=Path(directory)/'state.json'),
                        data_manager=dm, legacy_pole_storage=True)
    term.attach_host(start)
    term.recording_scope = 'all'
    return term, dm


def base(term, cmd='help'):
    before = term.host_counter.get_counters()
    u_before = term.host_counter.universes
    term.host_counter.increment()
    after = term.host_counter.get_counters()
    term.observe_event({'type': 'command', 'source': 'base', 'value':cmd,
                        'coordinate_before':before, 'coordinate_after':after,
                        'universe_before':u_before,
                        'universe_after':term.host_counter.universes, 'success':True})
    return after


def command(term, text):
    result = term.process_command(text, connected=False)
    assert result.handled, text
    if text == "sticky start":
        term.sticky_note.session_metadata["storage_version"] = 4
    assert not result.output.startswith('OAIS command error'), result.output
    return result.output


def saved(term, name):
    command(term, 'sticky stop')
    message = command(term, 'sticky save '+name)
    assert message.startswith('Saved '), message
    return term.sticky_note.get_note(name)


class LogicalStickyNoteTests(unittest.TestCase):
    def test_cubic_storage_and_roundtrip_through_reopened_manager(self):
        with tempfile.TemporaryDirectory() as folder:
            term, dm = setup(folder)
            command(term, 'navigator open cubic')
            command(term, 'sticky start')
            for _ in range(3): base(term)
            command(term, 'navigator turn')
            for _ in range(2): base(term)
            note = saved(term, 'cubic-note')
            self.assertEqual(note['schema_version'], 4)
            self.assertEqual(note['start'][0], '0 0 0 0 0 0')
            self.assertEqual(note['after'][0], '4 1 0 0 0 0')
            self.assertEqual(note['event_count'], 6)
            self.assertNotIn('events', note)
            self.assertNotIn('event_refs', note)
            other = StickyNoteEngine(data_manager=DataManager(base_dir=Path(folder)/'data'))
            _, events = other.load_path(note['id'])
            self.assertEqual([e['value'] for e in events],
                             ['help','help','help','navigator turn','help','help'])
            self.assertEqual([e['logical_before'][0].split()[0] for e in events],
                             ['0','1','8','27','8','27'])
            self.assertEqual([e['logical_after'][0].split()[0] for e in events],
                             ['1','8','27','8','27','4'])
            self.assertNotEqual(events[2]['logical_before'][-1], events[4]['logical_before'][-1])
            records = dm.load_logical_commands('8 0 0 0 0 0')
            self.assertEqual(len(records), 2)
            for r in records:
                self.assertNotIn('recording_id', r)
                self.assertNotIn('next', r)
                self.assertNotIn('definition', r)
            with self.assertRaises(KeyError):
                dm.load_pole_function('8 0 0 0 0 0', events[2]['logical_before'][2])

    def test_nested_pole_saves_open_child_first_step_and_parent_resumes(self):
        with tempfile.TemporaryDirectory() as folder:
            term, dm = setup(folder)
            command(term, 'navigator open cubic')
            command(term, 'sticky start')
            for _ in range(3): base(term)
            command(term, 'navigator turn')
            command(term, 'navigator child backward')
            base(term); base(term)
            command(term, 'navigator turn')
            base(term); base(term); base(term)
            note = saved(term, 'nested')
            _, path = StickyNoteEngine(data_manager=DataManager(base_dir=Path(folder)/'data')).load_path(note['id'])
            self.assertEqual([int(e['logical_after'][0].split()[0]) for e in path],
                             [1,8,27,8,8,7,6,7,6,5,4])
            self.assertEqual(path[4]['navigation']['op'], 'push')
            self.assertEqual(len(path[4]['logical_after'][1]), 2)
            # BASE commands following an explicit turn now advance the
            # newest active function outward (+1), not in prior leg direction.
            self.assertEqual(len(path[-2]['logical_after'][1]), 2)
            self.assertEqual(len(path[-1]['logical_after'][1]), 2)
            self.assertEqual(path[-2]['logical_after'][1][0]['step'], 2)
            self.assertEqual(len(dm.list_objects('pole_function')), 2)

    def test_constant_all_commands_share_real_but_have_distinct_universes(self):
        with tempfile.TemporaryDirectory() as folder:
            term, dm = setup(folder)
            command(term, 'navigator open constant')
            command(term, 'sticky start')
            for _ in range(3): base(term)
            command(term, 'navigator turn')
            base(term); base(term)
            note = saved(term, 'constant')
            _, path = term.sticky_note.load_path(note['id'])
            self.assertEqual(len(path), 6)
            self.assertEqual({e['logical_before'][0] for e in path}, {'0 0 0 0 0 0'})
            self.assertEqual(len({e['logical_before'][3] for e in path}), 6)
            objects = dm.get_objects_at_coordinate('0 0 0 0 0 0', 'logical_command')
            self.assertEqual(len(objects), 6)
            self.assertEqual(len({o['id'] for o in objects}), 6)

    def test_paused_identical_address_repeated_and_two_independent_notes(self):
        with tempfile.TemporaryDirectory() as folder:
            term, dm = setup(folder)
            command(term, 'navigator open constant')
            command(term, 'navigator pause')
            command(term, 'sticky start')
            for c in ('help','greetings','other'): base(term,c)
            first = saved(term,'first')
            command(term, 'sticky start')
            for c in ('one','two','three'): base(term,c)
            second = saved(term,'second')
            self.assertNotEqual(first['route_seed'],second['route_seed'])
            reader = StickyNoteEngine(data_manager=DataManager(base_dir=Path(folder)/'data'))
            a = reader.load_path(first['id'])[1]
            b = reader.load_path(second['id'])[1]
            self.assertEqual([e['value'] for e in a], ['help','greetings','other'])
            self.assertEqual([e['value'] for e in b], ['one','two','three'])
            self.assertEqual({tuple(str(v) for v in e['logical_before']) for e in a},
                             {tuple(str(v) for v in e['logical_before']) for e in b})
            self.assertEqual(len({obj['id'] for obj in dm.get_objects_at_coordinate(
                '0 0 0 0 0 0', 'logical_command')}), 6)

    def test_note_before_pole_open_pause_manual_turn_sync(self):
        with tempfile.TemporaryDirectory() as folder:
            term, dm = setup(folder)
            command(term, 'sticky start')
            command(term, 'navigator open cubic')
            base(term); base(term)
            command(term, 'navigator pause')
            base(term); base(term)  # no virtual movement
            command(term, 'navigator away')
            command(term, 'navigator turn')
            command(term, 'navigator toward')
            command(term, 'virtual sync')
            base(term)
            note = saved(term, 'controls')
            reader = StickyNoteEngine(data_manager=DataManager(base_dir=Path(folder)/'data'))
            _, path = reader.load_path(note['id'])
            ops = [e['navigation']['op'] for e in path]
            self.assertEqual(ops, ['open','auto_forward','auto_forward','pause','none','none','away','turn','toward','sync','none'])
            self.assertEqual(path[1]['logical_after'][0], '1 0 0 0 0 0')
            self.assertEqual(path[6]['logical_after'][0], '27 0 0 0 0 0')
            self.assertEqual(path[9]['logical_after'][0], '4 0 0 0 0 0')
            self.assertEqual(path[-1]['logical_after'][0], '5 0 0 0 0 0')

    def test_note_started_mid_nested_excursion_rehydrates_both_poles(self):
        with tempfile.TemporaryDirectory() as folder:
            term, dm = setup(folder)
            command(term,'navigator open cubic')
            for _ in range(3): base(term)
            command(term,'navigator turn')  # parent real 8, toward
            command(term,'navigator child backward')  # child real 7, away k1
            command(term,'sticky start')  # Note begins mid-child, not at any original pole
            base(term)  # child real 6, away k2
            command(term,'navigator turn')  # child real 7, toward
            base(term)  # child closes at real 8
            base(term)  # parent resumes to real 1
            note=saved(term,'mid_nested')
            self.assertEqual(len(note['initial_state']['layers']),2)
            self.assertTrue(all('definition' not in f for f in note['initial_state']['layers']))
            reader = StickyNoteEngine(data_manager=DataManager(base_dir=Path(folder)/'data'))
            _, events = reader.load_path(note['id'])
            self.assertEqual([int(e['logical_after'][0].split()[0]) for e in events],
                             [7,8,27,4])
            self.assertEqual(len(dm.list_objects('pole_function')),2)

    def test_rollover_storage_uses_separate_counter_and_path_universe(self):
        with tempfile.TemporaryDirectory() as folder:
            term, dm = setup(folder,'59 59 59 59 59 59')
            command(term,'navigator open linear')
            command(term,'sticky start')
            base(term)
            command(term,'navigator turn')
            note = saved(term,'rollover')
            _, events = StickyNoteEngine(data_manager=DataManager(base_dir=Path(folder)/'data')).load_path(note['id'])
            self.assertEqual(events[0]['logical_after'][0], '0 0 0 0 0 0')
            self.assertEqual(events[0]['logical_counter_universe_after'],1)
            self.assertEqual(events[1]['logical_after'][0], '59 59 59 59 59 59')
            self.assertEqual(events[1]['logical_counter_universe_after'],0)
            self.assertNotEqual(events[0]['logical_before'][3],events[0]['logical_after'][3])
            objects=dm.get_objects_at_coordinate('0 0 0 0 0 0','logical_command')
            self.assertEqual(objects[0]['counter_universe'],1)

    def test_failed_host_command_and_meta_transition_survive_readback(self):
        with tempfile.TemporaryDirectory() as folder:
            term, dm = setup(folder)
            command(term,'navigator open cubic')
            command(term,'sticky start')
            term.observe_event({
                'type':'transition','source':'meta','value':'oais',
                'from':'base','to':'oais',
                'coordinate_before':'0 0 0 0 0 0',
                'coordinate_after':'0 0 0 0 0 0',
                'universe_before':0,'universe_after':0,
            })
            term.observe_event({
                'type':'command','source':'base','value':'unknown_command',
                'coordinate_before':'0 0 0 0 0 0',
                'coordinate_after':'1 0 0 0 0 0',
                'universe_before':0,'universe_after':0,'success':False,
            })
            note=saved(term,'failed_meta')
            _, path=StickyNoteEngine(data_manager=dm).load_path(note['id'])
            self.assertEqual([e['value'] for e in path],['oais','unknown_command'])
            self.assertEqual(path[0]['type'],'transition')
            self.assertEqual((path[0]['from'],path[0]['to']),('base','oais'))
            self.assertFalse(path[1]['success'])
            self.assertEqual(path[1]['logical_after'][0],'1 0 0 0 0 0')
            self.assertEqual(path[1]['navigation']['op'],'auto_forward')

    def test_corrupt_event_fails_not_guess_and_no_command_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            term, dm = setup(folder)
            command(term,'navigator open cubic')
            command(term,'sticky start')
            base(term,'help'); base(term,'greetings')
            note = saved(term,'remove')
            addr = note['start']
            event_id = term.sticky_note._logical_event_id(note['route_seed'], 0, addr,
                                    note['start_counter_universe'], note['start_direction'])
            dm.delete_object(addr[0], 'logical_command',event_id)
            with self.assertRaisesRegex(ValueError,'Missing or ambiguous'):
                StickyNoteEngine(data_manager=dm).load_path(note['id'])

    def test_commit_rollback_retains_cache_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            term, dm = setup(folder)
            command(term,'navigator open cubic')
            command(term,'sticky start')
            base(term)
            real_save = dm.save_terminal_data
            def failing_save(terminal_id, collection, data):
                if collection == 'sticky_notes':
                    raise OSError('synthetic failure')
                return real_save(terminal_id,collection,data)
            dm.save_terminal_data = failing_save
            with self.assertRaises(OSError):
                term.sticky_note.save_reference('broken')
            self.assertEqual(dm.get_objects_at_coordinate('0 0 0 0 0 0','logical_command'),[])
            self.assertEqual(len(term.sticky_note.get_path()),1)
            self.assertTrue(term.sticky_note.active)


if __name__ == '__main__':
    unittest.main()
