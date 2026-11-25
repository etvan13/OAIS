"""BASE host connection: an independent, coordinate-aware terminal.

Only this adapter knows about BASE; OAIS has no BASE imports.
"""
from pathlib import Path
import shutil
import warnings

from Base.Base_Terminal import BaseTerminal
from Base.utils.counter import Counter
from Base.utils.data_manager import DataManager


class BaseConnection:
    name = "base"
    terminal_id = "base"
    has_coordinates = True
    prompt_pattern = r"\[\d+(?: \d+){5}\] BASE > $"
    display_name = "BASE"

    def __init__(self, meta):
        self.meta = meta

    def create_host(self, start, base_data_dir=None):
        root = Path(__file__).resolve().parents[2]
        path = Path(base_data_dir) if base_data_dir else root / "Base" / "Base_Data"
        legacy = root / "oais" / "Base_Data"
        # One-time relocation of the original BASE data. Never silently merge
        # two data stores or overwrite the destination's existing files.
        if base_data_dir is None and legacy.is_dir():
            if not path.exists() or not any(path.iterdir()):
                if path.exists():
                    path.rmdir()
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(legacy), str(path))
            else:
                warnings.warn(f"Old BASE data at {legacy} was not moved because "
                              f"{path} already contains data. Merge manually.",
                              stacklevel=2)
        return BaseTerminal(
            starting_coordinate=start,
            counter=Counter(load_state=False, save_path=path / "current_coordinate.json"),
            data_manager=DataManager(base_dir=path),
        )

    @staticmethod
    def prompt(host):
        return f"[{host.counter.get_counters()}] BASE > "

    @staticmethod
    def event(command, result):
        return {
            "type": "command", "value": command.strip(), "source": "base",
            "success": result.success,
            "coordinate_before": result.coordinate_before,
            "coordinate_after": result.coordinate_after,
            "universe_before": result.universe_before,
            "universe_after": result.universe_after,
            "output": result.output,
        }

    @classmethod
    def resume_prompt(cls, coordinate):
        return f"[{coordinate}] BASE > "

    def initial_event(self, start):
        return {"type": "state", "source": self.name,
                "coordinate_after": start, "universe_after": 0}

    def run(self, **kwargs):
        return self.meta.run_connected(self, **kwargs)

    def run_standalone(self, **kwargs):
        return self.create_host(self.meta.starting_coordinate, self.meta.base_data_dir).run(**kwargs)
