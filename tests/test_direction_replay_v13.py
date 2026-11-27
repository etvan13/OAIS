from history_assertions import steps
"""v13 contracts: source-command sign and terminal-private, read-only Replay."""
import json
from pathlib import Path
import tempfile
import unittest

from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.Commands.Replay.Replay import Replay
from oais.Commands.Replay.ReplayEngine import ReplayEngine
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager


class DirectionReplayV13Tests(unittest.TestCase):
    def make(self, directory, *, saved=False, terminal_id='base'):
        folder = Path(directory) / 'Data'
        return OaisTerminal(
            counter=Counter(load_state=saved, save_path=folder / 'current_coordinate.json'),
            data_manager=DataManager(base_dir=folder), terminal_id=terminal_id)

    @staticmethod
    def tick(term, command, success=True):
        before = term.host_counter.get_counters()
        before_u = term.host_counter.universes
        if command == 'backwards':
            term.host_counter.decrement()
        else:
            term.host_counter.increment()
        term.observe_event({
            'type':'command', 'source':'base', 'value':command, 'success':success,
            'coordinate_before':before, 'coordinate_after':term.host_counter.get_counters(),
            'universe_before':before_u, 'universe_after':term.host_counter.universes,
        })

    def test_unknown_forward_after_backward_cancels_without_changing_function(self):
        with tempfile.TemporaryDirectory() as folder:
            term = self.make(folder)
            term.attach_host('0 0 0 0 0 0')
            term.process_command('function k**2')
            for text in ('help','help','help','backwards','forward','help'):
                self.tick(term, text, success=text != 'forward')
            self.assertEqual(term.virtual_counter.coordinate, '16 0 0 0 0 0')
            self.assertEqual(term.navigator_engine.compact_state()['functions'], [
                {'f':'k**2','k':4,'direction':1}])
            self.assertEqual(term.host_counter.get_counters(), '4 0 0 0 0 0')
            self.assertEqual(json.loads(term.virtual_state_path.read_text())['functions'][0]['k'], 4)

    def test_root_at_zero_is_preserved_for_rebound_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            term = self.make(folder)
            term.attach_host('0 0 0 0 0 0')
            term.process_command('function k**2')
            self.tick(term,'help'); self.tick(term,'backwards')
            self.assertEqual(term.virtual_counter.coordinate,'0 0 0 0 0 0')
            self.assertEqual(term.navigator_engine.compact_state()['functions'], [
                {'f':'k**2','k':0,'direction':-1}])
            recovered=self.make(folder)
            recovered.attach_host(term.host_counter.get_counters(),term.host_counter.universes)
            self.tick(recovered,'invalid command',success=False)
            self.assertEqual(recovered.virtual_counter.coordinate,'1 0 0 0 0 0')
            self.assertEqual(recovered.navigator_engine.compact_state()['functions'], [
                {'f':'k**2','k':1,'direction':1}])

    def test_nested_zero_is_preserved_then_parent_resumes_on_extra_backwards(self):
        with tempfile.TemporaryDirectory() as folder:
            term=self.make(folder); term.attach_host('3 0 0 0 0 0')
            term.process_command('function k**3')
            for _ in range(3): self.tick(term,'help')
            term.process_command('function k**2')
            self.tick(term,'help'); self.tick(term,'backwards')
            self.assertEqual(term.virtual_counter.coordinate,'30 0 0 0 0 0')
            self.assertEqual(len(term.navigator_engine.layers),2)
            self.tick(term,'help')
            self.assertEqual(term.virtual_counter.coordinate,'31 0 0 0 0 0')
            self.tick(term,'backwards'); self.tick(term,'backwards')
            self.assertEqual(term.virtual_counter.coordinate,'11 0 0 0 0 0')
            self.assertEqual(term.navigator_engine.compact_state()['functions'], [
                {'f':'k**3','k':2,'direction':-1}])

    def test_replay_list_choose_and_coordinate_history_is_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            term=self.make(folder);term.attach_host('0 0 0 0 0 0')
            term.process_command('function k**2')
            term.process_command('sticky start')
            self.tick(term,'help'); self.tick(term,'backwards'); self.tick(term,'forward',success=False)
            term.process_command('function k**3')
            self.tick(term,'help')
            term.process_command('sticky stop')
            term.process_command('sticky save quadratic_roundtrip')
            note=term.sticky_note.get_note('quadratic_roundtrip')
            self.assertEqual([e['command'] for e in steps(term.sticky_note, note)], [
                'sticky start','help','backwards','forward','function k**3','help','sticky stop'])
            self.assertEqual([e['op'] for e in steps(term.sticky_note, note)], [
                'none','auto_forward','auto_back','auto_forward','push','auto_forward','none'])
            # Browsing must not read coordinate blocks; selecting a note must.
            from unittest.mock import patch
            with patch.object(term.data_manager, 'load_command_block', side_effect=AssertionError('unexpected coordinate read')):
                self.assertIn('quadratic_roundtrip', term.process_command('replay list').output)
            term.process_command('sticky start')
            before_recording=term.sticky_note.get_path()
            before_nav=term.navigator_engine.snapshot()
            before_oais=term.standalone_counter.get_counters()
            self.assertIn('1. quadratic_roundtrip',term.process_command('replay list').output)
            output=term.process_command('replay 1').output
            self.assertIn('1. [BASE] help', output)
            self.assertIn('3. [BASE] forward [failed]', output)
            self.assertNotIn('[OAIS] function k**3', output)
            self.assertIn('4. [BASE] help', output)
            self.assertIn('[4/4]', output)
            self.assertEqual(term.standalone_counter.get_counters(),before_oais)
            self.assertEqual(term.navigator_engine.snapshot(),before_nav)
            self.assertIn('0/4',term.process_command('replay reset').output)
            self.assertIn('1. [BASE] help',term.process_command('replay next').output)
            self.assertIn('COORDINATE TRACE',term.process_command('replay trace quadratic_roundtrip').output)
            self.assertEqual(term.navigator_engine.snapshot(), before_nav)
            self.assertEqual(term.sticky_note.get_path()[:len(before_recording)], before_recording)
            self.assertEqual([e['value'] for e in term.sticky_note.get_path()[len(before_recording):]],
                             ['replay list','replay 1','replay reset','replay next','replay trace quadratic_roundtrip'])
            term.process_command('sticky clear')
            # New terminal instance can read the exact same private notes.
            reader=ReplayEngine(DataManager(base_dir=Path(folder)/'Data'),terminal_id='base')
            self.assertIn('4 events',reader.load(note['id']))
            self.assertIn('[4/4]', reader.all())

    def test_interactive_replay_menu(self):
        with tempfile.TemporaryDirectory() as folder:
            term=self.make(folder);term.attach_host('0 0 0 0 0 0')
            term.process_command('sticky start');self.tick(term,'help');term.process_command('sticky stop')
            term.sticky_note.save_reference('test_menu')
            printed=[]
            choices=iter(['list','1','exit'])
            result=Replay(term).run(input_func=lambda prompt:next(choices),print_func=printed.append)
            self.assertIn('Returning',result)
            output='\n'.join(printed)
            self.assertIn('SAVED STICKY NOTES',output)
            self.assertIn('test_menu',output)
            self.assertIn('1. [BASE] help',output)

if __name__ == '__main__': unittest.main()
