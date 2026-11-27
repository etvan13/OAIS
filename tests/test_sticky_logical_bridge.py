"""Actual BASE/OAIS PTY command flow and saved v4 note recovery."""
from pathlib import Path
import sys
import tempfile
import unittest

try:
    import pexpect
except ImportError:
    pexpect = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(pexpect is None or sys.platform == 'win32', 'PTY requires pexpect / POSIX')
class LogicalBridgeTests(unittest.TestCase):
    def test_cubic_note_with_navigator_turn_in_base_scope_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            proc = pexpect.spawn(sys.executable,
                [str(ROOT/'main.py'),'--start','0 0 0 0 0 0','--data-dir',folder],
                cwd=str(ROOT), encoding='utf-8', timeout=20)
            try:
                proc.expect('BASE > ')
                def send(cmd):
                    proc.sendline(cmd)
                    proc.expect('BASE > ')
                    return proc.before
                self.assertIn('Opened pole',send('oais navigator open cubic'))
                self.assertIn('Recording started',send('oais sticky start'))
                send('help');send('help');send('help')
                self.assertIn('back)',send('oais navigator turn'))
                send('help');send('help')
                path = send('oais sticky path')
                self.assertIn('navigator turn',path)
                self.assertIn('f=pi_',path)
                self.assertIn('Recording stopped',send('oais sticky stop'))
                self.assertIn("Saved 'pty_cubic'",send('oais sticky save pty_cubic'))
                read = send('oais sticky read pty_cubic')
                self.assertIn('STICKY NOTE:',read)
                # Switching directly into OAIS no longer replays cached output.
                self.assertIn('virtual:27 0 0 0 0 0',read)  # reconstructed trace
                proc.sendline('exit');proc.expect(pexpect.EOF)
            finally:
                proc.close(force=True)
            # Start a new process: no active Navigator or cached temporary path.
            # Stored note must recover without relying on either one.
            proc2 = pexpect.spawn(sys.executable,
                [str(ROOT/'main.py'),'--start','0 0 0 0 0 0','--data-dir',folder],
                cwd=str(ROOT), encoding='utf-8', timeout=20)
            try:
                proc2.expect('BASE > ')
                proc2.sendline('oais sticky read pty_cubic')
                proc2.expect('BASE > ')
                self.assertIn('STICKY NOTE:',proc2.before)
                proc2.sendline('exit');proc2.expect(pexpect.EOF)
            finally:
                proc2.close(force=True)

    def test_nested_and_constant_with_interactive_sticky_menu(self):
        with tempfile.TemporaryDirectory() as folder:
            proc=pexpect.spawn(sys.executable,
                [str(ROOT/'main.py'),'--data-dir',folder],
                cwd=str(ROOT),encoding='utf-8',timeout=20)
            try:
                proc.expect('BASE > ')
                def send(c):
                    proc.sendline(c);proc.expect('BASE > ');return proc.before
                send('oais navigator open constant')
                self.assertIn('Recording started',send('oais sticky start'))
                send('help');send('help')
                send('oais navigator turn');send('help')
                send('oais sticky stop')
                self.assertIn("Saved 'constant_pty'",send('oais sticky save constant_pty'))
                self.assertIn('STICKY NOTE:',send('oais sticky read constant_pty'))
                # The submenu is still available after v4 saves.
                proc.sendline('oais sticky')
                proc.expect('Sticky Note> ')
                proc.sendline('list')
                proc.expect('Sticky Note> ')
                self.assertIn('constant_pty',proc.before)
                proc.sendline('exit')
                proc.expect('BASE > ')
                proc.sendline('exit');proc.expect(pexpect.EOF)
            finally:
                proc.close(force=True)


if __name__=='__main__':
    unittest.main()
