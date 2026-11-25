"""Small UI and automatic reverse-tick regressions for v8."""
import io
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout

from oais.Terminal.Oais_Terminal import OaisTerminal
from oais.Commands.Navigator.Navigator import Navigator
from oais.utils.counter import Counter
from oais.utils.data_manager import DataManager

class SimpleNavigatorTests(unittest.TestCase):
    def terminal(self, folder):
        term = OaisTerminal(counter=Counter(load_state=False,save_path=Path(folder)/'coord.json'),
                            data_manager=DataManager(Path(folder)/'Data'),terminal_id='base')
        term.attach_host('3 0 0 0 0 0')
        return term

    def host(self, t, cmd):
        before=t.host_counter.get_counters(); universe=t.host_counter.universes
        if cmd=='backwards':t.host_counter.decrement()
        else:t.host_counter.increment()
        t.observe_event({'type':'command','source':'base','value':cmd,'success':True,
                         'coordinate_before':before,'coordinate_after':t.host_counter.get_counters(),
                         'universe_before':universe,'universe_after':t.host_counter.universes})

    def test_menu_only_advertises_function_selection(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.terminal(d); n=Navigator(t)
            lines=[]; choices=iter(['help','functions','function k**3','exit'])
            n.run(input_func=lambda prompt:next(choices),print_func=lines.append)
            text='\n'.join(lines)
            self.assertNotIn('Navigator [',text.split('Navigator: choose')[0])
            self.assertIn('function <f(k)>',text)
            self.assertNotIn('checkpoint / restore',text)
            self.assertEqual(t.navigator_engine.compact_state()['functions'][0]['f'],'k**3')

    def test_base_backwards_decreases_k_and_forwards_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.terminal(d); t.process_command('navigator function k**3')
            for _ in range(3):self.host(t,'help')
            self.assertEqual(t.virtual_counter.coordinate,'30 0 0 0 0 0')
            self.host(t,'backwards'); self.assertEqual(t.virtual_counter.coordinate,'11 0 0 0 0 0')
            self.assertEqual(t.navigator_engine.layers[-1]['k'],2)
            self.host(t,'forwards'); self.assertEqual(t.virtual_counter.coordinate,'30 0 0 0 0 0')
            self.assertEqual(t.navigator_engine.layers[-1]['k'],3)
            for _ in range(3):self.host(t,'backwards')
            self.assertEqual(t.virtual_counter.coordinate,'3 0 0 0 0 0')
            self.assertTrue(t.navigator_engine.active)  # k=0 is reversible
            self.assertEqual(t.navigator_engine.layers[-1]['k'], 0)
            self.host(t,'backwards')  # root remains bounded at zero
            self.assertEqual(t.virtual_counter.coordinate, '3 0 0 0 0 0')
            self.host(t,'help')
            self.assertEqual(t.virtual_counter.coordinate, '4 0 0 0 0 0')

    def test_backwards_recorded_note_can_save(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.terminal(d); t.process_command('navigator function k**3')
            self.host(t,'help');self.host(t,'help')
            t.process_command('sticky start')
            self.host(t,'backwards')
            self.host(t,'backwards')
            t.process_command('sticky stop')
            note=t.sticky_note.save_reference('reverse')
            self.assertEqual(note['end'],'3 0 0 0 0 0')
            self.assertIn(-1,[f['direction'] for f in note['functions']])

if __name__ == '__main__':unittest.main()
