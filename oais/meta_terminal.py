"""OAIS meta-terminal: one keyboard, two independent terminal sessions.

The public class is MetaTerminal; OAISRuntime remains a compatibility alias.
Run main.py to use MetaTerminal, or launch one terminal independently.

On Linux/WSL, each terminal runs in its own subprocess behind a PTY.
BASE knows nothing about OAIS. The meta-terminal owns switching, passes
BASE result events to OAIS, and leaves Sticky Note's .txt storage alone.
"""

import argparse
import importlib
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import subprocess
import sys
import termios
import fcntl
from threading import Thread


def _components():
    """Load the existing classes under either a package or top-level layout."""
    prefix = f"{__package__}." if __package__ else ""
    base = importlib.import_module(prefix + "Terminal.Base_Terminal").BaseTerminal
    oais = importlib.import_module(prefix + "Terminal.Oais_Terminal").OaisTerminal
    counter = importlib.import_module(prefix + "utils.counter").Counter
    manager = importlib.import_module(prefix + "utils.data_manager").DataManager
    return base, oais, counter, manager


def _worker(role, start, data_dir):
    """Run a genuine terminal process; neither terminal imports the meta layer."""
    BaseTerminal, OaisTerminal, Counter, DataManager = _components()
    manager = DataManager(base_dir=(Path(data_dir) if role == "oais" else Path(data_dir).parent / "Base_Data"))
    counter = Counter(load_state=(role == "oais"),
                      save_path=(Path(data_dir) / "current_coordinate.json" if role == "oais" else Path(data_dir).parent / "Base_Data" / "current_coordinate.json"))

    if role == "base":
        terminal = BaseTerminal(starting_coordinate=start, counter=counter,
                                data_manager=manager)
        event_fd = int(os.environ["OAIS_HOST_EVENT_FD"])
        while True:
            try:
                command = input(f"[{terminal.counter.get_counters()}] BASE > ")
            except (EOFError, KeyboardInterrupt):
                break
            result = terminal.process_command(command)
            if result.output:
                print(result.output, flush=True)
            if command.strip() and not result.should_exit:
                event = {
                    "type": "command", "value": command.strip(),
                    "source": "base", "success": result.success,
                    "coordinate_before": result.coordinate_before,
                    "coordinate_after": result.coordinate_after,
                    "universe_before": result.universe_before,
                    "universe_after": result.universe_after,
                    "output": result.output,
                }
                os.write(event_fd, (json.dumps(event) + "\n").encode())
            if result.should_exit:
                break
        return

    terminal = OaisTerminal(counter=counter, data_manager=manager)
    terminal.attach_host(start, universes=0)
    terminal.source_name = "base"
    event_fd = int(os.environ["OAIS_OBSERVATION_FD"])
    ack_fd = int(os.environ["OAIS_OBSERVATION_ACK_FD"])

    def observe():
        with os.fdopen(event_fd, "r", encoding="utf-8") as incoming:
            for line in incoming:
                try:
                    event = json.loads(line)
                    if event.get("type") == "config":
                        terminal.recording_scope = event["scope"]
                    else:
                        terminal.observe_event(event)
                    os.write(ack_fd, b"1\n")
                except (KeyError, ValueError, TypeError) as error:
                    os.write(ack_fd, ("ERROR: " + str(error) + "\n").encode())

    Thread(target=observe, daemon=True).start()
    print(terminal.default_message(), flush=True)
    while True:
        try:
            command = input("OAIS > ")
        except (EOFError, KeyboardInterrupt):
            break
        # Here OAIS owns its own input; unprefixed OAIS commands are valid.
        result = terminal.process_command(command, connected=False)
        if result.output:
            print(result.output, flush=True)
        if result.should_exit:
            break


