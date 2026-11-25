"""BASE-visible shortcut must reach Navigator without discarding active layers."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
try:
    import pexpect
except ImportError:
    pexpect = None

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipIf(pexpect is None or sys.platform == 'win32', 'PTY needs POSIX and pexpect')
class FunctionAliasPTYTests(unittest.TestCase):
    def test_oais_function_shortcut_nests_after_three_base_ticks(self):
        with tempfile.TemporaryDirectory() as folder:
            child = pexpect.spawn(sys.executable,
                [str(ROOT / 'main.py'), '--data-dir', folder],
                cwd=str(ROOT), encoding='utf-8', timeout=20)
            try:
                child.expect('BASE > ')
                def send(cmd):
                    child.sendline(cmd)
                    child.expect('BASE > ')
                    return child.before
                self.assertIn('Opened pole', send('oais function k**2'))
                for _ in range(3):
                    send('help')
                self.assertIn('Opened pole', send('oais function k**3'))
                self.assertIn('k**2 (k=3, out) > k**3 (k=0, out)',
                              send('oais virtual'))
                state_path=Path(folder) / 'virtual_coordinate.json'
                state=json.loads(state_path.read_text())
                self.assertEqual(state['functions'], [
                    {'f':'k**2','k':3,'direction':1},
                    {'f':'k**3','k':0,'direction':1}])
                self.assertEqual(state['coordinate'], '9 0 0 0 0 0')
                send('forwards')
                self.assertIn('Virtual [FREE]: 10 0 0 0 0 0', send('oais virtual'))
                self.assertFalse(list((Path(folder) / 'coordinate_data').rglob('*.json')))
                child.sendline('exit')
                child.expect(pexpect.EOF)
            finally:
                child.close(force=True)

if __name__=='__main__':
    unittest.main()
