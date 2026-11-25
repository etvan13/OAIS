"""Historical cleanup opt-in must never remove command blocks or unrelated data."""
import json
from pathlib import Path
import tempfile
import unittest

from oais.utils.data_manager import DataManager
from tools.prune_legacy_poles import prune

class LegacyPoleMigrationTests(unittest.TestCase):
    def test_dry_run_and_backed_up_safe_prune(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = DataManager(base_dir=Path(folder) / 'Data')
            manager.save_pole_function('9 0 0 0 0 0',
                                       {'name':'expression','params':{'f':'k**2'}})
            manager.save_object('9 0 0 0 0 0', 'unrelated', 'another', {'value':'keep'})
            block = manager.save_command_block('9 0 0 0 0 0', 'help', '0'*32)
            manager.save_pole_function('8 0 0 0 0 0',
                                       {'name':'expression','params':{'f':'k**3'}})
            before = manager.get_coordinate_node('9 0 0 0 0 0')
            self.assertIn('pole_function', before['objects'])
            dry = prune(manager.base_dir)
            self.assertFalse(dry['applied'])
            self.assertEqual(dry['pole_objects'], 2)
            self.assertIn('pole_function', manager.get_coordinate_node('9 0 0 0 0 0')['objects'])
            with self.assertRaises(ValueError):
                prune(manager.base_dir, apply=True)
            result = prune(manager.base_dir, apply=True, acknowledge_legacy_breakage=True)
            self.assertTrue(result['applied'])
            node = manager.get_coordinate_node('9 0 0 0 0 0')
            self.assertEqual(node['objects']['unrelated'][0]['value'], 'keep')
            self.assertNotIn('pole_function', node['objects'])
            self.assertEqual(node['command_blocks'], [block])
            self.assertIsNone(manager.get_coordinate_node('8 0 0 0 0 0'))
            self.assertEqual(len(list(manager.coordinate_dir.rglob('*.pole-backup'))), 1)  # Same base-60 storage file

if __name__=='__main__':
    unittest.main()
