"""Simple Base Terminal for testing OAIS alongside an independent host.

Based on the original base terminal: a Counter, a DataManager, a small
command dictionary, and a run loop. No OAIS imports or movement helpers.
"""

from dataclasses import dataclass
import json

try:
    from ..utils.counter import Counter
    from ..utils.data_manager import DataManager
except ImportError:  # python main.py from the project root
    from utils.counter import Counter
    from utils.data_manager import DataManager


@dataclass
class HostResult:
    """Small wrapper expected by the CURRENT runtime.py."""
    output: str
    success: bool = True
    should_exit: bool = False
    coordinate_before: str = ""
    coordinate_after: str = ""
    universe_before: int = 0
    universe_after: int = 0


class BaseTerminal:
    def __init__(self, starting_coordinate="0 0 0 0 0 0", counter=None, data_manager=None):
        # Reuse the existing shared Counter rather than creating a movement system.
        self.counter = counter if counter is not None else Counter(load_state=False)
        self.counter.sync(starting_coordinate, save=False)
        self.data_manager = data_manager if data_manager is not None else DataManager()
        self.start_coordinate = starting_coordinate
        self.current_coordinate = self.counter.get_counters()

        self.commands = {
            "help": self.show_help,
            "greetings": self.greet,
            "hello": self.greet,
            "forwards": self.forwards,
            "backwards": self.backwards,
            "save_data": self.save_data_command,
            "load_data": self.load_data_command,
            "set_coord": self.set_coordinate_command,
            "exit": self.exit_command,
        }

    def set_start_coordinate(self, coordinate):
        self.counter.sync(coordinate, save=False)
        self.start_coordinate = self.counter.get_counters()
        self.current_coordinate = self.start_coordinate

    def default_message(self):
        return f"Current Coordinate: {self.current_coordinate}\nType 'help' for commands."

    def process_command(self, command):
        """Run one command; preserve the result shape used by current runtime.

        Each nonempty input advances once, except explicit movement commands.
        forwards = +1; backwards = -1; set_coord = exact destination.
        """
        command = command.strip()
        before = self.counter.get_counters()
        universe_before = self.counter.universes
        if not command:
            return HostResult("", coordinate_before=before, coordinate_after=before,
                              universe_before=universe_before, universe_after=universe_before)

        # Keep the familiar exact command dictionary, with one optional argument
        # for set_coord so connected runtime can set coordinates without nested input.
        name, _, arguments = command.partition(" ")
        name = name.lower()
        handler = self.commands.get(name)
        success = handler is not None
        if handler is None:
            response = "Unknown command."
        else:
            try:
                response = handler(arguments.strip())
            except (ValueError, TypeError, OSError) as exc:
                response = f"Command error: {exc}"
                success = False

        if name not in ("forwards", "backwards", "set_coord"):
            self.counter.increment()

        self.current_coordinate = self.counter.get_counters()
        return HostResult(
            output=self.default_message() + "\n" + response,
            success=success,
            should_exit=name == "exit" and success,
            coordinate_before=before,
            coordinate_after=self.current_coordinate,
            universe_before=universe_before,
            universe_after=self.counter.universes,
        )

    def run(self, input_func=input, print_func=print):
        print_func(self.default_message())
        while True:
            try:
                command = input_func("> ")
            except (EOFError, KeyboardInterrupt):
                break
            result = self.process_command(command)
            if result.output:
                print_func(result.output)
            if result.should_exit:
                break

    # ---------- Built-in Terminal Commands ---------- #
    def show_help(self, arguments=""):
        return ("Available commands:\n"
                "- help       : Show this help\n"
                "- greetings  : Print a greeting\n"
                "- forwards   : Move one coordinate forward\n"
                "- backwards  : Move one coordinate backward\n"
                "- save_data  : Save a message with optional JSON metadata\n"
                "- load_data  : Read messages (prompts for coordinate)\n"
                "- set_coord  : Set coordinate (prompts, or provide six numbers)\n"
                "- exit       : Exit")

    def greet(self, arguments=""):
        return "Hello Universe!"

    def forwards(self, arguments=""):
        self.counter.increment()
        self.current_coordinate = self.counter.get_counters()
        return f"Moved forwards to {self.current_coordinate}."

    def backwards(self, arguments=""):
        self.counter.decrement()
        self.current_coordinate = self.counter.get_counters()
        return f"Moved backwards to {self.current_coordinate}."

    def set_coordinate_command(self, arguments=""):
        coord = arguments or input("Enter new coordinate: ").strip()
        self.counter.sync(coord, save=False)
        self.current_coordinate = self.counter.get_counters()
        return f"Counter set to: {self.current_coordinate}"

    def save_data_command(self, arguments=""):
        coord = input(f"Enter coordinate to save data (Enter for {self.current_coordinate}): ").strip()
        coord = coord or self.current_coordinate
        title = input("Enter title: ")
        message = input("Enter message: ")
        raw_data = input('Enter data as JSON (Enter for none; e.g. {"color":"orange"}): ').strip()
        if raw_data:
            try:
                extra_data = json.loads(raw_data)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON data: {exc.msg}") from exc
            if not isinstance(extra_data, dict):
                raise ValueError('Data must be a JSON object, e.g. {"color":"orange"}.')
        else:
            extra_data = {}
        self.data_manager.create_coordinate_message(
            coordinate=coord, title=title, message=message, extra_data=extra_data
        )
        return f"Data saved at '{coord}'."

    def load_data_command(self, arguments=""):
        coord = input(f"Enter coordinate to load data (Enter for {self.current_coordinate}): ").strip()
        coord = coord or self.current_coordinate
        messages = self.data_manager.load_coordinate_messages(coord) or []
        if not messages:
            return f"No messages found at '{coord}'."
        lines = [f"Messages at '{coord}':"]
        for i, msg in enumerate(messages, 1):
            lines.append(f"{i}) Title: {msg.get('title', 'Untitled')}\n   Msg: {msg.get('message', '')}")
            if msg.get("data"):
                lines.append("   Data: " + json.dumps(msg["data"], ensure_ascii=False, sort_keys=True))
        return "\n".join(lines)

    def exit_command(self, arguments=""):
        return "Exiting Base Terminal."
