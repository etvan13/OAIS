"""Audit v13 BLAKE2b chain semantics and overlapping stationary note blocks."""
import tempfile
import unittest
from pathlib import Path
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager
from oais.utils.virtual_counter import seed_path_universe, evolve_path_universe

class UniverseChainAudit(unittest.TestCase):
    def make(self, root, name='A'):
        dm = DataManager(base_dir=Path(root) / 'Data')
        term = OaisTerminal(counter=Counter(load_state=False, save_path=Path(root) / (name+'.json')), data_manager=dm, terminal_id=name)
        term.attach_host('0 0 0 0 0 0')
        return term, dm

    @staticmethod
    def base_event(term, command, delta=1):
        before = term.host_counter.get_counters()
        universe = term.host_counter.universes
        if delta > 0:
            for _ in range(delta): term.host_counter.increment()
        elif delta < 0:
            for _ in range(-delta): term.host_counter.decrement()
        term.observe_event({'type':'command','source':'base','value':command,
            'coordinate_before':before,'coordinate_after':term.host_counter.get_counters(),
            'universe_before':universe,'universe_after':term.host_counter.universes,
            'success':command!='forward'})

    def test_zero_movement_oais_events_are_chained_at_same_coordinate(self):
        with tempfile.TemporaryDirectory() as root:
            t, dm = self.make(root)
            t.process_command('sticky start')
            t.process_command('function k**2')
            t.process_command('virtual')
            t.process_command('function k**3')
            t.process_command('sticky save zero_moves')
            note = t.sticky_note.get_note('zero_moves')
            self.assertEqual([e['command'] for e in note['plan']], ['function k**2','virtual','function k**3'])
            blocks = dm.get_coordinate_node('0 0 0 0 0 0')['command_blocks']
            self.assertEqual(len(blocks),3)
            self.assertEqual(len({b['universe'] for b in blocks}),3)
            expected = seed_path_universe('0 0 0 0 0 0', note['id'])
            self.assertEqual(blocks[0]['universe'], f'{expected:032x}')
            # Independently regenerate the exact event-chain values for the
            # three stationary OAIS events, including the no-op inspection.
            linear = ['0 0 0 0 0 0', [], 'k']
            quadratic = ['0 0 0 0 0 0', [{'f':'k**2','k':0,'direction':1}], 'k**2']
            nested = ['0 0 0 0 0 0', [{'f':'k**2','k':0,'direction':1},
                     {'f':'k**3','k':0,'direction':1}], 'k**3']
            operations = [('function k**2','open',linear,quadratic),
                          ('virtual','none',quadratic,quadratic),
                          ('function k**3','push',quadratic,nested)]
            for i,(command,op,before,after) in enumerate(operations):
                self.assertEqual(blocks[i]['command'],command)
                self.assertEqual(blocks[i]['universe'],f'{expected:032x}')
                expected=evolve_path_universe(expected,before,after,
                                              f'event:{i}:{command}:{op}')

    def test_multiple_notes_same_coordinate_do_not_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as root:
            t, dm = self.make(root)
            for label in ['one','two']:
                t.process_command('sticky start')
                t.process_command('virtual')
                t.process_command('function k**2') if label=='one' else t.process_command('function k**3')
                t.process_command('sticky save '+label)
                if label=='one':
                    t.navigator_engine.reset_to_linear('0 0 0 0 0 0')
            notes=[t.sticky_note.get_note(label) for label in ['one','two']]
            blocks=dm.get_coordinate_node('0 0 0 0 0 0')['command_blocks']
            self.assertEqual(len(blocks),4)
            self.assertEqual(len({b['universe'] for b in blocks}),4)
            self.assertNotEqual(notes[0]['id'],notes[1]['id'])
            for note in notes:
                seed=seed_path_universe(note['start'],note['id'])
                self.assertEqual(dm.load_command_block('0 0 0 0 0 0',f'{seed:032x}')['command'],'virtual')

    def test_digest_is_history_sensitive_and_repeatable(self):
        start='0 0 0 0 0 0'
        h=seed_path_universe(start,'fixed-note-id')
        a=[start,[], 'k']
        b=['1 0 0 0 0 0',[], 'k']
        x=evolve_path_universe(h,a,b,'event:0:help:auto_forward')
        y=evolve_path_universe(h,a,b,'event:0:backwards:auto_back')
        self.assertEqual(x,evolve_path_universe(h,a,b,'event:0:help:auto_forward'))
        self.assertNotEqual(x,y)
        self.assertNotEqual(x,evolve_path_universe(seed_path_universe(start,'other-note'),a,b,'event:0:help:auto_forward'))
        self.assertNotEqual(x,evolve_path_universe(h,a,b,'event:1:help:auto_forward'))
        self.assertNotEqual(evolve_path_universe(x,b,a,'event:1:backwards:auto_back'),h)

if __name__ == '__main__': unittest.main()
