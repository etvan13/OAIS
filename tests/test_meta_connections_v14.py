from history_assertions import steps
"""Meta connection registry, BASE independence, and counterless path recording."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    import pexpect
except ImportError:
    pexpect = None

from meta.meta_terminal import MetaTerminal
from meta.Connections.Counterless import CounterlessConnection, CounterlessHost
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager

ROOT = Path(__file__).resolve().parents[1]


class MetaArchitectureTests(unittest.TestCase):
    def test_dispatcher_owns_no_counter_or_datamanager(self):
        with tempfile.TemporaryDirectory() as root:
            meta = MetaTerminal(data_dir=Path(root) / "OAIS_Data",
                                base_data_dir=Path(root) / "BASE_Data")
            self.assertEqual(meta.available(), ("base", "standalone", "counterless"))
            self.assertFalse(hasattr(meta, "counter"))
            self.assertFalse(hasattr(meta, "data_manager"))
            self.assertRaises(ValueError, meta.run, "does-not-exist")

    def test_base_runs_as_independent_script(self):
        with tempfile.TemporaryDirectory() as root:
            code = "from utils.counter import Counter; from utils.data_manager import DataManager; " \
                   "from Base_Terminal import BaseTerminal; t=BaseTerminal(counter=Counter(load_state=False)," \
                   " data_manager=DataManager(base_dir=" + repr(root) + ")); print(t.process_command('greetings').output)"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT / "Base")
            proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT / "Base",
                                  env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Hello Universe!", proc.stdout)
            self.assertNotIn("oais", proc.stderr.lower())

    def test_base_storage_is_separate_and_backward_compatible(self):
        from Base.utils.data_manager import DataManager as BaseDataManager
        with tempfile.TemporaryDirectory() as folder:
            base_dir = Path(folder) / "Base_Data"
            oais_dir = Path(folder) / "oais" / "Data"
            manager = BaseDataManager(base_dir=base_dir)
            manager.create_coordinate_message("4 0 0 0 0 0", "Test", "BASE-owned message",
                                              extra_data={"kind": "original"})
            restored = BaseDataManager(base_dir=base_dir).load_coordinate_messages("4 0 0 0 0 0")
            self.assertEqual(restored[0]["title"], "Test")
            self.assertEqual(restored[0]["data"], {"kind": "original"})
            self.assertTrue(list((base_dir / "coordinate_data").rglob("*.json")))
            self.assertFalse(oais_dir.exists())

    def test_standalone_connection_does_not_import_base(self):
        with tempfile.TemporaryDirectory() as root:
            script = """import importlib.abc, sys
class BlockBase(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'Base' or fullname.startswith('Base.'):
            raise ImportError('BASE must not be imported')
sys.meta_path.insert(0, BlockBase())
from meta.meta_terminal import MetaTerminal
m = MetaTerminal(data_dir=__import__('pathlib').Path(sys.argv[1]))
m.run('standalone', input_func=lambda prompt: 'exit', print_func=lambda text: None)
print('standalone succeeded')
"""
            proc = subprocess.run([sys.executable, "-c", script, root], cwd=ROOT,
                                  capture_output=True, text=True, timeout=12)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("standalone succeeded", proc.stdout)

    def test_counterless_events_drive_source_and_function_without_native_coordinate(self):
        with tempfile.TemporaryDirectory() as root:
            dm = DataManager(base_dir=Path(root) / "oais_data")
            t = OaisTerminal(counter=Counter(load_state=False, save_path=Path(root) / "counter.json"),
                             data_manager=dm, terminal_id="counterless")
            t.attach_host("0 0 0 0 0 0", source="counterless")
            t.process_command("sticky start")
            t.process_command("function k**2")
            for command in ("echo a", "help", "invalid"):
                # An adapter sends no coordinate or movement fields.
                t.observe_event(CounterlessConnection.event(command, CounterlessHost().process_command(command)))
            self.assertEqual(t._source_position, ("3 0 0 0 0 0", 0))
            self.assertEqual(t.virtual_counter.coordinate, "9 0 0 0 0 0")
            self.assertEqual(t.navigator_engine.compact_state()["functions"][0]["k"], 3)
            t.process_command("sticky save generic_host")
            note = t.sticky_note.get_note("generic_host")
            self.assertEqual([event["command"] for event in steps(t.sticky_note, note)],
                             ["sticky start", "function k**2", "echo a", "help", "invalid", "sticky save generic_host"])
            self.assertEqual([event["source"] for event in steps(t.sticky_note, note)],
                             ["oais", "oais", "counterless", "counterless", "counterless", "oais"])
            self.assertTrue(steps(t.sticky_note, note)[-2]["failed"])
            self.assertEqual(len(t.replay_engine.available()), 1)
            # Reloading a counterless source is valid, not rejected as 'base or oais'.
            checkpoint = t.navigation_context()
            t2 = OaisTerminal(counter=Counter(load_state=False, save_path=Path(root) / "other.json"),
                              data_manager=dm, terminal_id="counterless")
            self.assertEqual(checkpoint["source"], "counterless")


@unittest.skipUnless(pexpect is not None and os.name == "posix", "PTY test requires Linux and pexpect")
class MetaCounterlessPTYTests(unittest.TestCase):
    def test_counterless_connection_record_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            args = [str(ROOT / "main.py"), "--connection", "counterless", "--data-dir", folder]
            child = pexpect.spawn(sys.executable, args, cwd=str(ROOT), encoding="utf-8", timeout=15)
            try:
                child.expect("DEMO > ")
                def send(command):
                    child.sendline(command)
                    child.expect("DEMO > ")
                    return child.before
                self.assertIn("FOLLOW", send("oais virtual status"))
                send("oais sticky start")
                send("oais function k**2")
                send("ping")
                send("echo hello")
                send("unknown")
                status = send("oais virtual status")
                self.assertIn("Virtual [FREE]: 9 0 0 0 0 0", status)
                self.assertIn("Saved", send("oais sticky save without_counter"))
                self.assertIn("[COUNTERLESS] ping", send("oais replay without_counter"))
                state = json.loads((Path(folder) / "virtual_coordinate.json").read_text())
                self.assertEqual(state["source"], "counterless")
                self.assertEqual(state["source_coordinate"], "3 0 0 0 0 0")
                self.assertEqual(state["coordinate"], "9 0 0 0 0 0")
                child.sendline("exit")
                child.expect(pexpect.EOF)
            finally:
                child.close(force=True)
            # The universal source position and function stack survive restart.
            reopened = pexpect.spawn(sys.executable, args, cwd=str(ROOT), encoding="utf-8", timeout=15)
            try:
                reopened.expect("DEMO > ")
                reopened.sendline("oais virtual status")
                reopened.expect("DEMO > ")
                self.assertIn("Virtual [FREE]: 9 0 0 0 0 0", reopened.before)
                reopened.sendline("ping")
                reopened.expect("DEMO > ")
                state = json.loads((Path(folder) / "virtual_coordinate.json").read_text())
                self.assertEqual(state["source_coordinate"], "4 0 0 0 0 0")
                self.assertEqual(state["coordinate"], "16 0 0 0 0 0")
                reopened.sendline("exit")
                reopened.expect(pexpect.EOF)
            finally:
                reopened.close(force=True)
