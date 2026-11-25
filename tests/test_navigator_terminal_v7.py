"""v7: interactive function terminal, independent counters, k storage."""
from pathlib import Path
import os
import sys
import tempfile
import unittest

from oais.Commands.Navigator.Navigator import Navigator
from oais.Commands.Navigator.NavigatorEngine import function_definition, evaluate_offset
from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager

try:
    import pexpect
except ImportError:
    pexpect = None

ROOT = Path(__file__).resolve().parents[1]


class NavigatorTerminalV7Tests(unittest.TestCase):
    def make_terminal(self, folder, *, connected=False):
        t = OaisTerminal(
            counter=Counter(load_state=False, save_path=Path(folder)/'oais.json'),
            data_manager=DataManager(base_dir=Path(folder)/'Data'),
            terminal_id='base' if connected else 'oais_standalone')
        if connected:
            t.attach_host('3 0 0 0 0 0')
        return t

    @staticmethod
    def base_tick(t, command='help'):
        before=t.host_counter.get_counters()
        before_u=t.host_counter.universes
        t.host_counter.increment()
        return t.observe_event({
            'type':'command','source':'base','value':command, 'success':True,
            'coordinate_before':before,'coordinate_after':t.host_counter.get_counters(),
            'universe_before':before_u,'universe_after':t.host_counter.universes})

    def test_k_math_and_invalid_expression_never_changes_stack(self):
        self.assertEqual(function_definition('2*k**2 + 5')['f'], '2*k**2 + 5')
        # Older i expressions are read as k, but k is the canonical output.
        self.assertEqual(function_definition('i**3')['f'], 'k**3')
        self.assertEqual(evaluate_offset(function_definition('2*k**2+5'),3),18)
        with tempfile.TemporaryDirectory() as d:
            t=self.make_terminal(d, connected=True)
            n=Navigator(t)
            for expr in ('__import__("os")', 'k/2', 'sin(k)', 'k**100000', 'x**3'):
                with self.subTest(expr=expr), self.assertRaises(ValueError):
                    n.process_command('function '+expr)
            self.assertEqual(t.navigator_engine.compact_state()['functions'], [])
            self.assertEqual(t.virtual_counter.coordinate, '3 0 0 0 0 0')

    def test_interactive_menu_and_function_stack(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make_terminal(d, connected=True)
            commands=iter(['functions','function k**3','stack','function k**2', 'away','back'])
            printed=[]
            message=Navigator(t).run(input_func=lambda prompt: next(commands),
                                     print_func=printed.append)
            self.assertIn('Returning to OAIS',message)
            self.assertIn('PRESET FUNCTIONS', '\n'.join(printed))
            self.assertIn('"k": 0','\n'.join(printed))
            self.assertEqual(t.navigator_engine.compact_state()['functions'], [
                {'f':'k**3','k':0,'direction':1},
                {'f':'k**2','k':1,'direction':1}])
            self.assertEqual(t.virtual_counter.coordinate, '4 0 0 0 0 0')
            self.assertEqual(t.host_counter.get_counters(),'3 0 0 0 0 0')
            self.assertEqual(t.standalone_counter.get_counters(),'6 0 0 0 0 0')

    def test_base_ticks_virtual_not_oais_and_then_follows_base(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make_terminal(d, connected=True)
            self.assertIn('Opened pole', t.process_command('navigator function k**3').output)
            self.assertEqual(t.virtual_counter.coordinate,'3 0 0 0 0 0')
            self.assertEqual(t.standalone_counter.get_counters(),'1 0 0 0 0 0')
            self.base_tick(t)
            self.base_tick(t)
            self.assertEqual(t.host_counter.get_counters(),'5 0 0 0 0 0')
            self.assertEqual(t.virtual_counter.coordinate,'11 0 0 0 0 0')
            self.assertEqual(t.navigator_engine.compact_state()['functions'][0]['k'],2)
            self.assertEqual(t.standalone_counter.get_counters(),'1 0 0 0 0 0')
            t.process_command('navigator turn')
            self.assertEqual(t.virtual_counter.coordinate,'4 0 0 0 0 0')
            self.base_tick(t)
            self.assertEqual(t.virtual_counter.coordinate,'11 0 0 0 0 0')
            self.assertTrue(t.navigator_engine.active)
            self.base_tick(t)
            self.assertEqual(t.virtual_counter.coordinate,'30 0 0 0 0 0')
            self.assertEqual(t.virtual_counter.mode,'free')
            self.assertEqual(t.standalone_counter.get_counters(),'2 0 0 0 0 0')
            self.assertIn('source=BASE',t.coordinate_display())
            self.assertIn('OAIS Counter:    2', t.coordinate_display())

    def test_standalone_uses_oais_counter_as_virtual_source(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make_terminal(d)
            t.process_command('help')
            self.assertEqual(t.virtual_counter.coordinate,'1 0 0 0 0 0')
            t.process_command('navigator function k**2')
            self.assertEqual(t.virtual_counter.coordinate,'2 0 0 0 0 0')
            t.process_command('help')
            t.process_command('help')
            self.assertEqual(t.standalone_counter.get_counters(),'4 0 0 0 0 0')
            self.assertEqual(t.virtual_counter.coordinate,'6 0 0 0 0 0')
            t.process_command('navigator turn')
            self.assertEqual(t.virtual_counter.coordinate,'3 0 0 0 0 0')
            t.process_command('help')
            self.assertEqual(t.virtual_counter.coordinate,'6 0 0 0 0 0')
            t.process_command('help')
            self.assertEqual(t.virtual_counter.coordinate,'11 0 0 0 0 0')
            self.assertIn('source=OAIS',t.coordinate_display())

    def test_sticky_records_k_function_from_interactive_menu(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make_terminal(d,connected=True)
            t.process_command('sticky start')
            commands=iter(['function k**3','exit'])
            Navigator(t).run(input_func=lambda _:next(commands),print_func=lambda _:None)
            self.base_tick(t)
            self.base_tick(t)
            t.process_command('sticky stop')
            note=t.sticky_note.save_reference('menu function note')
            self.assertEqual([slot['f'] for slot in note['functions']],['k','k**3'])
            self.assertEqual(note['plan'][1]['op'],'open')
            self.assertEqual(note['start'],'3 0 0 0 0 0')
            self.assertEqual(note['end'],'11 0 0 0 0 0')

    def test_restart_function_uses_current_base_even_after_old_pole(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make_terminal(d,connected=True)
            t.process_command('navigator open cubic')
            self.base_tick(t)
            t.process_command('navigator turn')  # completed at former pole=3
            self.assertEqual(t.virtual_counter.mode,'free')
            self.assertFalse(t.navigator_engine.active)
            self.assertIn('Opened pole',t.process_command('navigator function k**2').output)
            self.assertEqual(t.navigator_engine.layers[-1]['pole_real'], '4 0 0 0 0 0')
            self.assertEqual(t.navigator_engine.compact_state()['functions'][0]['k'],0)


@unittest.skipUnless(pexpect and os.name=='posix','Requires Linux/WSL and pexpect')
class NavigatorMenuPTYTests(unittest.TestCase):
    def test_menu_direct_from_base_keeps_counters_independent(self):
        with tempfile.TemporaryDirectory() as d:
            proc=pexpect.spawn(sys.executable,
                [str(ROOT/'main.py'), '--start','3 0 0 0 0 0','--data-dir',d],
                cwd=str(ROOT), encoding='utf-8', timeout=18)
            try:
                proc.expect('BASE > ')
                proc.sendline('oais navigator')
                proc.expect('Navigator> ')
                proc.sendline('function k**3')
                proc.expect('Navigator> ')
                self.assertIn('Opened pole',proc.before)
                proc.sendline('exit')
                proc.expect('BASE > ')
                proc.sendline('help')
                proc.expect('BASE > ')
                proc.sendline('help')
                proc.expect('BASE > ')
                proc.sendline('oais')
                proc.expect('Virtual Counter: 11 0 0 0 0 0')
                proc.expect('OAIS > ')
                seen=proc.before
                self.assertIn('source=BASE',seen)
                self.assertIn('f(k)=k**3 | k=2',seen)
                proc.sendline('return')
                proc.expect('BASE > ')
                proc.sendline('exit')
                proc.expect(pexpect.EOF)
            finally:
                proc.close(force=True)
