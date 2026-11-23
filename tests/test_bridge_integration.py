"""End-to-end test of the existing Meta Terminal PTY bridge (Linux/WSL)."""

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


@unittest.skipUnless(pexpect is not None and os.name == "posix",
                     "PTY integration requires pexpect and Linux/WSL")
class BridgeIntegrationTests(unittest.TestCase):
    def test_follow_hold_and_snap_through_actual_meta_terminal(self):
        with tempfile.TemporaryDirectory() as data:
            child = pexpect.spawn(sys.executable,
                                  [str(ROOT / "main.py"), "--data-dir", data],
                                  cwd=str(ROOT), encoding="utf-8", timeout=12)
            try:
                child.expect("BASE > ")
                def send(command):
                    child.sendline(command)
                    child.expect("BASE > ")
                    matches = re.findall(
                        r"Virtual \[(FOLLOW|FREE)\]: (\d+(?: \d+){5})",
                        child.before,
                    )
                    # Meta Terminal reprints prior OAIS history while switching;
                    # the LAST match is the response to this command.
                    return matches[-1] if matches else None

                self.assertEqual(send("oais virtual status"),
                                 ("FOLLOW", "0 0 0 0 0 0"))
                send("help")
                self.assertEqual(send("oais virtual status"),
                                 ("FOLLOW", "1 0 0 0 0 0"))
                self.assertEqual(send("oais virtual hold"),
                                 ("FREE", "1 0 0 0 0 0"))
                send("greetings")
                self.assertEqual(send("oais virtual status"),
                                 ("FREE", "1 0 0 0 0 0"))
                self.assertEqual(send("oais virtual sync"),
                                 ("FOLLOW", "2 0 0 0 0 0"))
                send("help")
                self.assertEqual(send("oais virtual status"),
                                 ("FOLLOW", "3 0 0 0 0 0"))
                child.sendline("exit")
                child.expect(pexpect.EOF)
            finally:
                child.close(force=True)


if __name__ == "__main__":
    unittest.main()
