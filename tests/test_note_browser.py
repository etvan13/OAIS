"""Metadata browsing, pagination, cache invalidation and typed replay."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from oais.Commands.Navigator.NavigatorEngine import NavigatorEngine
from oais.Commands.Replay.Replay import Replay
from oais.Commands.Replay.ReplayEngine import ReplayEngine
from oais.Commands.StickyNote.StickyNote import StickyNote
from oais.Commands.StickyNote.StickyNoteEngine import StickyNoteEngine
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager


class NoteBrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dm = DataManager(Path(self.tmp.name) / 'data')
        self.counter = Counter(load_state=False, persist=False)
        self.reader = StickyNoteEngine(counter=self.counter, data_manager=self.dm, terminal_id='base')
        self.replay = ReplayEngine(self.dm, 'base')
        self.terminal = SimpleNamespace(data_manager=self.dm, replay_engine=self.replay, sticky_note=self.reader)
        self.ui = Replay(self.terminal)

    def seed(self, kind, notes, terminal='base'):
        name = self.reader._collection_name(kind)
        self.dm.save_terminal_data(terminal, name, {'notes': notes})

    def command_notes(self, count):
        return [{'id': f'cmd-{i}', 'title': f'Command note {i}', 'blocks': 1,
                 'start': '0 0 0 0 0 0', 'end': '1 0 0 0 0 0',
                 'start_state': {'coordinate': '0 0 0 0 0 0'},
                 'plan': [{'command': f'command {i}', 'source': 'base', 'op': 'none'}]}
                for i in range(1, count + 1)]

    def conversation(self, title='Spacecraft research', count=3):
        nav = NavigatorEngine(); nav.open_pole('k**3')
        recorder = StickyNoteEngine(counter=self.counter, data_manager=self.dm, terminal_id='base',
                                    navigation_provider=nav.snapshot)
        recorder.start(metadata={'storage': 'data'})
        for i in range(count):
            recorder.record_event({'type': 'conversation', 'value': {'user': f'question {i}', 'assistant': f'answer {i}'}})
        return recorder.save(title)

    def test_browse_and_missing_lookup_never_scan_coordinates(self):
        self.seed('command', self.command_notes(45))
        self.conversation()
        self.seed('command', self.command_notes(1), terminal='other')
        with patch.object(self.dm, 'list_sticky_pointers', side_effect=AssertionError('legacy scan')), \
             patch.object(self.dm, 'list_objects', side_effect=AssertionError('legacy scan')), \
             patch.object(self.dm, 'find_sticky_pointer', side_effect=AssertionError('legacy lookup')), \
             patch.object(self.dm, 'find_object', side_effect=AssertionError('legacy lookup')), \
             patch.object(self.dm, 'load_block', side_effect=AssertionError('path load')), \
             patch.object(self.dm, 'get_coordinate_node', side_effect=AssertionError('coordinate read')):
            result = self.reader.browse_notes('command', page=2)
            self.assertEqual((result['total'], result['pages'], len(result['items'])), (45, 3, 20))
            self.assertEqual(result['items'][0]['number'], 21)
            self.assertNotIn('plan', result['items'][0])
            self.assertEqual(self.reader.browse_notes()['total'], 46)
            self.assertEqual(self.reader.search_notes('spacecraft')['total'], 1)
            self.assertEqual(len(self.replay.available()), 45)
            self.assertIn('Page 1/3', self.ui._run('list commands'))
            self.assertIn('Page 2/3', self.ui._run('more'))
            self.assertIn('Page 1/3', self.ui._run('prev'))
            self.assertIn('Spacecraft research', StickyNote(self.terminal).process_command('search spacecraft'))
            self.assertIn('Saved Sticky Note not found', self.ui.run('missing title'))
            with self.assertRaises(KeyError):
                self.reader.get_note('missing title')
            with self.assertRaises(KeyError):
                self.reader.load_path('missing title')

    def test_rank_search_and_empty_results(self):
        self.seed('conversation', [
            {'id': '1', 'title': 'AI for spacecraft'},
            {'id': '2', 'title': 'Spacecraft AI tools'},
            {'id': '3', 'title': 'Spacecraft AI'},
            {'id': '4', 'title': 'Optics'},
        ])
        result = self.reader.search_notes('SPACECRAFT AI', 'conversation')
        self.assertEqual([n['id'] for n in result['items']], ['3', '2', '1'])
        self.assertEqual(self.reader.search_notes('3')['items'][0]['id'], '3')
        self.assertEqual(self.reader.search_notes('not present')['pages'], 0)
        self.assertEqual(self.reader.browse_notes('conversation', page=3)['items'], [])
        for kwargs in ({'page': 0}, {'limit': 0}, {'limit': 201}, {'limit': True}):
            with self.assertRaises(ValueError): self.reader.browse_notes(**kwargs)

    def test_cache_reuses_collection_and_refreshes_on_external_write(self):
        self.seed('command', self.command_notes(45))
        with patch.object(self.dm, 'load_terminal_data', wraps=self.dm.load_terminal_data) as read:
            self.reader.browse_notes('command')
            self.reader.browse_notes('command', page=2)
            self.reader.search_notes('note 3', 'command')
            self.assertEqual(read.call_count, 1)
            another_dm = DataManager(self.dm.base_dir)
            another_dm.save_terminal_data('base', 'sticky_notes_commands', {'notes': self.command_notes(46)})
            result = self.reader.browse_notes('command')
            self.assertEqual(result['total'], 46)
            self.assertEqual(read.call_count, 2)
            result['items'][0]['title'] = 'Mutated by caller'
            self.assertEqual(self.reader.get_note('cmd-1')['title'], 'Command note 1')
            self.dm.terminal_data_location('base', 'sticky_notes_commands').unlink()
            self.assertEqual(self.reader.browse_notes('command')['total'], 0)

    def test_selection_uses_displayed_page_and_stable_id(self):
        self.seed('command', self.command_notes(45))
        self.ui._run('list commands 2')
        # The catalog changes after display. Number 21 still points to cmd-21.
        self.seed('command', self.command_notes(45)[1:])
        self.assertIn('command 21', self.ui._run('21'))
        self.assertEqual(self.replay.note['id'], 'cmd-21')
        with self.assertRaises(ValueError): self.replay.load('1')
        self.assertIn('Page 1/3', self.ui._run('list commands'))
        self.assertIn('command 2', self.ui._run('1'))
        self.assertEqual(self.replay.note['id'], 'cmd-2')

    def test_only_selected_conversation_loaded_and_display_is_stepwise(self):
        first = self.conversation('Spacecraft research', 3)
        self.conversation('Optics notes', 4)
        self.seed('command', self.command_notes(1))
        with patch.object(self.dm, 'load_block', wraps=self.dm.load_block) as read:
            self.assertIn('Spacecraft research', self.ui._run('list conversations'))
            self.assertIn('Spacecraft research', self.ui._run('search spacecraft'))
            self.assertEqual(read.call_count, 0)
            output = self.ui._run('1')
            self.assertEqual(read.call_count, 3)  # verify only the selected trajectory
            self.assertEqual(self.replay.note['id'], first['id'])
            self.assertIn('question 0', output)
            self.assertNotIn('question 1', output)
            self.assertIn('question 1', self.ui._run('next'))
            self.assertIn('question 2', self.ui._run('all'))
            self.assertEqual(read.call_count, 3)
            self.assertIn('conversation', self.ui._run('data ' + first['start']))
            self.assertEqual(self.replay.cursor, 3)
            self.assertEqual(len(self.replay.visible_events()), 3)  # data survives host-only filter
        self.assertIn('1. Command note 1', self.ui._run('list commands'))
        self.assertIn('command 1', self.ui._run('1'))

    def test_external_read_is_stateless_and_type_aware(self):
        first = self.conversation('Spacecraft research', 2)
        result = self.replay.browse('conversation', query='spacecraft', limit=1)
        self.assertIsNone(self.replay.browser_result)
        item = result['items'][0]
        self.assertEqual(item['id'], first['id'])
        note, events = self.replay.read_note(item['id'], block_type=item['type'])
        self.assertEqual(note['start'], item['start'])
        self.assertEqual(note['end'], item['end'])
        self.assertEqual([e['value']['user'] for e in events], ['question 0', 'question 1'])
        self.assertIsNone(self.replay.note)
        self.assertEqual(self.replay.cursor, 0)

    def test_legacy_reads_are_explicit(self):
        recorder = StickyNoteEngine(counter=self.counter, data_manager=self.dm, terminal_id='base')
        recorder.start()
        recorder.record_event({'type': 'command', 'source': 'base', 'value': 'help',
                               'coordinate_before': '0 0 0 0 0 0', 'coordinate_after': '1 0 0 0 0 0'})
        legacy = recorder.save('legacy only')
        self.assertEqual(self.reader.browse_notes()['total'], 0)
        self.assertEqual(self.reader.list_notes(), [])
        with self.assertRaises(KeyError): self.reader.load_path(legacy['id'])
        self.assertEqual(self.reader.load_path(legacy['id'], include_legacy=True)[1][0]['value'], 'help')
        self.assertTrue(any(n['id'] == legacy['id'] for n in self.reader.list_notes(include_legacy=True)))


if __name__ == '__main__':
    unittest.main()
