"""OAIS Meta: a non-interactive, command-shaped *connection dispatcher*.

main.py chooses a connection. A connection implements run(meta), while this
module supplies reusable PTY routing, event normalization/forwarding, and
acknowledged OAIS observation. There is no Meta Counter or DataManager.

A connected host owns its own data and may have no coordinate system at all.
This bridge observes commands routed through it, not arbitrary OS keystrokes.
"""

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys

# Only the connected PTY transport needs POSIX modules. Standalone OAIS
# remains importable when the BASE package or Linux PTY support is absent.
if os.name == "posix":
    import pty
    import termios
    import fcntl
from threading import Thread


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _connection_class(module, class_name):
    return getattr(importlib.import_module(module), class_name)


def _worker(role, module, class_name, start, data_dir, base_data_dir):
    """Child subprocess entry: the host and OAIS never import one another."""
    connection_type = _connection_class(module, class_name)
    connection = connection_type(None)

    if role == "host":
        terminal = connection.create_host(start, base_data_dir)
        event_fd = int(os.environ["OAIS_HOST_EVENT_FD"])
        while True:
            try:
                command = input(connection.prompt(terminal))
            except (EOFError, KeyboardInterrupt):
                break
            result = terminal.process_command(command)
            if result.output:
                print(result.output, flush=True)
            if command.strip() and not result.should_exit:
                event = connection.event(command, result)
                os.write(event_fd, (json.dumps(event) + "\n").encode("utf-8"))
            if result.should_exit:
                break
        return

    from oais.Terminal.Oais_Terminal import OaisTerminal
    from oais.utils.counter import Counter
    from oais.utils.data_manager import DataManager

    data_dir = Path(data_dir)
    terminal = OaisTerminal(
        counter=Counter(load_state=True, save_path=data_dir / "current_coordinate.json"),
        data_manager=DataManager(base_dir=data_dir),
        terminal_id=connection.terminal_id,
    )
    if connection.has_coordinates:
        terminal.attach_host(start, universes=0, source=connection.name)
    else:
        # A coordinate-free host resumes OAIS's own synthetic source position.
        # On a fresh source, OAIS starts at its universal zero coordinate.
        position = (terminal._source_position if terminal._source_mode == connection.name
                    else ("0 0 0 0 0 0", 0))
        terminal.attach_host(*position, source=connection.name)
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
                    reply = "1 " + json.dumps(terminal.coordinate_payload()) + "\n"
                    os.write(ack_fd, reply.encode("utf-8"))
                except (KeyError, ValueError, TypeError) as error:
                    os.write(ack_fd, ("ERROR: " + str(error) + "\n").encode("utf-8"))

    Thread(target=observe, daemon=True).start()
    print(terminal.default_message(), flush=True)
    while True:
        try:
            print(terminal.coordinate_display(), flush=True)
            command = input("OAIS > ")
        except (EOFError, KeyboardInterrupt):
            break
        result = terminal.process_command(command, connected=False)
        if result.output:
            print(result.output, flush=True)
        if result.should_exit:
            break


