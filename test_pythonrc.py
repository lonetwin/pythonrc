#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import tempfile

from unittest import TestCase, skipIf, skipUnless

try:
    from unittest.mock import patch, Mock
except ImportError:
    from mock import patch, Mock

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO


os.environ['SKIP_PYMP'] = "1"


import pythonrc

EDIT_CMD_TEST_LINES="""

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

"""


class TestImprovedConsole(TestCase):

    def setUp(self):
        _, pythonrc.config['HISTFILE'] = tempfile.mkstemp()
        self.pymp = pythonrc.ImprovedConsole()
        pythonrc.config['EDITOR'] = 'vi'
        pythonrc.config['EDIT_CMD'] = '\e'
        pythonrc.config['LIST_CMD'] = '\l'

    def test_init(self):
        self.assertEqual(self.pymp.session_history, [])
        self.assertEqual(self.pymp.buffer, [])
        self.assertIn('red', dir(pythonrc))

    def test_init_color_functions(self):
        self.assertEquals(pythonrc.red('spam'), '\033[1;31mspam\033[0m')
        self.assertEquals(pythonrc.green('spam', False), '\033[32mspam\033[0m')
        self.assertEquals(pythonrc.yellow('spam', False, True),
                          '\001\033[33m\002spam\001\033[0m\002')

    @skipIf(sys.version_info[:2] == (3, 5),
            "mock.assert_called_once doesn't exist in 3.5")
    @patch('pythonrc.readline')
    def test_init_readline(self, mock_readline):
        pymp = pythonrc.ImprovedConsole()
        for method in [mock_readline.set_history_length,
                       mock_readline.parse_and_bind,
                       mock_readline.set_completer,
                       mock_readline.set_pre_input_hook,
                       mock_readline.read_init_file
                      ]:
            method.assert_called_once()

    @patch('pythonrc.readline')
    def test_libedit_readline(self, mock_readline):
        mock_readline.__doc__ = 'libedit'
        pymp = pythonrc.ImprovedConsole()
        mock_readline.parse_and_bind.assert_called_once_with(
            'bind ^I rl_complete')

    def test_init_prompt(self):
        self.assertRegexpMatches(
            sys.ps1, '\001\033\[1;3[23]m\002>>> \001\033\[0m\002'
        )
        self.assertEqual(sys.ps2, '\001\033[1;31m\002... \001\033[0m\002')

        with patch.dict(os.environ,
                        {'SSH_CONNECTION': '1.1.1.1 10240 127.0.0.1 22'}):
            self.pymp.init_prompt()
            self.assertIn('[127.0.0.1]>>> ', sys.ps1)
            self.assertIn('[127.0.0.1]... ', sys.ps2)

    def test_init_pprint(self):
        self.assertEqual(sys.displayhook.__name__, 'pprint_callback')
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            sys.displayhook(42)
            sys.displayhook({'spam': 42})
            self.assertEquals(
                sys.stdout.getvalue(),
                ("%s\n" "{%s42}\n") % (pythonrc.blue('42'),
                                       pythonrc.purple("'spam': "))
            )

    @skipUnless(sys.version_info.major >= 3 and sys.version_info.minor > 3,
                'compact option does not exist for pprint in python < 3.3')
    def test_pprint_compact(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:

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
        completer = self.pymp.improved_rlcompleter()
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

        # - from ... import completion (submodule import)
        with patch.object(rl, 'get_line_buffer', return_value='from xml import '):
            self.assertEqual(completer('', 0), 'dom')
            self.assertTrue(completer('', 1).startswith('dom.'))

        # - from ... import completion (module content)
        with patch.object(rl, 'get_line_buffer', return_value='from tempfile import '):
            self.assertEqual(completer('', 0), 'NamedTemporaryFile')

        # - pathname completion
        with patch.object(rl, 'get_line_buffer', return_value='./p'):
            self.assertEqual(completer('./py', 0), './pythonrc.py')

        mock_input_line = ['/', '/', '/', '/h', '/home/t', '/home/t', '/home/test/f']
        mock_globs = [['/bin', '/home', '/sbin'],
                      ['/home'],
                      ['/home/test', '/home/steve'],
                      ['/home/test'],
                      ['/home/test/foo', '/home/test/bar/', '/home/test/baz']]
        mock_isdir = lambda path: not (path == '/home/test/foo')

        with patch.object(rl, 'get_line_buffer', side_effect=mock_input_line), \
             patch.object(pythonrc.glob, 'glob', side_effect=mock_globs), \
             patch.object(pythonrc.os.path, 'isdir', side_effect=mock_isdir):
            self.assertEqual(completer('/', 0), '/bin/')
            self.assertEqual(completer('/', 1), '/home/')
            self.assertEqual(completer('/', 2), '/sbin/')
            self.assertEqual(completer('/h', 0), '/home/')
            self.assertEqual(completer('/home/', 0), '/home/test/')
            self.assertEqual(completer('/home/t', 0), '/home/test/')
            self.assertEqual(completer('/home/test/f', 0), '/home/test/foo')

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
                  return_value='\e code')
    def test_raw_input_edit_cmd(self, ignored):
        mocked_cmd = Mock()
        with patch.dict(self.pymp.commands, {'\e': mocked_cmd}):
            self.pymp.raw_input('>>> ')
            mocked_cmd.assert_called_once_with('code')

    @patch.object(pythonrc.InteractiveConsole, 'raw_input',
                  return_value='\l shutil')
    def test_raw_input_list_cmd0(self, ignored):
        mocked_cmd = Mock()
        with patch.dict(self.pymp.commands, {'\l': mocked_cmd}):
            ret = self.pymp.raw_input('>>> ')
            mocked_cmd.assert_called_once_with('shutil')

    @patch.object(pythonrc.InteractiveConsole, 'raw_input',
                  return_value='\l global')
    def test_raw_input_list_cmd1(self, ignored):
        mocked_cmd = Mock()
        with patch.dict(self.pymp.commands, {'\l': mocked_cmd}):
            self.pymp.raw_input('>>> ')
            mocked_cmd.assert_called_once_with('global')

    def test_increase_indent(self):
        for count, char in enumerate(['if True:', '\t[', '{', '('], 1):
            self.pymp.push(char)
            self.assertEqual(self.pymp._indent, self.pymp.tab*count)

    def test_donot_crash_on_empty_continuation(self):
        self.pymp.push('if True:')
        self.assertEqual(self.pymp._indent, self.pymp.tab)
        self.pymp.push('')
        self.assertEqual(self.pymp._indent, self.pymp.tab)

    @patch.object(pythonrc.ImprovedConsole, 'lookup',
                  return_value=pythonrc.ImprovedConsole)
    def test_edit_cmd0(self, *ignored):
        """Test edit object"""
        with patch.object(pythonrc.os, 'system') as mocked_system:
            self.pymp.process_edit_cmd('pythonrc.ImprovedConsole')
            self.assertRegexpMatches(mocked_system.call_args[0][0],
                                     r'vi \+\d+ .*pythonrc.py')

    @patch.object(pythonrc.ImprovedConsole, 'lookup', return_value=None)
    def test_edit_cmd1(self, *ignored):
        """Test edit file"""
        with patch.object(pythonrc.os, 'system') as mocked_system:
            self.pymp.process_edit_cmd('/path/to/file')
            self.assertRegexpMatches(mocked_system.call_args[0][0],
                                     r'vi  /path/to/file')

    @patch.object(pythonrc.ImprovedConsole, '_mktemp_buffer',
                  return_value='/tmp/dummy')
    def test_edit_cmd2(self, *ignored):
        """Test edit session"""
        with patch.object(pythonrc.os, 'system') as mocked_system, \
             patch.object(pythonrc.os, 'unlink') as mocked_unlink, \
             patch.object(self.pymp, '_exec_from_file') as mocked_exec:
            self.pymp.process_edit_cmd('')
            mocked_system.assert_called_once_with('vi  /tmp/dummy')
            mocked_exec.assert_called_once_with('/tmp/dummy')
            mocked_unlink.assert_called_once_with('/tmp/dummy')

    def test_sh_exec0(self):
        """Test sh exec with command and argument"""
        self.pymp.locals['path'] = "/dummy/location"
        with patch('pythonrc.subprocess.Popen') as mocked_popen:
            mocked_popen.return_value.communicate = Mock(return_value=('foo', 'bar'))
            mocked_popen.return_value.returncode = 0
            self.pymp.process_sh_cmd('ls -l {path}')
            mocked_popen.assert_called_once_with(
                ['ls', '-l', '/dummy/location'],
                stdout=pythonrc.subprocess.PIPE,
                stderr=pythonrc.subprocess.PIPE
            )
            mocked_popen.return_value.communicate.assert_called_once_with()

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
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tempfl:
            tempfl.write(EDIT_CMD_TEST_LINES)
            tempfl.close()
            pymp._exec_from_file(tempfl.name)
            os.unlink(tempfl.name)

            self.assertIn('Foo', pymp.locals)
            self.assertIn('first', pymp.locals['Foo'].__dict__)
            self.assertIn('second', pymp.locals['Foo'].__dict__)
            self.assertIn('x', pymp.locals)
            self.assertIn('f', pymp.locals)
            self.assertEqual(pymp.locals['x'], 43)
