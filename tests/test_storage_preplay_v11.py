from history_assertions import steps
"""v11 compact navigation persistence and self-contained future Replay inputs."""
import json
from pathlib import Path
import tempfile
import unittest

from oais.Commands.Navigator.NavigatorEngine import NavigatorEngine
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager
from oais.utils.virtual_counter import (VirtualCounter, address_to_integer,
                                        integer_to_address)


class StorageReadinessV11Tests(unittest.TestCase):
    def make(self, directory, *, saved=False):
        root = Path(directory) / 'Data'
        return OaisTerminal(
            counter=Counter(load_state=saved, save_path=root / 'current_coordinate.json'),
            data_manager=DataManager(base_dir=root), terminal_id='base')

    @staticmethod
    def tick(term, command='help'):
        before, universe = term.host_counter.get_counters(), term.host_counter.universes
        if command == 'backwards':
            term.host_counter.decrement()
        else:
            term.host_counter.increment()
        term.observe_event({'type':'command', 'source':'base', 'value':command,
                            'success':True, 'coordinate_before':before,
                            'coordinate_after':term.host_counter.get_counters(),
                            'universe_before':universe,
                            'universe_after':term.host_counter.universes})

    def test_nested_reverse_note_reconstructs_from_coordinates(self):
        with tempfile.TemporaryDirectory() as d:
            t = self.make(d)
            t.attach_host('3 0 0 0 0 0')
            t.process_command('navigator function k**3')
            for _ in range(3): self.tick(t)
            t.process_command('navigator function k**2')
            for _ in range(2): self.tick(t)
            t.process_command('sticky start')
            for _ in range(2): self.tick(t, 'backwards')
            self.tick(t, 'forwards')
            t.process_command('navigator function 2*k')
            self.tick(t, 'help')
            self.tick(t, 'backwards')
            self.tick(t, 'backwards')
            t.process_command('sticky stop')
            note = t.sticky_note.save_reference('nested+reverse')
            self.assertEqual(note['start_state']['pole'], '3 0 0 0 0 0')
            self.assertEqual(note['start_state']['coordinate'], '34 0 0 0 0 0')
            self.assertEqual(note['start_state']['functions'], [
                {'f':'k**3','k':3,'direction':1}, {'f':'k**2','k':2,'direction':1}])
            self.assertEqual(note['end'], '30 0 0 0 0 0')
            self.assertEqual(note['blocks'], len(steps(t.sticky_note,note)))
            self.assertTrue(any(s['op']=='push' and s.get('f')=='2*k' for s in steps(t.sticky_note,note)))
            self.assertTrue(any(s['op']=='auto_back' for s in steps(t.sticky_note,note)))
            self.assertNotIn('pi_', json.dumps(note))
            self.assertNotIn('navigation', note)
            self.assertNotIn('origin', note)
            self.assertNotIn('transitions', note)
            stored = t.data_manager.load_terminal_data('base','sticky_notes')
            self.assertEqual(stored['version'],4)
            self.assertEqual(stored['notes'][-1],note)
            _, reconstructed = t.sticky_note.load_path(note['id'])
            end = reconstructed[-1]
            self.assertEqual(end['coordinate_after'], note['end'])
            self.assertEqual([(layer['step'],layer['leg']) for layer in end['logical_after'][1]],[(3,'away'),(0,'toward')])
            node = t.data_manager.get_coordinate_node('34 0 0 0 0 0')
            for block in node.get('command_blocks',[]):
                self.assertTrue(set(block).issubset({'command','universe','counter_universe','failed','source','op','f','delta','anchor','target','target_universe','source_origin','transition'}))
                self.assertNotIn('event', block)
                self.assertNotIn('title', block)
                self.assertNotIn('note', block)

    def test_compact_file_restores_nested_k_directions_and_next_delta(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make(d)
            t.attach_host('3 0 0 0 0 0')
            t.process_command('navigator function k**3')
            for _ in range(3): self.tick(t)
            t.process_command('navigator function k**2')
            for _ in range(2): self.tick(t)
            self.tick(t, 'backwards')  # child k=1, returning, real=31
            statepath=Path(d)/'Data'/'virtual_coordinate.json'
            data=json.loads(statepath.read_text())
            self.assertEqual(data['coordinate'],'31 0 0 0 0 0')
            self.assertEqual(data['pole'],'3 0 0 0 0 0')
            self.assertEqual(data['functions'][-1],{'f':'k**2','k':1,'direction':-1})
            self.assertNotIn('navigation', data)
            self.assertNotIn('path_universe', data)
            self.assertNotIn('entry_seed',data)
            self.assertNotIn('automatic',data)
            restored=self.make(d,saved=True)
            restored.attach_host(t.host_counter.get_counters(),t.host_counter.universes)
            self.assertEqual(restored.navigator_engine.compact_state()['functions'], data['functions'])
            self.tick(restored,'backwards')  # quad k=0 remains reversible
            self.assertEqual(restored.virtual_counter.coordinate,'30 0 0 0 0 0')
            self.assertEqual(restored.navigator_engine.compact_state()['functions'], [
                {'f':'k**3','k':3,'direction':1}, {'f':'k**2','k':0,'direction':-1}])

    def test_no_duplicate_host_cache_after_connected_observation(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make(d)
            t.attach_host('3 0 0 0 0 0')
            self.tick(t)
            state=json.loads((Path(d)/'Data'/'virtual_coordinate.json').read_text())
            self.assertEqual(state['source_coordinate'],'4 0 0 0 0 0')
            self.assertFalse((Path(d)/'Data'/'host_coordinate.json').exists())

    def test_legacy_v10_checkpoint_migrates_on_next_save(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make(d)
            t.attach_host('3 0 0 0 0 0')
            t.process_command('navigator function k**2')
            self.tick(t)
            import json as module
            old=t.navigator_engine.snapshot()
            path=Path(d)/'Data'/'virtual_coordinate.json'
            payload=t.navigation_context()
            payload.pop('pole',None)
            payload['mode']='free'; payload['automatic']=True
            payload['navigation']=old
            path.write_text(module.dumps(payload))
            t2=self.make(d)
            t2.attach_host(t.host_counter.get_counters(),t.host_counter.universes)
            self.tick(t2)
            migrated=json.loads(path.read_text())
            self.assertEqual(migrated['functions'][0]['k'],2)
            self.assertEqual(migrated['pole'],'3 0 0 0 0 0')
            self.assertNotIn('navigation',migrated)

    def test_pole_universe_overflow_roundtrip_and_invalid_coordinate_detected(self):
        v=VirtualCounter('59 59 59 59 59 59',2)
        n=NavigatorEngine(v)
        n.open_pole('k**2')
        n.away();n.away()
        saved=n.portable_state(n.snapshot(),source='oais',
                    source_coordinate='59 59 59 59 59 59',source_universes=2)
        self.assertEqual(saved['pole_universes'],2)
        roundtrip=NavigatorEngine(VirtualCounter())
        roundtrip.restore_portable(saved)
        self.assertEqual(roundtrip.compact_state()['functions'],saved['functions'])
        self.assertEqual(roundtrip.virtual.coordinate,'3 0 0 0 0 0')
        self.assertEqual(roundtrip.virtual.universe,3)
        corrupted=dict(saved)
        corrupted['coordinate']='4 0 0 0 0 0'
        with self.assertRaises(ValueError):
            NavigatorEngine(VirtualCounter()).restore_portable(corrupted)

if __name__=='__main__': unittest.main()
