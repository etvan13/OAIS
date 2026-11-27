"""Coordinate-backed command histories and independent conversation browsing."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oais.Commands.Navigator.NavigatorEngine import NavigatorEngine
from oais.Commands.Replay.ReplayEngine import ReplayEngine
from oais.Commands.StickyNote.StickyNoteEngine import StickyNoteEngine
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager
from oais.utils.virtual_counter import VirtualCounter, seed_path_universe


class CoordinateHistoryTests(unittest.TestCase):
    def make(self, folder):
        dm = DataManager(base_dir=Path(folder) / 'Data')
        term = OaisTerminal(counter=Counter(load_state=False, persist=False),
                            data_manager=dm, terminal_id='base')
        term.attach_host('0 0 0 0 0 0')
        return term, dm

    def record(self, term):
        term.process_command('sticky start')
        term.process_command('function k**2')
        term.observe_event({'type':'command','source':'base','value':'help'})
        term.process_command('virtual')
        term.process_command('function k**3')
        term.observe_event({'type':'command','source':'base','value':'help'})
        term.observe_event({'type':'command','source':'base','value':'backwards','movement':-1})
        result = term.process_command('sticky save route').output
        self.assertIn('Saved', result)
        return term.sticky_note.get_note('route')

    def test_reopen_and_missing_block_no_private_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            t, dm = self.make(folder)
            note = self.record(t)
            self.assertNotIn('plan', note)
            self.assertNotIn('functions', note)
            self.assertNotIn('coordinate_list', note['start_state'])
            fresh = ReplayEngine(DataManager(base_dir=dm.base_dir), terminal_id='base')
            with patch.object(fresh.data_manager, 'load_command_block', side_effect=AssertionError('browsing payloads')):
                self.assertIn('route', fresh.list_notes())
            fresh.load('route')
            self.assertEqual(len(fresh.events), note['blocks'])
            self.assertEqual(fresh.events[-1]['coordinate_after'], note['end'])
            self.assertIn('1. [BASE] help', fresh.all())
            self.assertNotIn('function', fresh.reset() + fresh.all())
            fresh.set_view('full')
            self.assertIn('function k**3', fresh.all())
            seed = seed_path_universe(note['start'], note['id'], counter_universe=note.get('start_universe',0))
            dm.delete_command_block(note['start'], f'{seed:032x}', counter_universe=note.get('start_universe',0))
            with self.assertRaisesRegex(ValueError,'Missing or ambiguous'):
                fresh.load('route')

    def test_terminal_block_tampering_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            t, dm = self.make(folder)
            note = self.record(t)
            _, events = t.sticky_note.load_path('route')
            last = events[-1]
            coord, history = last['logical_before'][0], last['logical_before'][3]
            _, path = dm.coordinate_location(coord)
            data = json.loads(path.read_text())
            block = next(b for b in data[coord]['command_blocks'] if b['universe']==f'{history:032x}')
            block['command'] = 'tampered last command'
            dm._write_json(path, data)
            with self.assertRaisesRegex(ValueError,'endpoint or history'):
                t.sticky_note.load_path('route')

    def test_hold_and_sync_reconstruct_without_executing(self):
        with tempfile.TemporaryDirectory() as folder:
            t, dm = self.make(folder)
            t.process_command('sticky start')
            t.process_command('virtual hold')
            t.observe_event({'type':'command','source':'base','value':'help'})
            t.process_command('virtual sync')
            self.assertIn('Saved', t.process_command('sticky save held').output)
            _, events = t.sticky_note.load_path('held')
            host = next(e for e in events if e['source']=='base')
            self.assertEqual(host['coordinate_before'], host['coordinate_after'])
            self.assertEqual(events[-1]['coordinate_after'],'1 0 0 0 0 0')

    def test_conversation_browsing_does_not_read_payloads(self):
        with tempfile.TemporaryDirectory() as folder:
            dm = DataManager(base_dir=Path(folder)/'Data')
            for i in range(23):
                v=VirtualCounter(); v.observe_host(f'{i} 0 0 0 0 0')
                nav=NavigatorEngine(v); nav.open_pole('k')
                recorder=StickyNoteEngine(counter=Counter(load_state=False,persist=False), data_manager=dm,
                                         navigation_provider=nav.snapshot, terminal_id='base')
                recorder.start(metadata={'storage':'data'})
                for j in range(2):
                    recorder.record_event({'type':'conversation','value':{'user':f'Question {i}-{j}','assistant':f'Answer {i}-{j}'}})
                note=recorder.save_reference(f'Conversation {i:02}')
                self.assertNotIn('plan',note)
            reader=ReplayEngine(dm,terminal_id='base')
            with patch.object(dm,'load_block',side_effect=AssertionError('browsing read a payload')):
                page=reader.browse('conversation',page=2)
                self.assertEqual(page['total'],23)
                self.assertEqual(len(page['items']),3)
                self.assertEqual(reader.browse('conversation',query='Conversation 22')['total'],1)
            with patch.object(dm,'load_block',wraps=dm.load_block) as reads:
                reader.load('Conversation 22',block_type='conversation')
                self.assertEqual(reads.call_count,2)
                self.assertIn('Question 22-0',reader.next())
                self.assertNotIn('Question 22-1',reader.reset()+reader.next())

if __name__=='__main__': unittest.main()
