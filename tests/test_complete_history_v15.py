"""Source-filtered Replay and complete coordinate history, without new fields."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.Commands.Replay.Replay import Replay
from oais.Commands.Replay.ReplayEngine import ReplayEngine
from oais.Commands.Navigator.Navigator import Navigator
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager
import test_storage_preplay_v11


class CompleteHistoryTests(unittest.TestCase):
    def make(self, root, source='base'):
        dm = DataManager(base_dir=Path(root)/'Data')
        t = OaisTerminal(counter=Counter(load_state=False, save_path=Path(root)/'counter.json'),
                         data_manager=dm, terminal_id=source)
        if source != 'oais_standalone':
            t.attach_host('0 0 0 0 0 0', source=source if source != 'base' else 'base')
        return t, dm

    @staticmethod
    def host(t, command='help'):
        t.observe_event({'type':'command','source':t.source_name,'value':command,
                         'success':True})

    def test_full_history_same_storage_and_filtered_replay(self):
        with tempfile.TemporaryDirectory() as root:
            t,dm = self.make(root)
            t.recording_scope = 'host'  # older Meta configuration cannot exclude events
            for cmd in ('sticky start','function k**2','virtual','navigator status'):
                t.process_command(cmd)
            self.host(t)
            t.process_command('function k**3')
            self.host(t,'greetings')
            t.process_command('replay list')
            self.assertIn('Saved', t.process_command('sticky save complete').output)
            note=t.sticky_note.get_note('complete')
            expected=['sticky start','function k**2','virtual','navigator status','help',
                      'function k**3','greetings','replay list','sticky save complete']
            self.assertEqual([e['command'] for e in note['plan']],expected)
            blocks=[]
            for path in dm.coordinate_dir.rglob('*.json'):
                for node in json.loads(path.read_text()).values():
                    blocks.extend(node.get('command_blocks',[]))
            self.assertCountEqual([b['command'] for b in blocks],expected)
            self.assertEqual(len({b['universe'] for b in blocks}),len(expected))
            self.assertTrue(all(set(b)<= {'command','universe','function','counter_universe','step','failed','source'} for b in blocks))
            self.assertEqual(test_storage_preplay_v11.StorageReadinessV11Tests.reconstruct_math_from_private_note(note)['real'],note['end'])
            before=t.navigator_engine.snapshot(); count=t.counter.get_counters()
            out=t.process_command('replay complete').output
            self.assertIn('1. [BASE] help',out); self.assertIn('2. [BASE] greetings',out)
            self.assertNotIn('[OAIS]',out)
            out=t.process_command('replay full complete').output
            self.assertIn('1. [OAIS] sticky start',out)
            self.assertIn('9. [OAIS] sticky save complete',out)
            self.assertIn('0/2', t.process_command('replay view host').output)
            self.assertIn('[1/2]',t.process_command('replay next').output)
            self.assertIn('[2/2]',t.process_command('replay all').output)
            self.assertIn('navigator status',t.process_command('replay trace complete').output)
            self.assertEqual(t.navigator_engine.snapshot(),before)
            self.assertEqual(t.counter.get_counters(),count)
            self.assertEqual(t.sticky_note.get_note('complete'),note)

    def test_failed_save_retained_and_retry_preserves_attempt(self):
        with tempfile.TemporaryDirectory() as root:
            t,dm=self.make(root)
            t.process_command('sticky start');self.host(t)
            with patch.object(dm,'save_terminal_data',side_effect=OSError('disk full')):
                self.assertIn('Could not save',t.process_command('sticky save retry').output)
            self.assertTrue(t.sticky_note.active)
            self.assertFalse(t.sticky_note.get_path()[-1]['success'])
            self.host(t,'greetings')
            self.assertIn('Saved',t.process_command('sticky save retry').output)
            plan=t.sticky_note.get_note('retry')['plan']
            self.assertTrue(plan[2]['failed']);self.assertEqual(plan[2]['command'],'sticky save retry')
            self.assertNotIn('failed',plan[-1]);self.assertEqual(plan[-1]['command'],'sticky save retry')
            self.assertEqual(len(plan),5)

    def test_stop_is_boundary_and_later_save_does_not_invent_a_move(self):
        with tempfile.TemporaryDirectory() as root:
            t,_=self.make(root,'counterless');t.process_command('sticky start');self.host(t,'ping')
            t.process_command('sticky stop');self.host(t,'echo outside')
            self.assertIn('Saved',t.process_command('sticky save stopped').output)
            note=t.sticky_note.get_note('stopped')
            self.assertEqual([e['command'] for e in note['plan']],['sticky start','ping','sticky stop'])
            self.assertEqual(note['end'],'1 0 0 0 0 0')
            self.assertIn('[COUNTERLESS] ping',t.process_command('replay stopped').output)

    def test_menu_inputs_and_standalone_notes(self):
        with tempfile.TemporaryDirectory() as root:
            t,_=self.make(root,'oais_standalone'); t.process_command('sticky start')
            choices=iter(['function k**2','status','exit'])
            Navigator(t).run(input_func=lambda _:next(choices),print_func=lambda _:None)
            t.process_command('help');t.process_command('sticky save standalone')
            self.assertIn('No host commands',t.process_command('replay standalone').output)
            self.assertIn('navigator exit',t.process_command('replay full standalone').output)
            t.process_command('sticky start'); choices=iter(['view host','load standalone','replay all','exit'])
            Replay(t).run(input_func=lambda _:next(choices),print_func=lambda _:None)
            t.process_command('sticky save menu')
            self.assertEqual([e['command'] for e in t.sticky_note.get_note('menu')['plan']],
                             ['sticky start','replay view host','replay load standalone','replay all','replay exit','sticky save menu'])

# Verify actual connected processes, the interactive Replay menu and scrollback.
import os
import sys
try:
    import pexpect
except ImportError:
    pexpect = None

@unittest.skipUnless(pexpect and os.name == 'posix', 'PTY requires POSIX and pexpect')
class CompleteHistoryPTYTests(unittest.TestCase):
    def test_direct_and_switched_inputs_share_history(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/'Data'
            child=pexpect.spawn(sys.executable,[str(root/'main.py'),'--data-dir',str(data),
                '--base-data-dir',str(Path(folder)/'Base_Data')],cwd=str(root),encoding='utf-8',timeout=12)
            try:
                child.expect_exact('BASE > ')
                def send(command,prompt='BASE > '):
                    child.sendline(command);child.expect_exact(prompt)
                    self.assertNotIn('\x1b[?1049h',child.before)
                    return child.before
                send('oais sticky start');send('oais function k**2');send('oais virtual')
                send('oais','OAIS > ');send('navigator status','OAIS > ');send('return')
                send('help');send('oais sticky save mixed')
                note=json.loads((data/'terminal_data/base/sticky_notes.json').read_text())['notes'][-1]
                self.assertEqual([e['command'] for e in note['plan']],['sticky start','function k**2','virtual','oais','navigator status','return','help','sticky save mixed'])
                state=(data/'virtual_coordinate.json').read_bytes()
                send('oais replay','Replay> ')
                out=send('mixed','Replay> ');self.assertIn('1. [BASE] help',out);self.assertNotIn('[OAIS]',out)
                send('replay view full','Replay> ')
                self.assertIn('[OAIS] sticky start',send('replay all','Replay> '))
                send('exit');self.assertEqual((data/'virtual_coordinate.json').read_bytes(),state)
                child.sendline('exit');child.expect(pexpect.EOF)
            finally:
                child.close(force=True)
