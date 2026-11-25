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

    @staticmethod
    def reconstruct_math_from_private_note(note):
        """Test-only simulation: no DataManager reads, saved blocks, or command IO.

        This verifies the note has enough data for *future* Replay, but is not
        itself a Replay implementation or command execution.
        """
        engine = NavigatorEngine(VirtualCounter())
        engine.restore_portable(note['start_state'])
        context = note['start_state']
        source = context['source']
        source_absolute = address_to_integer(context['source_coordinate'],
                                             context['source_universes'])
        for event in note['plan']:
            delta = event.get('delta', 0)
            if event['source'] == source:
                source_absolute += delta
                position, universe = integer_to_address(source_absolute)
                engine.virtual.observe_host(position, universe)
            op = event['op']
            if op in ('open', 'push', 'child'):
                if event.get('anchor') is not None:
                    engine.reset_to_linear(event['anchor'], event.get('anchor_universes',0))
                if op == 'open':
                    engine.open_pole(event['f'])
                elif op == 'push':
                    engine.push_function(event['f'])
                else:
                    engine.open_child(event['f'])
            elif op == 'auto':
                engine.advance_automatic()
            elif op == 'auto_back':
                engine.advance_host_direction(-1)
            elif op == 'auto_forward':
                engine.advance_host_direction(1)
            elif op in ('away', 'toward', 'turn', 'pause', 'resume'):
                getattr(engine, op)()
            elif op == 'hold':
                engine.virtual.hold(); engine.pause()
            elif op == 'sync':
                engine.reset_to_linear(event['target'], event.get('target_universes',0))
            elif op == 'none':
                if delta and event['source'] == source and not engine.layers and engine.virtual.mode == 'free':
                    engine.advance_linear(delta)
            else:
                raise AssertionError('Unrecognized stored navigation operation '+op)
        return engine.compact_state()

    def test_nested_reverse_note_reconstructs_from_private_json_only(self):
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
            self.assertEqual(note['blocks'], len(note['plan']))
            self.assertTrue(any(s['op']=='push' and s.get('f')=='2*k' for s in note['plan']))
            self.assertTrue(any(s['op']=='auto_back' for s in note['plan']))
            self.assertNotIn('pi_', json.dumps(note))
            self.assertNotIn('navigation', note)
            self.assertNotIn('origin', note)
            self.assertNotIn('transitions', note)
            stored = t.data_manager.load_terminal_data('base','sticky_notes')
            self.assertEqual(stored['version'],3)
            self.assertEqual(stored['notes'][-1],note)
            # No coordinate reads are needed to reconstruct the mathematical
            # endpoint, even though public command blocks remain in place.
            end = self.reconstruct_math_from_private_note(json.loads(json.dumps(note)))
            self.assertEqual(end['real'], note['end'])
            self.assertEqual(end['functions'], [
                {'f':'k**3','k':3,'direction':1}, {'f':'k**2','k':0,'direction':-1}])
            node = t.data_manager.get_coordinate_node('34 0 0 0 0 0')
            for block in node.get('command_blocks',[]):
                self.assertTrue(set(block).issubset({'command','universe','function',
                    'counter_universe','step','failed','source'}))
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
