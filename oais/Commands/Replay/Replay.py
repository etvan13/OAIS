"""Terminal adapter for read-only coordinate path playback and data inspection."""

import json


class Replay:
    def __init__(self, terminal):
        self.engine = terminal.replay_engine
        self.data_manager = terminal.data_manager

    def run(self, arguments="", *, input_func=input, print_func=print):
        if not arguments.strip():
            print_func("\nREPLAY — SAVED STICKY NOTES")
            print_func(self.engine.list_notes())
            print_func("Type a note number, title, or ID. 'list' refreshes; 'exit' returns.\n")
            while True:
                try:
                    choice = input_func("Replay> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print_func("")
                    break
                if not choice:
                    continue
                if choice.lower() in ("exit", "back", "return"):
                    break
                try:
                    print_func(self._run(choice))
                except (KeyError, ValueError, TypeError, NotImplementedError) as exc:
                    print_func(f"Replay error: {exc}")
            return "Returning to OAIS terminal."
        try:
            return self._run(arguments)
        except KeyError as exc:
            return f"Saved Sticky Note not found: {exc}"

    def _run(self, arguments=""):
        raw = arguments.strip()
        action, _, arg = raw.partition(' ')
        action = action.lower()
        arg = arg.strip()
        if not action or action in ('help', '?'):
            return ("Replay commands (read-only; never re-executes commands):\n"
                    "  replay                Choose a saved Sticky Note interactively\n"
                    "  replay list           List notes in this terminal's sticky_notes.json\n"
                    "  replay <number/title>  Show all saved commands in order\n"
                    "  replay load <title>    Load note for step-by-step inspection\n"
                    "  replay data <6 digits> Read messages and JSON data at a coordinate\n"
                    "  replay next [count]    Advance through recorded steps\n"
                    "  replay all             Show remaining steps\n"
                    "  replay reset           Rewind loaded replay\n"
                    "  replay status          Show current playback progress\n"
                    "  replay clear           Unload playback\n"
                    "  navigator trace <title>  Display full saved path")
        if action == 'list':
            return self.engine.list_notes()
        if action == 'data':
            if not arg:
                return 'Usage: replay data <six base-60 coordinate values>'
            coord = self.data_manager.coordinate_string(arg)
            messages = self.data_manager.load_coordinate_messages(coord) or []
            if not messages:
                return f"No messages found at '{coord}'."
            lines = [f'COORDINATE DATA: {coord}', f'Messages: {len(messages)} | source: OAIS DataManager', '']
            for index, message in enumerate(messages, 1):
                lines.append(f"{index}. {message.get('title', 'Untitled')}")
                lines.append(f"   Message: {message.get('message', '')}")
                data = message.get('data') or {}
                if data:
                    lines.append('   Data:')
                    for key, value in data.items():
                        lines.append(f'     {key}: {json.dumps(value, ensure_ascii=False)}')
                else:
                    lines.append('   Data: {}')
            return '\n'.join(lines)
        if action == 'load':
            if not arg:
                return 'Usage: replay load <title or ID>'
            return self.engine.load(arg)
        if action == 'next':
            try:
                count = int(arg) if arg else 1
            except ValueError as exc:
                raise ValueError('Step count must be an integer.') from exc
            return self.engine.next(count)
        if action == 'all':
            return self.engine.all()
        if action == 'reset':
            return self.engine.reset()
        if action == 'status':
            return self.engine.summary()
        if action == 'clear':
            self.engine.clear()
            return 'Replay unloaded.'
        if action == 'trace':
            if not arg:
                return 'Usage: replay trace <title or ID>'
            return self.engine.trace(arg)
        # Convenience: 'replay 1' or 'replay cubic_test' displays all commands.
        self.engine.load(raw)
        return self.engine.summary() + '\n' + self.engine.all()
