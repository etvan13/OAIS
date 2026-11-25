"""Functional Navigator regression tests against the four-part foundation."""
import json
from pathlib import Path
import tempfile
import unittest

from oais.Commands.Navigator.NavigatorEngine import (
    NavigatorEngine, function_definition, evaluate_offset,
)
from oais.Commands.Navigator.Navigator import Navigator
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager
from oais.utils.virtual_counter import VirtualCounter, SPACE


def pure_nav(start='3 0 0 0 0 0', universe=0):
    v = VirtualCounter()
    v.observe_host(start, universe)
    return NavigatorEngine(v)


def loc(engine):
    state = engine.virtual.snapshot()
    return state['coordinate'], state['counter_universe']


class NavigatorEngineTests(unittest.TestCase):
    def test_registry_is_explicit_integer_valued_and_rejects_unknown(self):
        self.assertEqual([evaluate_offset(function_definition('cubic_offset'), k)
                          for k in range(4)], [0, 1, 8, 27])
        self.assertEqual([evaluate_offset(function_definition('wave_offset'), k)
                          for k in range(9)], [0, 1, 2, 1, 0, -1, -2, -1, 0])
        self.assertEqual(evaluate_offset(function_definition('constant_offset'), 1234), 0)
        with self.assertRaises(ValueError):
            function_definition('eval(user_input)')
        with self.assertRaises(ValueError):
            function_definition('cubic_offset', {'scale': 1.2})
        with self.assertRaises(ValueError):
            function_definition('cubic_offset', {'other': 1})

    def test_cubic_exact_retrace_one_step_turn_and_ever_evolving_universe(self):
        n = pure_nav()
        n.open_pole('cubic_offset', seed='stable', activation_id='pi_' + 'a'*16)
        xs = [loc(n)[0]]
        us = [n.virtual.path_universe]
        for operation in [n.away, n.away, n.away, n.turn, n.toward, n.toward]:
            operation()
            xs.append(loc(n)[0])
            us.append(n.virtual.path_universe)
        self.assertEqual([int(x.split()[0]) for x in xs], [3, 4, 11, 30, 11, 4, 3])
        self.assertEqual(len(set(us)), 7)
        self.assertFalse(n.active)
        self.assertFalse(n.auto_enabled)
        self.assertEqual(n.virtual.mode, 'free')
        self.assertEqual(n.virtual.direction, 'linear')
        self.assertEqual(n.virtual.logical_address()[1:3], [[], 'linear_offset'])

    def test_backward_and_forward_position_functions(self):
        n = pure_nav()
        n.open_pole('linear_offset', {'slope': -1}, seed='a')
        n.away(); n.away()
        self.assertEqual(loc(n)[0], '1 0 0 0 0 0')
        n.turn(); n.toward()
        self.assertEqual(loc(n)[0], '3 0 0 0 0 0')
        n.open_pole('linear_offset', {'slope': 1}, seed='b')
        n.away(); n.away(); n.away()
        self.assertEqual(loc(n)[0], '6 0 0 0 0 0')

    def test_constant_real_coordinate_with_distinct_logical_addresses(self):
        n = pure_nav('6 0 0 0 0 0')
        n.open_pole('constant_offset', seed='constant')
        addresses = [n.virtual.logical_address()]
        for method in [n.away, n.away, n.turn, n.toward]:
            method()
            addresses.append(n.virtual.logical_address())
        self.assertEqual({addr[0] for addr in addresses}, {'6 0 0 0 0 0'})
        self.assertEqual(len({addr[-1] for addr in addresses}), len(addresses))
        self.assertEqual([addr[1][0]['step'] if addr[1] else 0 for addr in addresses],
                         [0,1,2,1,0])
        self.assertEqual(addresses[3][1][0]['leg'], 'toward')

    def test_nested_turn_resumes_frozen_parent_and_registers_unique_pole(self):
        stored = []
        n = pure_nav()
        n.on_open = lambda frame, entry_seed=None: stored.append((frame, entry_seed))
        n.open_pole('linear_offset', {'slope':-1}, seed='nested')
        xs = [loc(n)[0]]
        for operation in [n.away, n.away, n.turn, n.turn, n.turn, n.toward]:
            operation(); xs.append(loc(n)[0])
        self.assertEqual([int(x.split()[0]) for x in xs], [3,2,1,2,1,2,3])
        self.assertFalse(n.active)
        self.assertEqual(len(stored), 2)
        self.assertEqual(stored[0][0]['pole_real'], '3 0 0 0 0 0')
        self.assertEqual(stored[1][0]['pole_real'], '2 0 0 0 0 0')
        self.assertEqual(stored[1][0]['opened_at'], {'parent_step':1,'parent_leg':'toward'})
        self.assertNotEqual(stored[0][0]['id'], stored[1][0]['id'])

    def test_child_with_different_function_and_unfinished_snapshot(self):
        n = pure_nav()
        n.open_pole('linear_offset', {'slope': -1}, seed='ch')
        n.away(); n.away(); n.turn()  # parent at real=2, k1/toward
        parent_id = n.layers[0]['id']
        n.open_child('cubic_offset', {'scale':2})  # 2 + 2*1^3 = 4
        self.assertEqual(loc(n)[0], '4 0 0 0 0 0')
        n.away()  # 2 + 2*8 = 18
        self.assertEqual(loc(n)[0], '18 0 0 0 0 0')
        snapshot = json.loads(json.dumps(n.snapshot()))
        restored = pure_nav()
        restored.restore(snapshot)
        self.assertEqual(restored.snapshot()['virtual']['path_universe'],
                         snapshot['virtual']['path_universe'])
        for operation in ['turn','toward','toward']:
            getattr(n, operation)()
            getattr(restored, operation)()
            self.assertEqual(n.virtual.logical_address(), restored.virtual.logical_address())
        self.assertEqual(loc(n)[0], '3 0 0 0 0 0')
        self.assertFalse(n.active)
        self.assertEqual(parent_id, snapshot['layers'][0]['id'])

    def test_wave_can_revisit_positions_while_depth_advances(self):
        n = pure_nav('3 0 0 0 0 0')
        n.open_pole('wave_offset', seed='w')
        positions, states = [], []
        for _ in range(8):
            n.away()
            positions.append(loc(n)[0])
            states.append(n.virtual.logical_address())
        self.assertEqual([int(x.split()[0]) for x in positions], [4,5,4,3,2,1,2,3])
        self.assertEqual(len({x[-1] for x in states}), 8)
        for i in range(8):
            n.turn() if i == 0 else n.toward()
        self.assertFalse(n.active)
        self.assertEqual(loc(n)[0], '3 0 0 0 0 0')

    def test_counter_overflow_is_not_path_universe(self):
        n = pure_nav('59 59 59 59 59 59')
        n.open_pole('linear_offset', seed='rollover')
        n.away()
        self.assertEqual(loc(n), ('0 0 0 0 0 0', 1))
        self.assertGreater(n.virtual.path_universe, 0)
        n.turn()
        self.assertEqual(loc(n), ('59 59 59 59 59 59', 0))
        m = pure_nav('0 0 0 0 0 0')
        m.open_pole('linear_offset', {'slope':-1}, seed='negative')
        m.away()
        self.assertEqual(loc(m), ('59 59 59 59 59 59', -1))

    def test_automatic_progression_pause_resume_and_root_completion(self):
        n = pure_nav()
        n.open_pole('cubic_offset', seed='automatic')
        n.advance_automatic(); n.advance_automatic()
        self.assertEqual(loc(n)[0], '11 0 0 0 0 0')
        n.pause()
        self.assertIsNone(n.advance_automatic())
        n.resume(); n.advance_automatic()
        self.assertEqual(loc(n)[0], '30 0 0 0 0 0')
        n.turn()
        n.advance_automatic(); n.advance_automatic()
        self.assertFalse(n.active)
        self.assertIsNone(n.advance_automatic())

    def test_invalid_turn_and_pole_do_not_change_state(self):
        n = pure_nav()
        with self.assertRaises(ValueError):
            n.turn()
        n.open_pole('cubic_offset', seed='known')
        before = n.snapshot()
        with self.assertRaises(ValueError):
            n.turn()  # apex at zero
        self.assertEqual(n.snapshot(), before)
        n.away()
        with self.assertRaises(ValueError):
            n.open_pole('linear_offset')
        with self.assertRaises(ValueError):
            n.open_child('linear_offset')  # not returning

    def test_pole_register_failure_does_not_move_live_state(self):
        n = pure_nav()
        before = n.snapshot()
        def fail(*args, **kwargs):
            raise OSError('Disk full')
        n.on_open = fail
        with self.assertRaises(OSError):
            n.open_pole('cubic_offset')
        self.assertEqual(n.snapshot(), before)

    def test_snapshot_corruption_rejected_without_movement(self):
        n = pure_nav()
        n.open_pole('cubic_offset', seed='stable')
        n.away()
        saved = n.snapshot()
        broken = json.loads(json.dumps(saved))
        broken['virtual']['coordinate'] = '9 0 0 0 0 0'
        other = pure_nav()
        before = other.snapshot()
        with self.assertRaises(ValueError):
            other.restore(broken)
        self.assertEqual(other.snapshot(), before)


