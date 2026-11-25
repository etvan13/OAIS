"""OAIS alone, no observed external program or Meta input proxy."""
from pathlib import Path
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager


class StandaloneConnection:
    name = "standalone"

    def __init__(self, meta):
        self.meta = meta

    def run(self, **kwargs):
        data = Path(self.meta.data_dir)
        terminal = OaisTerminal(
            counter=Counter(load_state=True, save_path=data / "current_coordinate.json"),
            data_manager=DataManager(base_dir=data), terminal_id="oais_standalone",
            persist_virtual_state=True,
        )
        return terminal.run(**kwargs)
