# Base/utils/counter.py
# Formatting-only copy: original behavior and signatures preserved.

import os
import json
from pathlib import Path


BASE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_ROOT / 'Base_Data'
DATA_DIR.mkdir(parents=True, exist_ok=True)
C_PATH = DATA_DIR / 'current_coordinate.json'
BACKUP_PATH = DATA_DIR / 'current_coordinate.bak'


class Counter:

    def __init__(self, load_state=True, save_path=None):
        self.save_path = Path(save_path) if save_path is not None else C_PATH
        self.backup_path = self.save_path.with_suffix(".bak") if save_path is not None else BACKUP_PATH
        self.counters = [0] * 6
        self.universes = 0
        if load_state:
            self.load_counters()

    # --- Copy ---
    def copy(self):
        new_counter = Counter(load_state=False, save_path=self.save_path)
        new_counter.counters = self.counters[:]
        new_counter.universes = self.universes
        return new_counter

    # --- Observe external state ---
    def sync(self, coordinate, universes=None, save=False):
        """
        Synchronize OAIS with the state of the system
        OAIS is currently observing.

        When attached to DEEP, DEEP is authoritative.

        save=False is intentional for normal runtime syncing.
        We don't want every DEEP command causing disk I/O.
        """
        if isinstance(coordinate, str):
            coordinate = self.parse_coordinate(coordinate)
        if not self._valid_coordinate_list(coordinate):
            raise ValueError('Invalid coordinate supplied to OAIS Counter.')
        self.counters = list(coordinate)
        if universes is not None:
            self.universes = universes
        if save:
            self.save_counters()

    # --- Load ---
    def load_counters(self):
        if self.save_path.exists():
            try:
                with self.save_path.open('r', encoding='utf-8') as source:
                    data = json.load(source)
                coordinate = data.get('coordinate_list')
                if self._valid_coordinate_list(coordinate):
                    self.counters = coordinate
                    self.universes = data.get('universes', 0)
                    return
            except (json.JSONDecodeError, OSError):
                print(f'{self.save_path} corrupted. Attempting OAIS backup...')
        if self.backup_path.exists():
            try:
                raw = self.backup_path.read_text(encoding='utf-8').strip()
                parts = raw.split()
                if len(parts) == 6 and all((part.isdigit() and 0 <= int(part) < 60 for part in parts)):
                    self.counters = [int(part) for part in parts]
                    self.universes = 0
                    self.save_counters()
                    return
            except OSError:
                pass
        self.counters = [0] * 6
        self.universes = 0

    # --- Save ---
    def save_counters(self):
        self.save_path.parent.mkdir(parents=True, exist_ok=True)
        data = {'coordinate': self.get_counters(), 'coordinate_list': list(self.counters), 'universes': self.universes}
        temporary = Path(str(self.save_path) + '.tmp')
        with temporary.open('w', encoding='utf-8') as output:
            json.dump(data, output, indent=4)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.save_path)
        if self.counters[0] == 34:
            try:
                self.backup_path.write_text(self.get_counters(), encoding='utf-8')
            except OSError as exc:
                print(f'Could not write OAIS coordinate backup: {exc}')

    # --- Movement ---
    def increment(self):
        self._update_counters(1)
        self.save_counters()

    def decrement(self):
        self._update_counters(-1)
        self.save_counters()

    def spec_change(self, value):
        self._update_counters(value)
        self.save_counters()

    def _update_counters(self, delta):
        for index in range(len(self.counters)):
            self.counters[index] += delta
            if delta > 0 and self.counters[index] >= 60:
                self.counters[index] %= 60
                if index == len(self.counters) - 1:
                    self.universes += 1
                continue
            if delta < 0 and self.counters[index] < 0:
                self.counters[index] = 59
                if index == len(self.counters) - 1:
                    self.universes -= 1
                continue
            break

    # --- Coordinate validation ---
    @staticmethod
    def _valid_coordinate_list(coordinate):
        return isinstance(coordinate, list) and len(coordinate) == 6 and all((isinstance(value, int) and 0 <= value < 60 for value in coordinate))

    @staticmethod
    def parse_coordinate(coord_str):
        parts = coord_str.split()
        if len(parts) != 6 or not all((part.isdigit() and int(part) < 60 for part in parts)):
            raise ValueError('Invalid coordinate format. Expected: ## ## ## ## ## ##')
        return [int(part) for part in parts]

    # --- Access ---
    def get_counters(self):
        return ' '.join(map(str, self.counters))

    def get_counters_list(self):
        return list(self.counters)

    # --- Base-60 helpers ---
    def baseTenConv(self, digits=None):
        if digits is None:
            digits = self.counters
        return sum((digit * 60 ** index for index, digit in enumerate(digits)))

    def strCoord_conv(self, number):
        number %= 60 ** 6
        digits = []
        while number > 0:
            digits.append(number % 60)
            number //= 60
        while len(digits) < 6:
            digits.append(0)
        return ' '.join((str(value).zfill(2) for value in digits))

    def coord_conv(self, number):
        number %= 60 ** 6
        digits = []
        while number > 0:
            digits.append(number % 60)
            number //= 60
        while len(digits) < 6:
            digits.append(0)
        return digits

    def univ_count(self, number):
        return number // 60 ** 6

    def calculate_distance(self, ref_counter):
        current = self.baseTenConv()
        if isinstance(ref_counter, list):
            target = self.baseTenConv(ref_counter)
        else:
            target = ref_counter.baseTenConv()
        return self.coord_conv(target - current)
