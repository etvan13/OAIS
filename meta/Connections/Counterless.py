"""Example connection that has no native coordinate, Counter, or DataManager.

This is intentionally a minimal test host, not an OS shell or keyboard hook.
It proves an ordinary program can drive OAIS's universal event counter.
"""
from dataclasses import dataclass


@dataclass
class CommandResult:
    output: str
    success: bool = True
    should_exit: bool = False


class CounterlessHost:
    def process_command(self, command):
        text = command.strip()
        name, _, value = text.partition(" ")
        if name == "help":
            return CommandResult("Commands: help, echo TEXT, ping, exit")
        if name == "echo":
            return CommandResult(value)
        if name == "ping":
            return CommandResult("pong")
        if name == "exit":
            return CommandResult("Exiting counterless test terminal.", should_exit=True)
        return CommandResult(f"Unknown command: {name}", success=False)


class CounterlessConnection:
    name = "counterless"
    terminal_id = "counterless"
    has_coordinates = False
    prompt_pattern = r"DEMO > $"
    display_name = "DEMO"

    def __init__(self, meta):
        self.meta = meta

    @staticmethod
    def create_host(start, base_data_dir=None):
        return CounterlessHost()

    @staticmethod
    def prompt(host):
        return "DEMO > "

    @staticmethod
    def event(command, result):
        return {"type": "command", "source": "counterless",
                "value": command.strip(), "success": result.success,
                "output": result.output}

    @classmethod
    def resume_prompt(cls, coordinate):
        return "DEMO > "

    def initial_event(self, start):
        return {"type": "state", "source": self.name}

    def run(self, **kwargs):
        return self.meta.run_connected(self, **kwargs)
