#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import tempfile

from unittest import TestCase, skipIf, skipUnless, main
from unittest.mock import patch, Mock, mock_open
from io import StringIO


os.environ['SKIP_PYMP'] = "1"


import pythonrc

EDIT_CMD_TEST_LINES = """

x = 42
class Foo(object):


    def first(self):
        pass


    def second(self):

        pass


if x == 43:
    raise Exception()
elif x == 42:
    x += 1
else:
    raise Exception()

f = Foo()

1 + '2'
z = 123
"""


class TestImprovedConsole(TestCase):

    def setUp(self):
        _, pythonrc.config.HISTFILE = tempfile.mkstemp()
        self.pymp = pythonrc.ImprovedConsole()
        pythonrc.config.EDITOR = 'vi'
        pythonrc.config.EDIT_CMD = r'\e'
        pythonrc.config.LIST_CMD = r'\l'
        # py27 compatibility
        if not hasattr(self, 'assertRegex'):
            self.assertRegex = self.assertRegexpMatches

    def test_init(self):
        self.assertEqual(self.pymp.session_history, [])
        self.assertEqual(self.pymp.buffer, [])
        self.assertIn('red', dir(pythonrc))

    def test_init_color_functions(self):
        self.assertEqual(pythonrc.red('spam'), '\033[1;31mspam\033[0m')
        self.assertEqual(pythonrc.green('spam', False), '\033[32mspam\033[0m')
        self.assertEqual(pythonrc.yellow('spam', False, True),
                         '\001\033[33m\002spam\001\033[0m\002')

    @skipIf(sys.version_info[:2] == (3, 5),
            "mock.assert_called_once doesn't exist in 3.5")
    @patch('pythonrc.readline')
    def test_init_readline(self, mock_readline):
        pythonrc.ImprovedConsole()
        for method in [mock_readline.set_history_length,
                       mock_readline.parse_and_bind,
                       mock_readline.set_completer,
                       mock_readline.set_pre_input_hook,
                       mock_readline.read_init_file]:
            method.assert_called_once()

    @patch('pythonrc.readline')
    def test_libedit_readline(self, mock_readline):
        mock_readline.__doc__ = 'libedit'
        pythonrc.ImprovedConsole()
        mock_readline.parse_and_bind.assert_called_once_with('bind ^I rl_complete')

    def test_init_prompt(self):
        self.assertRegex(
            sys.ps1, ('\001\033' r'\[1;3[23]m\002>>> ' '\001\033' r'\[0m\002')
        )
        self.assertEqual(sys.ps2, '\001\033[1;31m\002... \001\033[0m\002')

        with patch.dict(os.environ,
                        {'SSH_CONNECTION': '1.1.1.1 10240 127.0.0.1 22'}):
            self.pymp.init_prompt()
            self.assertIn('[127.0.0.1]>>> ', sys.ps1)
            self.assertIn('[127.0.0.1]... ', sys.ps2)

    def test_init_pprint(self):
        self.assertEqual(sys.displayhook.__name__, 'pprint_callback')
        with patch('sys.stdout', new_callable=StringIO):
            sys.displayhook(42)
            sys.displayhook({'spam': 42})
            self.assertEqual(
                sys.stdout.getvalue(),
                ("%s\n" "{%s42}\n") % (pythonrc.blue('42'),
                                       pythonrc.purple("'spam': "))
            )

    @skipUnless(sys.version_info.major >= 3 and sys.version_info.minor > 3,
                'compact option does not exist for pprint in python < 3.3')
    def test_pprint_compact(self):
        with patch('sys.stdout', new_callable=StringIO):

            # - test compact pprint-ing with 80x25 terminal
            with patch.object(pythonrc.subprocess, 'check_output',
                              return_value='25 80'):
                sys.displayhook(list(range(22)))
                self.assertIn('20, 21]', sys.stdout.getvalue())
                sys.displayhook(list(range(23)))
                self.assertIn('21,\n 22]', sys.stdout.getvalue())

            # - test compact pprint-ing with resized 100x25 terminal
            with patch.object(pythonrc.subprocess, 'check_output',
                              return_value=('25 100')):
                sys.displayhook(list(range(23)))
                self.assertIn('21, 22]', sys.stdout.getvalue())

    def test_completer(self):
        completer = self.pymp.completer.complete
        rl = pythonrc.readline

        # - no leading characters
        with patch.object(rl, 'get_line_buffer', return_value='\t'):
            self.assertEqual(completer('\t', 0), '    ')
            self.assertEqual(completer('', 1), None)

        # - keyword completion
        with patch.object(rl, 'get_line_buffer', return_value='cla\t'):
            self.assertEqual(completer('cla', 0), 'class ')

        # - import statement completion
        with patch.object(rl, 'get_line_buffer', return_value='import th'):
            self.assertIn(completer('th', 0), ('this', 'threading'))
            self.assertIn(completer('th', 1), ('this', 'threading'))

        # - from ... completion (module name)
        with patch.object(rl, 'get_line_buffer', return_value='from th'):
            self.assertIn(completer('th', 0), ('this', 'threading'))
            self.assertIn(completer('th', 1), ('this', 'threading'))

        # - from ... import completion (import keyword)
        with patch.object(rl, 'get_line_buffer', return_value='from os '):
            self.assertEqual(completer('', 0), 'import ')

        # - from ... import completion (submodule name)
        with patch.object(rl, 'get_line_buffer', return_value='from xlm.'):
            self.assertEqual(completer('xml.', 0), 'xml.dom')
            self.assertTrue(completer('xml.', 1).startswith('xml.dom.'))

        # - from ... import completion (submodule import - 0)
        with patch.object(rl, 'get_line_buffer', return_value='from xml import '):
            self.assertEqual(completer('', 0), 'dom')
            self.assertTrue(completer('', 1).startswith('dom.'))

        # - from ... import completion (submodule import - 1)
        with patch.object(rl, 'get_line_buffer', return_value='from xml.dom import x'):
            self.assertEqual(completer('x', 0), 'xmlbuilder')

        # - from ... import completion (module content)
        with patch.object(rl, 'get_line_buffer', return_value='from tempfile import '):
            self.assertEqual(completer('', 0), 'NamedTemporaryFile')

        # - pathname completion
        with patch.object(rl, 'get_line_buffer', return_value='./t'):
            self.assertEqual(completer('./te', 0), './test_pythonrc.py')

        mock_input_line = ['/', '/', '/', '/h', '/home/t', '/home/t', '/home/test/f']
        mock_globs = [['/bin', '/home', '/sbin'],
                      ['/home'],
                      ['/home/test', '/home/steve'],
                      ['/home/test'],
                      ['/home/test/foo', '/home/test/bar/', '/home/test/baz']]
        mock_isdir = lambda path: not (path == '/home/test/foo')

        with patch.object(rl, 'get_line_buffer', side_effect=mock_input_line), \
             patch.object(pythonrc.glob, 'iglob', side_effect=mock_globs), \
             patch.object(pythonrc.os.path, 'isdir', side_effect=mock_isdir):
            self.assertEqual(completer('/', 0), '/bin/')
            self.assertEqual(completer('/', 1), '/home/')
            self.assertEqual(completer('/', 2), '/sbin/')
            self.assertEqual(completer('/h', 0), '/home/')
            self.assertEqual(completer('/home/', 0), '/home/test/')
            self.assertEqual(completer('/home/t', 0), '/home/test/')
            self.assertEqual(completer('/home/test/f', 0), '/home/test/foo')

        # - pathname completion, with expand user
        with patch.object(rl, 'get_line_buffer', return_value='~/'):
            completion = completer('~/', 0)
            self.assertTrue(completion.startswith(os.path.expanduser('~')))

    def test_push(self):
        self.assertEqual(self.pymp._indent, '')
        self.pymp.push('class Foo:')
        self.assertEqual(self.pymp._indent, '    ')
        self.pymp.push('    def dummy():')
        self.assertEqual(self.pymp._indent, '        ')
        self.pymp.push('        pass')
        self.assertEqual(self.pymp._indent, '        ')
        self.pymp.push('')
        self.assertEqual(self.pymp._indent, '')

    @patch.object(pythonrc.InteractiveConsole, 'raw_input',
                  return_value=r'\e code')
    def test_raw_input_edit_cmd(self, ignored):
        mocked_cmd = Mock()
        with patch.dict(self.pymp.commands, {r'\e': mocked_cmd}):
            self.pymp.raw_input('>>> ')
            mocked_cmd.assert_called_once_with('code')

    @patch.object(pythonrc.InteractiveConsole, 'raw_input',
                  return_value=r'\l shutil')
    def test_raw_input_list_cmd0(self, ignored):
        mocked_cmd = Mock()
        with patch.dict(self.pymp.commands, {r'\l': mocked_cmd}):
            ret = self.pymp.raw_input('>>> ')
            mocked_cmd.assert_called_once_with('shutil')

    @patch.object(pythonrc.InteractiveConsole, 'raw_input',
                  return_value=r'\l global')
    def test_raw_input_list_cmd1(self, ignored):
        mocked_cmd = Mock()
        with patch.dict(self.pymp.commands, {r'\l': mocked_cmd}):
            self.pymp.raw_input('>>> ')
            mocked_cmd.assert_called_once_with('global')

    def test_increase_indent(self):
        for count, char in enumerate(['if True:', '\t[', '{', '('], 1):
            self.pymp.push(char)
            self.assertEqual(self.pymp._indent, pythonrc.config.ONE_INDENT*count)

    def test_donot_crash_on_empty_continuation(self):
        self.pymp.push('if True:')
        self.assertEqual(self.pymp._indent, pythonrc.config.ONE_INDENT)
        self.pymp.push('')
        self.assertEqual(self.pymp._indent, pythonrc.config.ONE_INDENT)

    @patch.object(pythonrc.ImprovedConsole, 'lookup',
                  return_value=pythonrc.ImprovedConsole)
    def test_edit_cmd0(self, *ignored):
        """Test edit object"""
        with patch.object(pythonrc.os, 'system') as mocked_system:
            self.pymp.process_edit_cmd('pythonrc.ImprovedConsole')
            self.assertRegex(mocked_system.call_args[0][0],
                                     r'vi \+\d+ .*pythonrc.py')

    @patch.object(pythonrc.ImprovedConsole, 'lookup', return_value=None)
    def test_edit_cmd1(self, *ignored):
        """Test edit file"""
        with patch.object(pythonrc.os, 'system') as mocked_system:
            self.pymp.process_edit_cmd('/path/to/file')
            self.assertRegex(mocked_system.call_args[0][0],
                                     r'vi  /path/to/file')

    def test_edit_cmd2(self, *ignored):
        """Test edit session"""
        tempfl = StringIO()
        tempfl.name = "/tmp/dummy"

        with patch.object(pythonrc.os, 'system', return_value=0) as mocked_system, \
             patch.object(pythonrc.os, 'unlink') as mocked_unlink, \
             patch.object(self.pymp, '_exec_from_file') as mocked_exec, \
             patch.object(pythonrc, 'open', return_value=tempfl), \
             patch.object(pythonrc.ImprovedConsole, '_mktemp_buffer',
                          return_value=tempfl.name):
            self.pymp.session_history = 'x = 42'
            self.pymp.process_edit_cmd('')
            mocked_system.assert_called_once_with(f'vi  {tempfl.name}')
            mocked_unlink.assert_called_once_with(tempfl.name)
            mocked_exec.assert_called_once_with(
                tempfl, print_comments=pythonrc.config.POST_EDIT_PRINT_COMMENTS
            )

    def test_edit_cmd3(self, *ignored):
        """Test edit previous session"""
        tempfl = StringIO()
        tempfl.name = "/tmp/dummy"
        with patch.object(pythonrc.os, 'system', return_value=0) as mocked_system, \
             patch.object(pythonrc.os, 'unlink') as mocked_unlink, \
             patch.object(self.pymp, '_exec_from_file') as mocked_exec, \
             patch.object(pythonrc, 'open', return_value=tempfl), \
             patch.object(pythonrc.ImprovedConsole, '_mktemp_buffer',
                          return_value=tempfl.name):
            self.pymp.session_history = []
            self.pymp.process_edit_cmd('')
            mocked_system.assert_called_once_with(f'vi  {tempfl.name}')
            mocked_unlink.assert_called_once_with(tempfl.name)
            mocked_exec.assert_called_once_with(tempfl, print_comments=False)

    def test_sh_exec0(self):
        """Test sh exec with command and argument"""
        self.pymp.locals['path'] = "/dummy/location"
        with patch('pythonrc.subprocess.run') as mocked_run, \
                patch.object(sys, 'stdout', new_callable=StringIO):
            self.pymp.process_sh_cmd('ls -l {path}')
            mocked_run.assert_called_once_with(
                ['ls', '-l', '/dummy/location'],
                capture_output=True,
                env=os.environ,
                text=True
            )

    @patch.object(pythonrc.os, 'chdir')
    def test_sh_exec1(self, mocked_chdir):
        """Test sh exec with cd, user home and shell variable"""
        self.pymp.locals['path'] = "~/${RUNTIME}/location"
        with patch.dict(pythonrc.os.environ, {'RUNTIME': 'dummy',
                                              'HOME': '/home/me/'}):
            self.pymp.process_sh_cmd('cd {path}')
            mocked_chdir.assert_called_once_with('/home/me/dummy/location')

    def test_exec_from_file(self):
        """Test exec from file with multiple newlines in code blocks"""
        pymp = pythonrc.ImprovedConsole()
        tempfl = StringIO(EDIT_CMD_TEST_LINES)
        with patch.object(sys, 'stderr', new_callable=StringIO):
            pymp._exec_from_file(tempfl)

        self.assertIn('Foo', pymp.locals)
        self.assertIn('first', pymp.locals['Foo'].__dict__)
        self.assertIn('second', pymp.locals['Foo'].__dict__)
        self.assertIn('x', pymp.locals)
        self.assertIn('f', pymp.locals)
        self.assertEqual(pymp.locals['x'], 43)
        self.assertNotIn('z', pymp.locals)

        with tempfile.NamedTemporaryFile(mode='w') as tempfl:
            pythonrc.readline.write_history_file(tempfl.name)
            expected = filter(None, EDIT_CMD_TEST_LINES.splitlines()[:-1])
            recieved = filter(None, map(str.rstrip, open(tempfl.name)))
            self.assertEqual(list(expected), list(recieved))

    def test_post_edit_print_comments0(self):
        """Test post edit print comments"""
        with patch.object(sys, 'stderr', new_callable=StringIO) as mock_stderr, \
                patch.object(pythonrc.os, 'system', return_value=0):
            self.pymp.session_history = ['x = 42']
            self.pymp.process_edit_cmd('')
            self.assertEqual(
                mock_stderr.getvalue(),

                pythonrc.grey('... # x = 42', bold=False)
            )

    def test_post_edit_print_comments1(self):
        """Test post edit do not print comments"""
        with patch.object(sys, 'stderr', new_callable=StringIO) as mock_stderr, \
                patch.object(pythonrc.os, 'system', return_value=0):
            tempfl = StringIO('# x = 42\ny = "foo"')
            self.pymp._exec_from_file(tempfl, print_comments=False)
            self.assertEqual(mock_stderr.getvalue(), pythonrc.cyan('... y = "foo"'))

    def test_lookup(self):
        self.pymp.locals['os'] = os
        self.assertIs(self.pymp.lookup('os'), os)
        self.assertIs(self.pymp.lookup('os.path'), os.path)
        self.assertIs(self.pymp.lookup('os.path.basename'), os.path.basename)

        self.assertIs(self.pymp.lookup('subprocess'), None)
        self.assertIs(self.pymp.lookup('subprocess.Popen'), None)

    def test_process_help_cmd(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_stderr:
            self.pymp.process_help_cmd('abs')
            output = sys.stdout.getvalue()
            self.assertTrue(output.startswith("Help on built-in function abs"))

        with patch.object(sys, 'stdout', new_callable=StringIO) as mock_stderr:
            self.pymp.process_help_cmd('')
            self.assertEqual(
                pythonrc.cyan(self.pymp.__doc__.format(**pythonrc.config.__dict__)),
                mock_stderr.getvalue().strip()
            )


if __name__ == '__main__':
    main()