class MetaTerminal:
    """Owns the visible terminal, command routing, and BASE-to-OAIS observations."""

    def __init__(self, starting_coordinate="0 0 0 0 0 0", data_dir=None):
        self.starting_coordinate = starting_coordinate
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent / "Data"
        self.running = False
        self.active = "base"
        self._direct = False
        self._processes = {}
        self._masters = {}
        self._history = {"base": "", "oais": ""}
        self._ready = {}
        self._host_coordinate = starting_coordinate
        self._host_universe = 0
        self._alternate = False

        # Keep the original main.py --mode base/oais interfaces available.
        BaseTerminal, OaisTerminal, Counter, DataManager = _components()
        self.data_manager = DataManager(base_dir=self.data_dir)
        self.base_data_manager = DataManager(base_dir=self.data_dir.parent / "Base_Data")
        self.host = BaseTerminal(starting_coordinate=starting_coordinate,
                                 counter=Counter(load_state=False,
                                     save_path=self.data_dir.parent / "Base_Data" / "current_coordinate.json"),
                                 data_manager=self.base_data_manager)
        self.oais = OaisTerminal(counter=Counter(load_state=True,
                                     save_path=self.data_dir / "current_coordinate.json"),
                                 data_manager=self.data_manager, runtime=self)
        self.base_terminal = self.host
        self.oais_terminal = self.oais
        self.host_counter = self.host.counter
        self.counter = self.oais.counter

    def sync_from_host(self):
        """Expose the latest observed BASE position for existing callers."""
        self.host.counter.sync(self._host_coordinate, universes=self._host_universe,
                               save=False)
        self.oais.attach_host(self._host_coordinate, self._host_universe)
        self.counter = self.oais.counter
        return self.counter.get_counters()

    def set_host_coordinate(self, coordinate):
        """Set the initial coordinate before run(), as with the old runtime."""
        if self.running:
            raise RuntimeError("Cannot set BASE position while its PTY is running")
        self.starting_coordinate = coordinate
        self._host_coordinate = coordinate
        self.host.set_start_coordinate(coordinate)
        return self.sync_from_host()

    def _launch(self, role, extra_fds, environment):
        master, slave = pty.openpty()
        settings = termios.tcgetattr(slave)
        settings[3] &= ~(termios.ECHO | termios.ECHONL)
        termios.tcsetattr(slave, termios.TCSANOW, settings)
        module = self.__class__.__module__
        cmd = ([sys.executable, "-u", "-m", module]
               if module != "__main__" else [sys.executable, "-u", str(Path(__file__).resolve())])
        cmd += ["--_meta-worker", role, "--start", self.starting_coordinate,
                "--data-dir", str(self.data_dir)]

        def child_tty():
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

        try:
            proc = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave,
                                    pass_fds=extra_fds, env=environment,
                                    preexec_fn=child_tty)
        finally:
            os.close(slave)
        self._masters[role] = master
        self._processes[role] = proc

    def _start(self):
        self._host_event_read, host_event_write = os.pipe()
        observation_read, self._observation_write = os.pipe()
        self._ack_read, observation_ack_write = os.pipe()
        base_env = dict(os.environ, OAIS_HOST_EVENT_FD=str(host_event_write))
        oais_env = dict(os.environ, OAIS_OBSERVATION_FD=str(observation_read),
                        OAIS_OBSERVATION_ACK_FD=str(observation_ack_write))
        try:
            self._launch("base", (host_event_write,), base_env)
            self._launch("oais", (observation_read, observation_ack_write), oais_env)
        finally:
            os.close(host_event_write)
            os.close(observation_read)
            os.close(observation_ack_write)
        self._observe({"type": "state", "coordinate_after": self.starting_coordinate,
                       "universe_after": 0})

    @staticmethod
    def _emit(text):
        sys.stdout.write(text)
        sys.stdout.flush()

    @staticmethod
    def _prompt(tail):
        if tail.endswith("Sticky Note> "):
            return "sticky"
        if tail.endswith("OAIS > "):
            return "oais"
        if re.search(r"\[\d+(?: \d+){5}\] BASE > $", tail):
            return "base"
        # Preserve BASE's existing interactive save_data/load_data prompts.
        if re.search(r"(?:^|\n)[^\n]{1,200}[:?] $", tail):
            return "followup"
        return None

    def _read_to_prompt(self, role, visible=True):
        """Stream child output until it is ready for its next input."""
        master = self._masters[role]
        tail = ""
        new_output = ""
        while True:
            if not select.select([master], [], [], 0.25)[0]:
                if self._processes[role].poll() is not None:
                    return "closed", new_output
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:
                return "closed", new_output
            if not chunk:
                return "closed", new_output
            text = chunk.decode("utf-8", errors="replace")
            new_output += text
            self._history[role] = (self._history[role] + text)[-100_000:]
            if visible:
                self._emit(text)
            tail = (tail + text.replace("\r", ""))[-1000:]
            prompt = self._prompt(tail)
            if prompt:
                return prompt, new_output

    def _observe(self, event):
        """Send a BASE result to OAIS and wait until its recorder has seen it."""
        os.write(self._observation_write, (json.dumps(event) + "\n").encode())
        response = self._read_line(self._ack_read)
        if not response.startswith("1"):
            raise RuntimeError("OAIS observation failed: " + response.strip())
        if event.get("type") == "state" or event.get("source") == "base":
            self._host_coordinate = event["coordinate_after"]
            self._host_universe = event["universe_after"]
            # Host snapshot is separate from OAIS standalone state.
            _, _, Counter, _ = _components()
            snapshot = Counter(load_state=False, save_path=self.data_dir / "host_coordinate.json")
            snapshot.sync(self._host_coordinate, universes=self._host_universe, save=True)
            self.sync_from_host()

    @staticmethod
    def _read_line(fd):
        data = bytearray()
        while True:
            chunk = os.read(fd, 1)
            if not chunk or chunk == b"\n":
                return data.decode("utf-8", errors="replace")
            data.extend(chunk)

    def _send(self, role, line, display_echo=False):
        if display_echo:
            self._emit(line + "\n")
        self._history[role] = (self._history[role] + line + "\n")[-100_000:]
        os.write(self._masters[role], (line + "\n").encode("utf-8"))
        prompt, output = self._read_to_prompt(role)
        self._ready[role] = prompt
        if role == "base" and prompt == "base" and line.strip():
            # BASE writes one event for each completed non-exit command.
            self._observe(json.loads(self._read_line(self._host_event_read)))
        return prompt, output

    def _enter_oais(self, direct=False):
        # Change only the default scope for new recordings. An active note
        # retains the scope it was started with.
        self._observe({"type": "config", "scope": "base" if direct else "all"})
        if not direct:
            self._transition("oais", from_role="base", to_role="oais")
        self.active = "oais"
        if self._alternate:
            self._emit("\x1b[?1049h\x1b[H\x1b[J")
        else:
            self._emit("\n--- OAIS TERMINAL ---\n")
        self._emit(self._history["oais"])

    def _transition(self, value, from_role, to_role):
        self._observe({
            "type": "transition", "source": "meta", "value": value,
            "from": from_role, "to": to_role,
            "coordinate_before": self._host_coordinate,
            "coordinate_after": self._host_coordinate,
            "universe_before": self._host_universe,
            "universe_after": self._host_universe,
        })

    def _return_to_base(self, summary="", record_transition=False):
        if record_transition:
            self._transition("return", from_role="oais", to_role="base")
        self.active = "base"
        self._direct = False
        if self._alternate:
            self._emit("\x1b[?1049l")
        else:
            self._emit("\n--- BASE TERMINAL ---\n")
        if summary:
            self._emit(summary.rstrip() + "\n")
        self._emit(f"[{self._host_coordinate}] BASE > ")

    def run(self, input_func=input, print_func=print):
        """Run the PTY proxy. Only BASE receives inputs not claimed by 'oais'."""
        if os.name != "posix":
            raise RuntimeError("PTY mode requires Linux/WSL or another POSIX system")
        self._alternate = sys.stdin.isatty() and sys.stdout.isatty()
        self.running = True
        try:
            self._start()
            print_func("OAIS meta-terminal started. 'oais' switches; 'oais sticky' opens Sticky Note.")
            print_func("In OAIS, type 'return' to resume BASE. In BASE, 'exit' quits.")
            self._ready["oais"], _ = self._read_to_prompt("oais", visible=False)
            self._ready["base"], _ = self._read_to_prompt("base")
            while self.running:
                try:
                    line = input_func("")
                except (EOFError, KeyboardInterrupt):
                    break
                command = line.strip()
                if self.active == "base" and self._ready["base"] == "base":
                    name, separator, arguments = command.partition(" ")
                    if name.lower() == "oais":
                        direct = bool(separator and arguments.strip())
                        self._enter_oais(direct=direct)
                        if direct:
                            self._direct = True
                            prompt, output = self._send("oais", arguments.strip(), display_echo=True)
                            if prompt == "oais":
                                text = re.sub(r"\r", "", output)
                                text = re.sub(r"OAIS > $", "", text).strip()
                                self._return_to_base(summary=text)
                        continue
                if self.active == "oais" and self._ready["oais"] == "oais":
                    if command.lower() in ("return", "base", "exit"):
                        self._history["oais"] += line + "\nOAIS > "
                        self._return_to_base(record_transition=True)
                        continue
                prompt, output = self._send(self.active, line)
                if self.active == "base" and prompt == "closed":
                    break
                if self.active == "oais" and prompt == "closed":
                    self._return_to_base(summary="OAIS session ended.")
                    break
                if self.active == "oais" and self._direct and prompt == "oais":
                    # Interactive commands, e.g. Sticky Note, have now exited.
                    self._return_to_base()
        finally:
            self.running = False
            if self.active == "oais" and self._alternate:
                self._emit("\x1b[?1049l")
            self._close()
            self.oais.detach_host()
            self.counter = self.oais.counter

    def _close(self):
        for name in ("_observation_write", "_host_event_read", "_ack_read"):
            fd = getattr(self, name, None)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        for proc in self._processes.values():
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        for fd in self._masters.values():
            try:
                os.close(fd)
            except OSError:
                pass


# Existing main.py imports OAISRuntime; it requires no changes when this
# file is installed as runtime.py.
OAISRuntime = MetaTerminal


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--_meta-worker", choices=("base", "oais"))
    parser.add_argument("--start", default="0 0 0 0 0 0")
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    if args._meta_worker:
        _worker(args._meta_worker, args.start, args.data_dir)
    else:
        MetaTerminal(starting_coordinate=args.start, data_dir=args.data_dir).run()