class MetaTerminal:
    """Registry of connection commands and their shared transport methods.

    Meta has no input menu, Counter, or storage. A connection's run() owns the
    selected session. Register an additional class with register(name, cls).
    """

    def __init__(self, starting_coordinate="0 0 0 0 0 0", data_dir=None,
                 base_data_dir=None, persist_virtual_state=False, alternate_screen=False):
        self.starting_coordinate = starting_coordinate
        self.data_dir = Path(data_dir) if data_dir else PROJECT_ROOT / "oais" / "Data"
        self.base_data_dir = (Path(base_data_dir) if base_data_dir else
                              PROJECT_ROOT / "Base" / "Base_Data")
        self.persist_virtual_state = persist_virtual_state
        self.alternate_screen = bool(alternate_screen)
        self.connections = {}
        self.connection = None
        self.running = False

        # Lazy module paths mean standalone OAIS does not import BASE, and
        # adding a new connection only requires one registration below.
        self.register("base", "meta.Connections.Base:BaseConnection")
        self.register("standalone", "meta.Connections.Standalone:StandaloneConnection")
        self.register("counterless", "meta.Connections.Counterless:CounterlessConnection")

    def register(self, name, connection_class):
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
            raise ValueError("Connection names must be simple lowercase identifiers.")
        if isinstance(connection_class, str):
            if ":" not in connection_class:
                raise ValueError("Use 'module.path:ClassName' for lazy connections.")
        elif not callable(getattr(connection_class, "run", None)):
            raise TypeError("A connection must define a run() method.")
        self.connections[name] = connection_class

    def available(self):
        return tuple(self.connections)

    def run(self, connection="base", input_func=input, print_func=print):
        if connection not in self.connections:
            raise ValueError(f"Unknown connection '{connection}'. Available: {', '.join(self.available())}")
        factory = self.connections[connection]
        if isinstance(factory, str):
            module, class_name = factory.rsplit(":", 1)
            factory = _connection_class(module, class_name)
        self.connection = factory(self)
        return self.connection.run(input_func=input_func, print_func=print_func)

    def run_connected(self, connection, input_func=input, print_func=print):
        """Shared process/PTY routing used by external-host connections."""
        if os.name != "posix":
            raise RuntimeError("PTY mode requires Linux/WSL or another POSIX system")
        self.connection = connection
        self._alternate = self.alternate_screen and sys.stdin.isatty() and sys.stdout.isatty()
        if input_func is input and sys.stdin.isatty():
            try:
                import readline  # Enable normal line editing and arrow-key history.
            except ImportError:
                pass
        self.active = "host"
        self._direct = False
        self._processes = {}
        self._masters = {}
        self._history = {"host": "", "oais": ""}
        self._ready = {}
        self._host_coordinate = self.starting_coordinate if connection.has_coordinates else "0 0 0 0 0 0"
        self._host_universe = 0
        self._oais_state = None
        self.running = True
        try:
            self._start()
            print_func(f"OAIS Meta connected to {connection.name.upper()}. 'oais' switches; 'oais <command>' runs directly.")
            print_func("In OAIS, 'return' resumes the host. In the host, 'exit' quits.")
            self._ready["oais"], _ = self._read_to_prompt("oais", visible=False)
            self._ready["host"], _ = self._read_to_prompt("host")
            while self.running:
                try:
                    line = input_func("")
                except (EOFError, KeyboardInterrupt):
                    break
                command = line.strip()
                if self.active == "host" and self._ready["host"] == "host":
                    name, separator, arguments = command.partition(" ")
                    if name.lower() == "oais":
                        direct = bool(separator and arguments.strip())
                        self._enter_oais(direct=direct)
                        if direct:
                            self._direct = True
                            prompt, output = self.route(arguments.strip(), "oais", display_echo=True)
                            if prompt == "oais":
                                response = re.sub(r"\r", "", output)
                                response = re.sub(r"OAIS > $", "", response).strip()
                                self._return_to_host(summary=response if self._alternate else "")
                        continue
                if self.active == "oais" and self._ready["oais"] == "oais":
                    if command.lower() in ("return", self.connection.name, "exit", "base"):
                        self._return_to_host(record_transition=True)
                        continue
                prompt, output = self.route(line)
                if self.active == "host" and prompt == "closed":
                    break
                if self.active == "oais" and prompt == "closed":
                    self._return_to_host(summary="OAIS session ended.")
                    break
                if self.active == "oais" and self._direct and prompt == "oais":
                    self._return_to_host()
        finally:
            self.running = False
            if self.active == "oais" and self._alternate:
                self._emit("\x1b[?1049l")
            self._close()

    def _launch(self, role, extra_fds, environment):
        master, slave = pty.openpty()
        settings = termios.tcgetattr(slave)
        settings[3] &= ~(termios.ECHO | termios.ECHONL)
        termios.tcsetattr(slave, termios.TCSANOW, settings)
        conn = self.connection.__class__
        cmd = [sys.executable, "-u", "-m", "meta.meta_terminal",
               "--_meta-worker", role,
               "--connection-module", conn.__module__,
               "--connection-class", conn.__name__,
               "--start", self.starting_coordinate,
               "--data-dir", str(self.data_dir.resolve()),
               "--base-data-dir", str(self.base_data_dir.resolve())]

        def child_tty():
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

        try:
            proc = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave,
                                    pass_fds=extra_fds, env=environment,
                                    cwd=PROJECT_ROOT, preexec_fn=child_tty)
        finally:
            os.close(slave)
        self._masters[role] = master
        self._processes[role] = proc

    def _start(self):
        self._host_event_read, host_event_write = os.pipe()
        observation_read, self._observation_write = os.pipe()
        self._ack_read, observation_ack_write = os.pipe()
        host_env = dict(os.environ, OAIS_HOST_EVENT_FD=str(host_event_write))
        oais_env = dict(os.environ, OAIS_OBSERVATION_FD=str(observation_read),
                        OAIS_OBSERVATION_ACK_FD=str(observation_ack_write))
        try:
            self._launch("host", (host_event_write,), host_env)
            self._launch("oais", (observation_read, observation_ack_write), oais_env)
        finally:
            os.close(host_event_write)
            os.close(observation_read)
            os.close(observation_ack_write)
        self._observe(self.connection.initial_event(self.starting_coordinate))

    @staticmethod
    def _emit(value):
        sys.stdout.write(value)
        sys.stdout.flush()

    def _prompt(self, tail):
        if tail.endswith("Sticky Note> "):
            return "sticky"
        if tail.endswith("Navigator> "):
            return "navigator"
        if tail.endswith("Replay> "):
            return "replay"
        if tail.endswith("OAIS > "):
            return "oais"
        if re.search(self.connection.prompt_pattern, tail):
            return "host"
        if re.search(r"(?:^|\n)[^\n]{1,200}[:?] $", tail):
            return "followup"
        return None

    def _read_to_prompt(self, role, visible=True):
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
            output = chunk.decode("utf-8", errors="replace")
            new_output += output
            self._history[role] = (self._history[role] + output)[-100_000:]
            if visible:
                self._emit(output)
            tail = (tail + output.replace("\r", ""))[-1000:]
            prompt = self._prompt(tail)
            if prompt:
                return prompt, new_output

    @staticmethod
    def _read_line(fd):
        data = bytearray()
        while True:
            chunk = os.read(fd, 1)
            if not chunk or chunk == b"\n":
                return data.decode("utf-8", errors="replace")
            data.extend(chunk)

    def observe(self, event):
        """Forward an observed host event; wait for OAIS persistence/ACK."""
        os.write(self._observation_write, (json.dumps(event) + "\n").encode("utf-8"))
        response = self._read_line(self._ack_read)
        if not response.startswith("1 "):
            raise RuntimeError("OAIS observation failed: " + response.strip())
        self._oais_state = json.loads(response[2:])
        if event.get("type") == "state" or event.get("source") == self.connection.name:
            # The host may provide native coordinates, or OAIS may synthesize
            # coordinates for a counterless host. No Meta Counter is needed.
            self._host_coordinate = self._oais_state.get("source_coordinate", self._host_coordinate)
            self._host_universe = self._oais_state.get("source_universes", self._host_universe)

    def _observe(self, event):
        return self.observe(event)

    def route(self, command, role=None, *, display_echo=False):
        """Forward input to the active session; return its prompt and output."""
        return self._send(role or self.active, command, display_echo=display_echo)

    def _send(self, role, line, display_echo=False):
        if display_echo:
            self._emit(line + "\n")
        self._history[role] = (self._history[role] + line + "\n")[-100_000:]
        os.write(self._masters[role], (line + "\n").encode("utf-8"))
        if role == "host":
            # Host prompts must not become visible until OAIS acknowledges
            # updating its Navigator, virtual counter, and active recording.
            prompt, output = self._read_to_prompt(role, visible=False)
            self._ready[role] = prompt
            if prompt == "host" and line.strip():
                self.observe(json.loads(self._read_line(self._host_event_read)))
            self._emit(output)
        else:
            prompt, output = self._read_to_prompt(role)
            self._ready[role] = prompt
        return prompt, output

    def _transition(self, value, from_role, to_role):
        self.observe({"type": "transition", "source": "meta", "value": value,
                      "from": from_role, "to": to_role,
                      "coordinate_before": self._host_coordinate,
                      "coordinate_after": self._host_coordinate,
                      "universe_before": self._host_universe,
                      "universe_after": self._host_universe})

    def _enter_oais(self, direct=False):
        if not direct:
            self._transition("oais", from_role=self.connection.name, to_role="oais")
        self.active = "oais"
        if self._alternate:
            self._emit("\x1b[?1049h\x1b[H\x1b[J")
        else:
            self._emit("\n--- OAIS TERMINAL ---\n")
        state = self._oais_state
        if state:
            stack = state.get("active") or []
            activity = (f" | f(k)={stack[-1]['f']} | k={stack[-1]['k']}"
                        if stack else " | linear")
            self._emit(f"\nOAIS Counter:    {state['oais']} "
                       f"(U={state['oais_universe']})\n"
                       f"Virtual Counter: {state['virtual']} "
                       f"(U={state['virtual_universe']}, source={state['source']}, "
                       f"{state['virtual_mode'].upper()}){activity}\n")
        self._emit("OAIS > ")

    def _return_to_host(self, summary="", record_transition=False):
        if record_transition:
            self._transition("return", from_role="oais", to_role=self.connection.name)
        self.active = "host"
        self._direct = False
        if self._alternate:
            self._emit("\x1b[?1049l")
        else:
            self._emit(f"\n--- {self.connection.display_name} TERMINAL ---\n")
        if summary:
            self._emit(summary.rstrip() + "\n")
        self._emit(self.connection.resume_prompt(self._host_coordinate))

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


OAISRuntime = MetaTerminal  # Compatibility with older callers.


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--_meta-worker", choices=("host", "oais"), required=True)
    parser.add_argument("--connection-module", required=True)
    parser.add_argument("--connection-class", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--base-data-dir", type=Path, required=True)
    args = parser.parse_args()
    _worker(args._meta_worker, args.connection_module, args.connection_class,
            args.start, args.data_dir, args.base_data_dir)
