"""Real two-process bridge protects the v10 checkpoint writer."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

try:
    import pexpect
except ImportError:
    pexpect = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(pexpect and os.name == 'posix', 'PTY/pexpect required')
class RealV10Bridge(unittest.TestCase):
    def test_worker_owns_checkpoint_and_sticky_start_context(self):
        with tempfile.TemporaryDirectory() as d:
            child = pexpect.spawn(sys.executable,
                [str(ROOT / 'main.py'), '--start', '3 0 0 0 0 0', '--data-dir', d],
                cwd=str(ROOT), encoding='utf-8', timeout=20)
            try:
                child.expect('BASE > ')
                child.sendline('oais navigator')
                child.expect('Navigator> ')
                child.sendline('function k**2')
                child.expect('Navigator> ')
                child.sendline('exit')
                child.expect('BASE > ')
                for _ in range(3):
                    child.sendline('help')
                    child.expect('BASE > ')
                state_path=Path(d)/'virtual_coordinate.json'
                checkpoint=json.loads(state_path.read_text())
                self.assertFalse((Path(d)/'host_coordinate.json').exists())
                self.assertNotIn('navigation',checkpoint)
                self.assertEqual(checkpoint['source'],'base')
                self.assertEqual(checkpoint['source_coordinate'],'6 0 0 0 0 0')
                self.assertEqual(checkpoint['coordinate'],'12 0 0 0 0 0')
                self.assertEqual(checkpoint['functions'],[
                    {'f':'k**2','k':3,'direction':1}])
                # Invoking OAIS only moves its own normal Counter.
                child.sendline('oais help')
                child.expect('BASE > ')
                new_checkpoint=json.loads(state_path.read_text())
                self.assertEqual(new_checkpoint['coordinate'],'12 0 0 0 0 0')
                self.assertEqual(new_checkpoint['source_coordinate'],'6 0 0 0 0 0')
                child.sendline('oais sticky start')
                child.expect('BASE > ')
                child.sendline('help')
                child.expect('BASE > ')
                child.sendline('oais sticky stop')
                child.expect('BASE > ')
                child.sendline('oais sticky save integration')
                child.expect('BASE > ')
                notes=json.loads((Path(d)/'terminal_data'/'base'/'sticky_notes.json').read_text())['notes']
                note=notes[-1]
                self.assertEqual(note['start_state']['coordinate'],'12 0 0 0 0 0')
                self.assertEqual(note['start_state']['functions'],[
                    {'f':'k**2','k':3,'direction':1}])
                self.assertEqual(note['start_state']['source'],'base')
                self.assertEqual(note['end'],'19 0 0 0 0 0')
                child.sendline('exit')
                child.expect(pexpect.EOF)
            finally:
                child.close(force=True)


@unittest.skipUnless(pexpect and os.name == 'posix', 'PTY/pexpect required')
class RealV10Standalone(unittest.TestCase):
    def test_main_standalone_owns_virtual_json_and_restores_k(self):
        with tempfile.TemporaryDirectory() as d:
            def launch():
                return pexpect.spawn(sys.executable, [str(ROOT/'main.py'), '--mode',
                    'oais', '--data-dir', d], cwd=str(ROOT), encoding='utf-8', timeout=20)
            first=launch()
            path=Path(d)/'virtual_coordinate.json'
            try:
                first.expect('OAIS > ')
                first.sendline('navigator function k**2')
                first.expect('OAIS > ')
                first.sendline('help')
                first.expect('OAIS > ')
                state=json.loads(path.read_text())
                self.assertEqual(state['source'],'oais')
                self.assertEqual(state['functions'][0]['k'],1)
                self.assertEqual(state['coordinate'],'2 0 0 0 0 0')
                first.sendline('exit')
                first.expect(pexpect.EOF)
            finally:
                first.close(force=True)
            second=launch()
            try:
                second.expect('OAIS > ')
                self.assertIn('f(k)=k**2 | k=1',second.before)
                second.sendline('help')
                second.expect('OAIS > ')
                state=json.loads(path.read_text())
                self.assertEqual(state['functions'][0]['k'],2)
                self.assertEqual(state['coordinate'],'5 0 0 0 0 0')
                second.sendline('exit')
                second.expect(pexpect.EOF)
            finally:
                second.close(force=True)
