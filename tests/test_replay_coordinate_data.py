"""Coordinate message inspection through the replay command."""
import tempfile
import unittest
from pathlib import Path
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager

class ReplayCoordinateDataTests(unittest.TestCase):
    def test_metadata_and_no_live_navigation_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm = DataManager(base_dir=Path(tmp)/'data')
            term = OaisTerminal(counter=Counter(load_state=False, save_path=Path(tmp)/'state.json'), data_manager=dm)
            term.attach_host('5 0 0 0 0 0')
            coord = '34 34 34 34 34 34'
            dm.create_coordinate_message(coord, 'Kaus', 'kaus was here', extra_data={'color':'orange','colors':['orange','blue']})
            before = term.navigator_engine.snapshot()
            result = term.process_command('replay data '+coord).output
            self.assertIn('kaus was here',result)
            self.assertIn('color: "orange"',result)
            self.assertIn('colors: ["orange", "blue"]',result)
            self.assertEqual(before,term.navigator_engine.snapshot())
            self.assertIn('No messages found',term.process_command('replay data 1 2 3 4 5 6').output)
            self.assertIn('Usage:',term.process_command('replay data').output)
            self.assertIn('Coordinate values must be between 0 and 59',term.process_command('replay data 60 0 0 0 0 0').output)

if __name__=='__main__': unittest.main()
