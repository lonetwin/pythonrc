#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import tempfile

from unittest import TestCase, skipIf

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO


os.environ['SKIP_PYMP'] = "1"


import pythonrc


class TestImprovedConsole(TestCase):

    def setUp(self):
        _, pythonrc.config['HISTFILE'] = tempfile.mkstemp()
        self.pymp = pythonrc.ImprovedConsole()

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
