"""Sticky Note command for OAIS.

The engine caches commands until save, then DataManager stores them at their
real coordinates. No separate text exports are generated.
"""



class StickyNote:
    def __init__(self, terminal):
        self.terminal = terminal
        self.engine = terminal.sticky_note

    def run(self, arguments=""):
        """Handle one action, or enter the Sticky Note menu without arguments."""
        if arguments.strip():
            return self.process_command(arguments)

        print("\nSTICKY NOTE")
        print("Type 'help' for commands, 'exit' to return.\n")
        # Menu actions are OAIS input when recording across both terminals.
        while True:
            try:
                command = input("Sticky Note> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not command:
                continue
            before_state = self.terminal.begin_nested_input(command)
            text = "sticky " + command
            action = command.split()[0].lower()
            was_active = self.engine.active
            if command.lower() in ("exit", "back"):
                self.terminal.end_nested_input(text, before_state)
                break
            boundary_recorded = False
            if action in ("stop", "save", "clear"):
                boundary_recorded = self.terminal.sticky_boundary_before(text, before_state)
            message = self.process_command(command)
            if boundary_recorded and message.startswith("Could not save Sticky Note:"):
                self.engine.mark_last_failed(text)
            self.terminal.sticky_boundary_after(text, before_state, was_active)
            if message:
                print(message)
        return "Returning to terminal."

    def process_command(self, command):
        action, _, arguments = command.strip().partition(" ")
        action = action.lower()
        arguments = arguments.strip()

        if action == "help":
            return (
                "Sticky Note commands:\n"
                "  start         Start recording all commands\n"
                "  stop          Stop recording; keep the temporary path\n"
                "  status        Show recording state\n"
                "  path          Show the temporary command path\n"
                "  save <title>  Commit the cached path to OAIS coordinates\n"
                "  list [type] [page]  Browse saved paths (all, commands, conversations, text, files)\n"
                "  search <title>      Search saved note titles\n"
                "  read <title>  Read saved information (commands also support replay)\n"
                "  clear         Discard the temporary path\n"
                "  exit          Return to the terminal"
            )

        if action == "start":
            if self.engine.active:
                return "Recording is already active."
            if self.engine.get_path():
                return "A temporary path exists. Save or clear it before starting again."
            self.engine.start(clear=True, metadata={
                "scope": "all", "storage": "logical"})
            virtual = self.terminal.virtual_counter.logical_address()
            return f"Recording started at virtual {virtual}."

        if action == "stop":
            self.engine.stop()
            return f"Recording stopped. {len(self.engine.get_path())} events retained."

        if action == "status":
            state = self.engine.status()
            label = "PAUSED" if state["paused"] else "ON" if state["active"] else "OFF"
            if self.engine.session_metadata.get("storage") == "logical":
                return (f"Recording: {label} | Events: {state['event_count']} | "
                        f"Virtual: {self.terminal.virtual_counter.logical_address()}")
            return (
                f"Recording: {label} | Events: {state['event_count']} | "
                f"Start: {state['start_coordinate']} | "
                f"Current: {state['current_coordinate']}"
            )

        if action == "path":
            path = self.engine.get_path()
            if not path:
                return "Temporary path is empty."
            return "TEMPORARY PATH\n" + "\n".join(
                self.format_event(event, index)
                for index, event in enumerate(path, 1)
            )

        if action == "save":
            return self.save_note(arguments or "Sticky Note")

        if action == "clear":
            self.engine.stop(clear=True)
            return "Temporary path cleared."

        if action in ("list", "search"):
            aliases = {"all": None, "commands": "command", "conversations": "conversation", "files": "file", "command": "command", "conversation": "conversation", "file": "file", "text": "text"}
            kind, page, query = None, 1, ""
            if action == "search":
                query = arguments
            else:
                parts = arguments.lower().split()
                if parts and parts[0] in aliases:
                    kind = aliases[parts.pop(0)]
                if len(parts) > 1 or (parts and not parts[0].isdigit()):
                    return "Usage: list [all|commands|conversations|text|files] [page]"
                if parts:
                    page = int(parts[0])
            try:
                result = self.engine.browse_notes(kind, query=query, page=page)
            except ValueError as exc:
                return str(exc)
            if not result["total"]:
                return "No saved Sticky Notes matching this selection."
            lines = [f"SAVED STICKY NOTES | Page {page}/{result['pages']} | {result['total']} notes"]
            lines.extend(f"  {n['number']}. {n['title']} [{n['id']}] ({n['type']})" for n in result["items"])
            if not result["items"]:
                lines.append("Page out of range.")
            lines.append("Use read <title or ID> or replay for interactive browsing.")
            return "\n".join(lines)

        if action == "read":
            if not arguments:
                return "Usage: read <title or ID>"
            try:
                note, events = self.engine.load_path(arguments)
            except KeyError:
                return f"No Sticky Note named '{arguments}'."
            except (ValueError, NotImplementedError) as exc:
                return f"Cannot read Sticky Note: {exc}"
            lines = [
                f"STICKY NOTE: {note.get('title', arguments)}",
                f"Start: {note.get('start', note.get('start_coordinate', '?')) if isinstance(note.get('start'), str) else (note.get('start') or [note.get('start_coordinate', '?')])[0]}",
                f"End: {note.get('end', note.get('end_coordinate', '?')) if isinstance(note.get('end'), str) else (note.get('after') or [note.get('end_coordinate', '?')])[0]}",
                f"Events: {len(events)}",
                "",
                "PATH",
            ]
            lines.extend(self.format_event(event, index)
                         for index, event in enumerate(events, 1))
            return "\n".join(lines)

        return "Unknown Sticky Note command. Type 'help'."

    def save_note(self, title):
        """Commit cached commands to coordinate storage only."""
        was_active = self.engine.active and not self.engine.paused
        if was_active:
            self.engine.pause()
        if not self.engine.get_path():
            if was_active:
                self.engine.resume()
            return "Nothing to save. Start recording and run some commands first."
        try:
            saved = self.engine.save_reference(title=title)
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            if was_active:
                self.engine.resume()
            return f"Could not save Sticky Note: {exc}. Temporary path retained."
        self.engine.stop(clear=True)
        return f"Saved '{saved['title']}' to OAIS DataManager. Temporary path cleared."

    @staticmethod
    def format_event(event, index):
        """Include both coordinates so moves and revisits are visible."""
        if not isinstance(event, dict):
            return f"{index}. {event}"
        kind = event.get("type", "command")
        value = event.get("value", "")
        if kind == "conversation":
            text = f"{index}. [CONVERSATION @ {event.get('coordinate_before', '?')}]\nUser:\n{value['user']}\n\nAssistant:\n{value['assistant']}"
            if event.get("attachments"):
                text += "\nAttachments: " + ", ".join(event["attachments"])
            return text
        if kind in ("text", "file"):
            return f"{index}. [{kind.upper()} @ {event.get('coordinate_before', '?')}] {value}"
        before = event.get("coordinate_before", event.get("coordinate", "?"))
        after = event.get("coordinate_after", before)
        command = event.get("value", "")
        source = event.get("source", "oais").upper()
        result = " [failed]" if event.get("success") is False else ""
        if event.get("type") == "transition":
            return f"{index}. [META] {command} ({event.get('from')} -> {event.get('to')}) @ [{after}]"
        if event.get("from_plan"):
            return f"{index}. [{source}] {command}{result}"
        if "logical_before" in event:
            v = event["logical_before"]
            w = event.get("logical_after", v)
            return (f"{index}. [{source} virtual:{v[0]} | k={v[1]} | "
                    f"f={v[2]} | U={v[3]}] {command} "
                    f"-> [virtual:{w[0]} | U={w[3]}]"
                    f"{result}")
        return f"{index}. [{source}: {before}] {command} -> [{after}]{result}"
