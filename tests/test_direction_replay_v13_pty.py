"""End-to-end BASE -> OAIS Replay menu and signed tick behavior."""
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

@unittest.skipIf(pexpect is None or sys.platform == 'win32', 'PTY requires POSIX and pexpect')
class DirectionReplayV13PTYTests(unittest.TestCase):
    def test_base_replay_menu_and_unknown_forward_tick(self):
        with tempfile.TemporaryDirectory() as folder:
            child=pexpect.spawn(sys.executable, [str(ROOT/'main.py'), '--data-dir',folder],
                               cwd=str(ROOT), encoding='utf-8', timeout=25)
            try:
                child.expect('BASE > ')
                def send(command):
                    child.sendline(command)
                    child.expect('BASE > ')
                    return child.before
                self.assertIn('Opened pole',send('oais function k**2'))
                send('oais sticky start')
                send('help')
                send('help')
                send('backwards')
                send('forward')  # BASE rejects spelling but still increments.
                checkpoint=Path(folder)/'virtual_coordinate.json'
                state=json.loads(checkpoint.read_text())
                self.assertEqual(state['functions'], [{'f':'k**2','k':2,'direction':1}])
                self.assertEqual(state['coordinate'],'4 0 0 0 0 0')
                self.assertIn('Recording stopped',send('oais sticky stop'))
                self.assertIn('Saved',send('oais sticky save base_menu'))
                before=checkpoint.read_bytes()
                child.sendline('oais replay')
                child.expect('Replay> ')
                self.assertIn('base_menu',child.before)
                child.sendline('1')
                child.expect('Replay> ')
                self.assertIn('1. [BASE] help',child.before)
                self.assertIn('3. [BASE] backwards',child.before)
                self.assertIn('4. [BASE] forward [failed]',child.before)
                child.sendline('exit')
                child.expect('BASE > ')
                self.assertEqual(checkpoint.read_bytes(), before)
                self.assertIn('4. [BASE] forward [failed]',send('oais replay base_menu'))
                self.assertEqual(checkpoint.read_bytes(), before)
                child.sendline('exit');child.expect(pexpect.EOF)
            finally:
                child.close(force=True)

if __name__ == '__main__': unittest.main()
