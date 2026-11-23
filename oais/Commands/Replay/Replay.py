"""Terminal adapter for read-only coordinate path playback and data inspection."""

import json


class Replay:
    def __init__(self, terminal):
        self.engine = terminal.replay_engine
        self.data_manager = terminal.data_manager

    def run(self, arguments=""):
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
                    "  replay <title>         Load and show entire coordinate path\n"
                    "  replay load <title>    Load saved note at its coordinate\n"
                    "  replay data <60_coord> Read messages and JSON data at a coordinate\n"
                    "  replay next [count]    Advance through recorded steps\n"
                    "  replay all             Show remaining steps\n"
                    "  replay reset           Rewind loaded replay\n"
                    "  replay status          Show current playback progress\n"
                    "  replay clear           Unload playback\n"
                    "  navigator trace <title>  Display entire coordinate-derived path")
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
        # Convenience: 'replay cubic_test' means load and display everything.
        self.engine.load(raw)
        return self.engine.summary() + '\n' + self.engine.all()
