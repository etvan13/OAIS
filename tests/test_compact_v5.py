"""New compact coordinate storage is separate from legacy v4 replay."""
from pathlib import Path
import tempfile
import unittest
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager


class CompactV5Tests(unittest.TestCase):
    def make(self, location):
        dm = DataManager(base_dir=Path(location)/'Data')
        t = OaisTerminal(counter=Counter(load_state=False, save_path=Path(location)/'counter.json'),
                         data_manager=dm, terminal_id='deep_base')
        t.attach_host('0 0 0 0 0 0')
        t.recording_scope='all'
        self.assertIn('Recording started', t.process_command('sticky start').output)
        return t, dm

    @staticmethod
    def event(t, text, movement, success=True):
        before=t.host_counter.get_counters(); u=t.host_counter.universes
        if movement > 0:
            for _ in range(movement): t.host_counter.increment()
        elif movement < 0:
            for _ in range(-movement): t.host_counter.decrement()
        t.observe_event({'type':'command','source':'base','value':text,
                         'coordinate_before':before,'coordinate_after':t.host_counter.get_counters(),
                         'universe_before':u,'universe_after':t.host_counter.universes,
                         'success':success})

    def test_reverse_and_revisits_are_compact_and_keyed(self):
        with tempfile.TemporaryDirectory() as tmp:
            t, dm=self.make(tmp)
            for text, move, status in [('hello',1,True),('forwards',1,True),
                                       ('backwards',-1,True),('test',1,False),('hmm',1,False)]:
                self.event(t, text, move, status)
            self.assertIn('Saved ',t.process_command('sticky save test_new1').output)
            note=t.sticky_note.get_note('test_new1')
            self.assertEqual(set(note), {'id', 'title', 'start', 'end', 'start_state', 'functions', 'blocks', 'plan'})
            self.assertEqual([f['direction'] for f in note['functions']],[1,-1])
            self.assertEqual(note['blocks'],7)
            self.assertEqual(note['end'],'3 0 0 0 0 0')
            nodes={str(i)+' 0 0 0 0 0':dm.get_coordinate_node(str(i)+' 0 0 0 0 0') for i in range(4)}
            blocks=[b for node in nodes.values() for b in node['command_blocks']]
            self.assertEqual(len(blocks),7)
            self.assertEqual(len({b['universe'] for b in blocks}),7)
            self.assertEqual([(b['command'],b.get('function')) for b in blocks],
                [('sticky start',0),('hello',None),('forwards',None),('test',0),('backwards',1),('hmm',None),('sticky save test_new1',None)])
            self.assertTrue(all('address' not in b and 'navigation' not in b and 'id' not in b for b in blocks))
            self.assertFalse(any('logical_command' in node.get('objects',{}) for node in nodes.values()))
            self.assertEqual(dm.load_command_block('2 0 0 0 0 0', blocks[4]['universe'])['command'], 'backwards')
            self.assertTrue((Path(tmp)/'Data/terminal_data/deep_base/sticky_notes.json').is_file())
            self.assertEqual(dm.get_objects_at_coordinate('0 0 0 0 0 0','sticky_note'),[])

    def test_stationary_commands_have_distinct_histories(self):
        with tempfile.TemporaryDirectory() as tmp:
            t,dm=self.make(tmp)
            for name in ('one','two','three'):
                self.event(t,name,0)
            self.assertIn('Saved ',t.process_command('sticky save paused').output)
            blocks=dm.get_coordinate_node('0 0 0 0 0 0')['command_blocks']
            self.assertEqual(len({b['universe'] for b in blocks}),5)
            self.assertTrue(all(b['step']==0 for b in blocks))

    def test_duplicate_coordinate_key_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm=DataManager(base_dir=Path(tmp))
            key='a'*32
            dm.save_command_block('0 0 0 0 0 0','first',key)
            with self.assertRaises(ValueError):
                dm.save_command_block('0 0 0 0 0 0','second',key)
            self.assertEqual(dm.load_command_block('0 0 0 0 0 0',key)['command'],'first')
            self.assertTrue(dm.delete_command_block('0 0 0 0 0 0',key))
            with self.assertRaises(KeyError):
                dm.load_command_block('0 0 0 0 0 0',key)

if __name__=='__main__': unittest.main()
