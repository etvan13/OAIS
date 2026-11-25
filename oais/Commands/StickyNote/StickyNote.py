"""Sticky Note command for OAIS.

The engine caches commands until save, then DataManager stores them at their
real coordinates. Text files are optional, human-readable exports.
"""

from datetime import datetime, timezone
from pathlib import Path
import re


class StickyNote:
    def __init__(self, terminal, save_dir=None):
        self.terminal = terminal
        self.engine = terminal.sticky_note
        self.save_dir = (
            Path(save_dir)
            if save_dir is not None
            else Path(terminal.data_manager.base_dir).parent / "Exports" / "sticky_notes"
        )

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
            if command.lower() in ("exit", "back"):
                self.terminal.end_nested_input(command, before_state)
                break
            message = self.process_command(command)
            self.terminal.end_nested_input(command, before_state)
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
                "  start         Start recording the current terminal scope\n"
                "  stop          Stop recording; keep the temporary path\n"
                "  status        Show recording state\n"
                "  path          Show the temporary command path\n"
                "  save <title>  Commit the cached path to OAIS coordinates\n"
                "  list          List saved coordinate paths\n"
                "  read <title>  Read saved commands (or use 'replay')\n"
                "  clear         Discard the temporary path\n"
                "  exit          Return to the terminal"
            )

        if action == "start":
            if self.engine.active:
                return "Recording is already active."
            if self.engine.get_path():
                return "A temporary path exists. Save or clear it before starting again."
            self.engine.start(clear=True, metadata={
                "scope": self.terminal.recording_scope, "storage": "logical"})
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
            return self.save_text(arguments or "Sticky Note")

        if action == "clear":
            self.engine.stop(clear=True)
            return "Temporary path cleared."

        if action == "list":
            notes = self.engine.list_notes()
            if notes:
                return "SAVED STICKY NOTES\n" + "\n".join(
                    f"  {note.get('title', 'Untitled')} [{note['id']}]"
                    for note in notes
                )
            # Old text-only recordings remain available.
            files = sorted(self.save_dir.glob("*.txt")) if self.save_dir.exists() else []
            if files:
                return "LEGACY TEXT NOTES\n" + "\n".join(
                    f"  {file.stem}" for file in files
                )
            return "No saved Sticky Notes."

        if action == "read":
            if not arguments:
                return "Usage: read <title or ID>"
            try:
                note, events = self.engine.load_path(arguments)
            except KeyError:
                # Older versions saved only a .txt export.
                file = self.save_dir / (self.filename(arguments) + ".txt")
                if file.is_file():
                    return file.read_text(encoding="utf-8")
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

    def save_text(self, title):
        """Commit cached commands to DataManager and export a readable .txt.

        No coordinate writes happen before this method is called. If any
        coordinate write fails, the engine retains its cache and attempts
        to remove the partially written coordinate records.
        """
        was_active = self.engine.active and not self.engine.paused
        if was_active:
            self.engine.pause()  # fixed snapshot during multi-file commit
        path = self.engine.get_path()
        if not path:
            if was_active:
                self.engine.resume()
            return "Nothing to save. Start recording and run some commands first."

        file = None
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            stem = self.filename(title)
            file = self.save_dir / f"{stem}.txt"
            number = 2
            while file.exists():
                file = self.save_dir / f"{stem}_{number}.txt"
                number += 1

            lines = [
                f"STICKY NOTE: {title}",
                f"Saved: {datetime.now(timezone.utc).isoformat()}",
                f"Start: {path[0].get('logical_before', path[0].get('coordinate_before', self.engine.start_coordinate))}",
                f"End: {path[-1].get('logical_after', path[-1].get('coordinate_after', self.engine.current_coordinate()))}",
                f"Events: {len(path)}",
                "",
                "PATH",
            ]
            lines.extend(self.format_event(event, index)
                         for index, event in enumerate(path, 1))
            file.write_text("\n".join(lines) + "\n", encoding="utf-8")

            # DataManager is authoritative; the .txt is a convenience export.
            saved = self.engine.save_reference(title=title)
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            if file is not None and file.is_file():
                try:
                    file.unlink()
                except OSError:
                    pass
            if was_active:
                self.engine.resume()
            return f"Could not save Sticky Note: {exc}. Temporary path retained."

        self.engine.stop(clear=True)
        return (f"Saved '{saved['title']}' to OAIS DataManager "
                f"and {file}. Temporary path cleared.")

    @staticmethod
    def filename(title):
        """Limit titles to safe, local filename characters."""
        return re.sub(r"[^a-z0-9_-]+", "_", title.strip().lower()).strip("_") or "sticky_note"

    @staticmethod
    def format_event(event, index):
        """Include both coordinates so moves and revisits are visible."""
        if not isinstance(event, dict):
            return f"{index}. {event}"
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
