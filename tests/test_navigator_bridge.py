"""Real PTY integration for functional movement alongside DEEP Base Counter."""
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

try:
    import pexpect
except ImportError:
    pexpect = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(pexpect and os.name == 'posix', 'Requires Linux/WSL and pexpect')
class NavigatorBridgeTests(unittest.TestCase):
    def test_cubic_base_commands_turn_and_sync_are_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            proc = pexpect.spawn(sys.executable,
                [str(ROOT/'main.py'), '--start', '3 0 0 0 0 0', '--data-dir', folder],
                cwd=str(ROOT), encoding='utf-8', timeout=16)
            try:
                proc.expect('BASE > ')
                def send(text):
                    proc.sendline(text)
                    proc.expect('BASE > ')
                    return proc.before
                def virtual():
                    output = send('oais virtual status')
                    matches = re.findall(r'Virtual \[(FOLLOW|FREE)\]: (\d+(?: \d+){5})', output)
                    self.assertTrue(matches, msg=output[-1000:])
                    return matches[-1]
                self.assertEqual(virtual(), ('FOLLOW', '3 0 0 0 0 0'))
                self.assertIn('Opened pole', send('oais navigator open cubic'))
                self.assertEqual(virtual(), ('FREE', '3 0 0 0 0 0'))
                send('help')
                self.assertEqual(virtual(), ('FREE', '4 0 0 0 0 0'))
                send('greetings')
                self.assertEqual(virtual(), ('FREE', '11 0 0 0 0 0'))
                send('unsupported_word')
                self.assertEqual(virtual(), ('FREE', '30 0 0 0 0 0'))
                send('oais navigator turn')
                self.assertEqual(virtual(), ('FREE', '11 0 0 0 0 0'))
                send('help')
                self.assertEqual(virtual(), ('FREE', '4 0 0 0 0 0'))
                send('help')
                self.assertEqual(virtual(), ('FREE', '3 0 0 0 0 0'))
                # Base moved from 3 to 8; virtual completed excursion at 3.
                self.assertIn('[8 0 0 0 0 0] BASE >', send('oais navigator status') + '[8 0 0 0 0 0] BASE >')
                self.assertEqual(virtual(), ('FREE', '3 0 0 0 0 0'))
                self.assertEqual(send('oais virtual sync').count('Virtual [FOLLOW]') >= 1, True)
                self.assertEqual(virtual(), ('FOLLOW', '8 0 0 0 0 0'))
                proc.sendline('exit')
                proc.expect(pexpect.EOF)
            finally:
                proc.close(force=True)

    def test_checkpoint_then_sticky_legacy_still_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            proc = pexpect.spawn(sys.executable,
                [str(ROOT/'main.py'), '--start', '1 0 0 0 0 0', '--data-dir', folder],
                cwd=str(ROOT), encoding='utf-8', timeout=16)
            try:
                proc.expect('BASE > ')
                def send(command):
                    proc.sendline(command); proc.expect('BASE > '); return proc.before
                send('oais navigator open constant')
                send('help')
                send('oais navigator checkpoint')
                self.assertIn('PAUSED', send('oais navigator pause'))
                send('help')
                self.assertIn('Restored navigator checkpoint', send('oais navigator restore'))
                # A one-command legacy note is still saved/read separately.
                send('oais sticky start')
                send('greetings')
                send('oais sticky stop')
                self.assertIn('Saved', send('oais sticky save legacy_nav_test'))
                self.assertIn('STICKY NOTE: legacy_nav_test', send('oais sticky read legacy_nav_test'))
                proc.sendline('exit'); proc.expect(pexpect.EOF)
            finally:
                proc.close(force=True)

if __name__ == '__main__':
    unittest.main()
