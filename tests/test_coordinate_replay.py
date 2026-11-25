"""Read-only playback tests for v4 coordinate-addressed Sticky Notes."""
from pathlib import Path
import tempfile
import unittest

from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager
from oais.Commands.Replay.ReplayEngine import ReplayEngine


def run(term, text):
    result = term.process_command(text)
    if 'OAIS command error:' in result.output:
        raise AssertionError(result.output)
    return result.output


def base(term, cmd='help'):
    before = term.host_counter.get_counters()
    u = term.host_counter.universes
    term.host_counter.increment()
    term.observe_event({'type': 'command', 'source': 'base', 'value': cmd,
                        'coordinate_before': before,
                        'coordinate_after': term.host_counter.get_counters(),
                        'universe_before': u,
                        'universe_after': term.host_counter.universes,
                        'success': True})


class CoordinateReplayTests(unittest.TestCase):
    def make(self, folder):
        term = OaisTerminal(
            counter=Counter(load_state=False, save_path=Path(folder)/'state.json'),
            data_manager=DataManager(base_dir=Path(folder)/'data'), legacy_pole_storage=True)
        term.attach_host('0 0 0 0 0 0')
        term.recording_scope = 'all'
        return term

    def save_cubic(self, term):
        run(term, 'navigator open cubic')
        run(term, 'sticky start')
        term.sticky_note.session_metadata['storage_version'] = 4
        for _ in range(3): base(term)
        run(term, 'navigator turn')
        for _ in range(2): base(term)
        run(term, 'sticky stop')
        run(term, 'sticky save cubic_replay')

    def test_replay_steps_and_trace_do_not_touch_live_navigation(self):
        with tempfile.TemporaryDirectory() as folder:
            term = self.make(folder)
            self.save_cubic(term)
            before = term.navigator_engine.snapshot()
            host_before = term.host_counter.get_counters()
            oais_before = term.standalone_counter.get_counters()
            self.assertIn('5 events', run(term, 'replay load cubic_replay'))
            first = run(term, 'replay next 2')
            self.assertIn('0 0 0 0 0 0 -> 1 0 0 0 0 0', first)
            self.assertIn('1 0 0 0 0 0 -> 8 0 0 0 0 0', first)
            self.assertIn('[2/5]', first)
            self.assertIn('[5/5]', run(term, 'replay all'))
            self.assertIn('End of replay', run(term, 'replay next'))
            self.assertIn('0/5', run(term, 'replay reset'))
            self.assertIn('COORDINATE TRACE: cubic_replay', run(term, 'navigator trace cubic_replay'))
            self.assertEqual(before, term.navigator_engine.snapshot())
            self.assertEqual(host_before, term.host_counter.get_counters())
            # Each OAIS replay *input* advances the independent OAIS counter;
            # replay itself never moves BASE or the active Navigator.
            self.assertNotEqual(oais_before, term.standalone_counter.get_counters())

    def test_read_from_fresh_data_manager_and_missing_event_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            term = self.make(folder)
            self.save_cubic(term)
            reader = ReplayEngine(DataManager(base_dir=Path(folder)/'data'))
            self.assertIn('5 events', reader.load('cubic_replay'))
            self.assertIn('27 0 0 0 0 0', reader.all())
            note, events = term.sticky_note.load_path('cubic_replay')
            event_id = term.sticky_note._logical_event_id(
                note['route_seed'], 0, events[0]['logical_before'],
                events[0]['logical_counter_universe_before'],
                events[0]['logical_direction_before'])
            term.data_manager.delete_object(events[0]['logical_before'][0], 'logical_command', event_id)
            with self.assertRaisesRegex(ValueError, 'Missing or ambiguous'):
                reader.load('cubic_replay')
            self.assertEqual(reader.cursor, 5)  # unsuccessful load preserves prior session

    def test_convenience_replay_and_bad_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            term = self.make(folder)
            self.save_cubic(term)
            message = run(term, 'replay cubic_replay')
            self.assertIn('[5/5]', message)
            self.assertIn('Step count must be a positive integer',
                          term.process_command('replay next 0').output)
            self.assertIn('Saved Sticky Note not found', run(term, 'replay missing_note'))
            self.assertIn('Replay unloaded', run(term, 'replay clear'))
            self.assertIn('No replay loaded', term.process_command('replay next').output)


if __name__ == '__main__':
    unittest.main()