class NavigatorTerminalTests(unittest.TestCase):
    def new_terminal(self, tmp):
        return OaisTerminal(
            counter=Counter(load_state=False, save_path=Path(tmp)/'standalone.json'),
            data_manager=DataManager(base_dir=Path(tmp)/'data'))

    def test_function_stays_in_virtual_state_without_coordinate_pole_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            o = self.new_terminal(tmp)
            o.attach_host('3 0 0 0 0 0')
            reply = o.navigator_command('open cubic')
            self.assertIn('Opened pole', reply)
            pole = o.data_manager.get_objects_at_coordinate('3 0 0 0 0 0','pole_function')
            self.assertEqual(pole, [])
            self.assertEqual(o.navigator_engine.compact_state()['functions'][0]['f'], 'k**3')
            # Ordinary host command advances once, host before/after are real
            o.observe_event({'type':'command', 'source':'base','value':'help',
                'coordinate_before':'3 0 0 0 0 0', 'coordinate_after':'4 0 0 0 0 0',
                'universe_after':0})
            self.assertEqual(o.virtual_counter.coordinate, '4 0 0 0 0 0')
            o.observe_event({'type':'command', 'source':'base','value':'hello',
                'coordinate_before':'4 0 0 0 0 0','coordinate_after':'5 0 0 0 0 0',
                'universe_after':0})
            self.assertEqual(o.virtual_counter.coordinate, '11 0 0 0 0 0')
            self.assertEqual(o.host_counter.get_counters(), '5 0 0 0 0 0')
            self.assertEqual(o.data_manager.get_objects_at_coordinate('3 0 0 0 0 0','pole_function'), [])
            self.assertEqual(o.data_manager.get_objects_at_coordinate('11 0 0 0 0 0','pole_function'), [])
            self.assertEqual(o.data_manager.get_objects_at_coordinate('11 0 0 0 0 0','logical_command'), [])

    def test_checkpoint_restore_from_self_contained_terminal_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            o = self.new_terminal(tmp)
            o.attach_host('3 0 0 0 0 0')
            o.navigator_command('open backward')
            o.navigator_command('away')
            o.navigator_command('away')
            o.navigator_command('turn')
            o.navigator_command('child cubic scale=2')
            o.navigator_command('away')
            checkpoint = Navigator(o).checkpoint()
            self.assertIn('definition', str(checkpoint))
            self.assertEqual(o.data_manager.list_objects('pole_function'), [])
            original_address = o.virtual_counter.logical_address()
            restart = self.new_terminal(tmp)
            restart.attach_host('8 0 0 0 0 0')  # different host, still independent
            restored = Navigator(restart).restore()
            self.assertEqual(restart.virtual_counter.logical_address(), original_address)
            self.assertEqual(restored['layers'][1]['definition']['name'],'cubic_offset')
            for op in ('turn','toward'):
                getattr(o.navigator_engine, op)()
                getattr(restart.navigator_engine, op)()
                self.assertEqual(restart.virtual_counter.logical_address(),
                                 o.virtual_counter.logical_address())
            self.assertEqual(restart.host_counter.get_counters(), '8 0 0 0 0 0')

    def test_virtual_hold_pauses_active_navigation_sync_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            o = self.new_terminal(tmp)
            o.attach_host('3 0 0 0 0 0')
            o.navigator_command('open cubic')
            o.virtual_command('hold')
            self.assertFalse(o.navigator_engine.auto_enabled)
            o.observe_event({'type':'command','source':'base','value':'help',
                 'coordinate_after':'4 0 0 0 0 0','universe_after':0})
            self.assertEqual(o.virtual_counter.coordinate, '3 0 0 0 0 0')
            o.navigator_command('resume')
            o.observe_event({'type':'command','source':'base','value':'hello',
                 'coordinate_after':'5 0 0 0 0 0','universe_after':0})
            self.assertEqual(o.virtual_counter.coordinate, '4 0 0 0 0 0')
            o.virtual_command('sync')
            self.assertEqual(o.virtual_counter.coordinate, '5 0 0 0 0 0')
            self.assertFalse(o.navigator_engine.active)
            self.assertEqual(o.virtual_counter.mode, 'follow')

    def test_standalone_tick_independent_of_virtual_after_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            o = self.new_terminal(tmp)
            o.counter.sync('3 0 0 0 0 0')
            o.virtual_counter.observe_host('3 0 0 0 0 0')
            o.process_command('navigator open cubic')
            host_at_open = o.counter.get_counters()
            self.assertEqual(o.virtual_counter.coordinate, host_at_open)
            o.process_command('help')
            o.process_command('status')
            self.assertEqual(o.virtual_counter.coordinate, '12 0 0 0 0 0')
            self.assertEqual(o.counter.get_counters(), '6 0 0 0 0 0')


if __name__ == '__main__':
    unittest.main()
