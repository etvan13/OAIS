"""Terminal adapter for read-only coordinate path playback and data inspection."""

import json


class Replay:
    def __init__(self, terminal):
        self.terminal = terminal
        self.engine = terminal.replay_engine
        self.data_manager = terminal.data_manager

    def run(self, arguments="", *, input_func=input, print_func=print):
        if not arguments.strip():
            print_func("\nREPLAY — SAVED STICKY NOTES")
            print_func(self.engine.list_notes(None))
            print_func("Type a note number, title, or ID. 'list' refreshes; 'exit' returns.\n")
            while True:
                try:
                    choice = input_func("Replay> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print_func("")
                    break
                if not choice:
                    continue
                text = choice if choice.lower().startswith("replay ") else "replay " + choice
                if choice.lower() in ("exit", "back", "return"):
                    self.terminal.record_inspection(text)
                    break
                try:
                    print_func(self._run(choice))
                    self.terminal.record_inspection(text)
                except (KeyError, ValueError, TypeError, NotImplementedError) as exc:
                    self.terminal.record_inspection(text, success=False)
                    print_func(f"Replay error: {exc}")
            return "Returning to OAIS terminal."
        try:
            return self._run(arguments)
        except KeyError as exc:
            return f"Saved Sticky Note not found: {exc}"

    def _run(self, arguments=""):
        raw = arguments.strip()
        # Accept both menu-local commands and their prefixed forms.
        if raw.lower().startswith("replay "):
            raw = raw[7:].strip()
        action, _, arg = raw.partition(' ')
        action = action.lower()
        arg = arg.strip()
        if not action or action in ('help', '?'):
            return ("Replay commands (read-only; never re-executes commands):\n"
                    "  replay                Choose a saved Sticky Note interactively\n"
                    "  replay list [type] [page]  Browse commands, conversations, text, files or all\n"
                    "  replay search <title> Search the current type; search alone clears\n"
                    "  replay page N / more / prev  Browse note pages\n"
                    "  replay <number/title>  Show commands or the first data block\n"
                    "  replay full <title>   Show complete OAIS + host history\n"
                    "  replay view host/full Change view and rewind\n"
                    "  replay load <title>    Load note for step-by-step inspection\n"
                    "  replay data <6 digits> Read messages and JSON data at a coordinate\n"
                    "  replay next [count]    Advance through recorded steps\n"
                    "  replay all             Show remaining steps\n"
                    "  replay reset           Rewind loaded replay\n"
                    "  replay status          Show current playback progress\n"
                    "  replay clear           Unload playback\n"
                    "  navigator trace <title>  Display full saved path")
        if action == 'view':
            return self.engine.set_view(arg.lower())
        if action == 'full':
            if not arg:
                return self.engine.set_view('full')
            self.engine.load(arg, view='full')
            return self.engine.summary() + '\n' + self.engine.all()
        if action == 'list':
            aliases = {"all": None, "commands": "command", "conversations": "conversation", "files": "file", "command": "command", "conversation": "conversation", "text": "text", "file": "file"}
            parts = arg.lower().split()
            kind = self.engine.browser_type
            if parts and parts[0] in aliases:
                kind = aliases[parts.pop(0)]
            if len(parts) > 1 or (parts and not parts[0].isdigit()):
                raise ValueError("Usage: replay list [all|commands|conversations|text|files] [page]")
            return self.engine.list_notes(kind, page=int(parts[0]) if parts else 1)
        if action == 'search':
            return self.engine.list_notes(self.engine.browser_type, query=arg)
        if action in ('page', 'more', 'prev'):
            if action == 'page':
                if not arg.isdigit():
                    raise ValueError("Usage: replay page <positive number>")
                page = int(arg)
            else:
                page = max(1, self.engine.browser_page + (1 if action == 'more' else -1))
                if action == 'more' and self.engine.browser_result is not None:
                    page = min(page, max(1, self.engine.browser_result["pages"]))
            return self.engine.list_notes(self.engine.browser_type, query=self.engine.browser_query, page=page, limit=self.engine.browser_limit)
        if action == 'data':
            if not arg:
                return 'Usage: replay data <six base-60 coordinate values>'
            coord = self.data_manager.coordinate_string(arg)
            messages = self.data_manager.load_coordinate_messages(coord) or []
            blocks = self.data_manager.get_blocks_at_coordinate(coord)
            if not messages and not blocks:
                return f"No messages found at '{coord}'. No typed blocks found."
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
            if blocks:
                lines.append(f"\nTyped blocks: {len(blocks)}")
                for index, block in enumerate(blocks, 1):
                    lines.append(f"{index}. {block['type']}: {json.dumps(block, ensure_ascii=False)}")
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
        # Preserve command-history convenience, but avoid flooding the screen
        # with an entire conversation or other long data path by default.
        self.engine.load(raw)
        summary = self.engine.summary()
        if self.engine.note.get("storage") == "functional_data_v1":
            return summary + '\n' + self.engine.next() + '\nUse next [count] or all to read more.'
        return summary + '\n' + self.engine.all()
