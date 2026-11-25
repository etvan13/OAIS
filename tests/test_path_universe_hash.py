"""Pure, versioned path-universe identity: no Navigator or filesystem required."""
import unittest

from oais.utils.virtual_counter import seed_path_universe, evolve_path_universe


class PathUniverseHashTests(unittest.TestCase):
    def test_seed_determinism_and_separation(self):
        a = seed_path_universe('3 0 0 0 0 0', 'note-seed')
        self.assertEqual(a, seed_path_universe('3 0 0 0 0 0', 'note-seed'))
        self.assertNotEqual(a, seed_path_universe('3 0 0 0 0 0', 'different'))
        self.assertNotEqual(a, seed_path_universe('3 0 0 0 0 0', 'note-seed', counter_universe=1))
        self.assertLess(a, 1 << 128)

    def test_history_dependency_direction_and_state_order(self):
        seed = seed_path_universe('3 0 0 0 0 0', 'note-seed')
        a = ['3 0 0 0 0 0', 0, 'pi_0123456789abcdef']
        b = ['4 0 0 0 0 0', 1, 'pi_0123456789abcdef']
        first = evolve_path_universe(seed, a, b, 'away')
        self.assertEqual(first, evolve_path_universe(seed, a, b, 'away'))
        self.assertNotEqual(first, evolve_path_universe(seed, b, a, 'away'))
        self.assertNotEqual(first, evolve_path_universe(seed, a, b, 'toward'))
        self.assertNotEqual(first, evolve_path_universe(seed, a, b, 'away', counter_universe_after=1))
        second = evolve_path_universe(first, b, a, 'toward')
        self.assertNotEqual(second, seed)  # returning to pole does not rewind path history

    def test_hold_at_identical_logical_position_still_evolves(self):
        start = seed_path_universe('6 0 0 0 0 0', 'note-seed')
        state = ['6 0 0 0 0 0', 0, 'linear_offset']
        a = evolve_path_universe(start, state, state, 'hold-event')
        b = evolve_path_universe(a, state, state, 'hold-event')
        self.assertNotEqual(a, b)

    def test_optional_secret_produces_different_chain(self):
        public = seed_path_universe('3 0 0 0 0 0', 'seed')
        keyed = seed_path_universe('3 0 0 0 0 0', 'seed', secret=b'secret key')
        self.assertNotEqual(public, keyed)
        self.assertEqual(keyed, seed_path_universe('3 0 0 0 0 0', 'seed', secret=b'secret key'))
        self.assertNotEqual(keyed, seed_path_universe('3 0 0 0 0 0', 'seed', secret=b'wrong key'))

    def test_bad_input_rejected(self):
        state = ['3 0 0 0 0 0', 0, 'linear_offset']
        with self.assertRaises(ValueError):
            seed_path_universe('3 0 0 0 0 0', '')
        with self.assertRaises(ValueError):
            evolve_path_universe(-1, state, state, 'hold')
        with self.assertRaises(ValueError):
            evolve_path_universe(0, state, state, '')
        with self.assertRaises(ValueError):
            evolve_path_universe(0, state[:2], state, 'away')
        with self.assertRaises(ValueError):
            seed_path_universe('3 0 0 0 0 0', 'seed', secret='not bytes')


if __name__ == '__main__':
    unittest.main()
