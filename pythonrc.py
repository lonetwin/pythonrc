#!/usr/bin/env python
# -*- coding: utf-8 -*-
# The MIT License (MIT)
#
# Copyright (c) 2015 Steven Fernandez
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""lonetwin's pimped-up pythonrc

This file will be executed when the Python interactive shell is started, if
$PYTHONSTARTUP is in your environment and points to this file.

You could also simply make this file executable and call it directly.

This file create an InteractiveConsole instance, which provides:
  * colored prompts and pretty printing
  * intelligent tab completion:¹
    - with preceding text
        + names in the current namespace
        + for objects, their attributes/methods
        + for strings with a '/', pathname completion
    - without preceding text four spaces
  * shortcut to open your $EDITOR with the last executed command
    (the '\e' command)
  * temporary escape to $SHELL or ability to execute a shell command and
    capturing the output in to the '_' variable (the '!' command)
  * execution history
  * convenient printing of doc stings (the '?' command)

Some ideas borrowed from:
  * http://eseth.org/2008/pimping-pythonrc.html
    (which co-incidentally reused something I wrote back in 2005 !! Ain't
     sharing great ?)
  * http://igotgenes.blogspot.in/2009/01/tab-completion-and-history-in-python.html

If you have any other good ideas please feel free to leave a comment.

¹ Since python 3.4 the default interpreter also has tab completion enabled
however it does not do pathname completion
"""

try:
    import builtins
except ImportError:
    import __builtin__ as builtins
import atexit
import glob
import keyword
import os
import pprint
import re
import readline
import rlcompleter
import signal
import subprocess
import sys

from code import InteractiveConsole
from collections import namedtuple
from tempfile import mkstemp


HISTFILE = os.path.expanduser("~/.python_history")
HISTSIZE = 1000
EDITOR   = os.environ.get('EDITOR', 'vi')
SHELL    = os.environ.get('SHELL', '$SHELL')


def create_color_func(code):
    def color_func(text, bold=True, readline_workaround=False):
        code_str = '1;{}'.format(code) if bold else code
        # - reason for readline_workaround: http://bugs.python.org/issue20359
        if readline_workaround:
            return "\001\033[{}m\002{}\001\033[0m\002".format(code_str, text)
        else:
            return "\033[{}m{}\033[0m".format(code_str, text)
    return color_func

# add any colors you might need.
red    = create_color_func(31)
green  = create_color_func(32)
yellow = create_color_func(33)
blue   = create_color_func(34)
purple = create_color_func(35)
cyan   = create_color_func(36)


class ImprovedConsole(InteractiveConsole, object):

    EDIT_CMD = '\e'
    SH_EXEC  = '!'
    DOC_CMD  = '?'
    HELP_CMD = '\h'

    def __init__(self, tab='    ', *args, **kwargs):
        self.session_history = [] # This holds the last executed statements
        self.buffer = []          # This holds the statement to be executed
        self.tab = tab
        super(ImprovedConsole, self).__init__(*args, **kwargs)
        self._init_readline()
        self._init_prompt()
        self._init_pprint()

    def _init_readline(self):
        """Activates history and tab completion
        """
        # - init history
        if os.path.exists(HISTFILE):
            readline.read_history_file(HISTFILE)

        readline.set_history_length(HISTSIZE)
        atexit.register(lambda :readline.write_history_file(HISTFILE))

        # - turn on tab completion
        readline.parse_and_bind('tab: complete')

        # - other useful stuff
        readline.parse_and_bind('set skip-completed-text on')
        readline.set_completer(self._improved_rlcompleter())

    def _init_prompt(self):
        """Activates color on the prompt based on python version.

        Also adds the hosts IP if running on a remote host over a
        ssh connection.
        """
        prompt_color = green if sys.version_info.major == 2 else yellow
        sys.ps1 = prompt_color('>>> ', readline_workaround=True)
        sys.ps2 = red('... ', readline_workaround=True)
        # - if we are a remote connection, modify the ps1
        if os.environ.get('SSH_CONNECTION'):
            this_host = os.environ['SSH_CONNECTION'].split()[-2]
            sys.ps1 = prompt_color('[{}]>>> '.format(this_host), readline_workaround=True)
            sys.ps2 = red('[{}]... '.format(this_host), readline_workaround=True)

    def _init_pprint(self):
        """Activates pretty-printing of output values.
        """
        try:
            rows, cols = subprocess.check_output('stty size', shell=True).strip().split()
        except:
            cols = 80
        def pprint_callback(value):
            if value is not None:
                builtins._ = value
                formatted = pprint.pformat(value, width=cols)
                if issubclass(type(value), dict):
                    formatted = re.sub(r'([ {][^{:]+?: )+?', lambda m: purple(m.group()), formatted)
                    # keys = r'|'.join(repr(i) for i in value.keys())
                    # formatted = re.sub(keys, lambda match: red(match.group(0)), formatted)
                    print(formatted)
                else:
                   print(blue(formatted))
        sys.displayhook = pprint_callback

    def _improved_rlcompleter(self):
        """Enhances the default rlcompleter to also do pathname completion
        """
        rlcompleter_instance = rlcompleter.Completer(namespace=self.locals)
        # - remove / from the delimiters to help identify possibility
        # for path completion and set the completer function
        readline.set_completer_delims(readline.get_completer_delims().replace('/', ''))
        def complete_wrapper(text, state):
            if text == '':
                return None if state > 0 else self.tab
            match = rlcompleter_instance.complete(text, state)
            if match is None:
                if '/' in text:
                    try:
                        match = glob.glob(text+'*')[state]
                    except IndexError:
                        return None
            return match
        return complete_wrapper

    def raw_input(self, *args):
        """Read the input and delegate if necessary.
        """
        line = InteractiveConsole.raw_input(self, *args)
        if line == self.HELP_CMD:
            print(HELP)
            line = ''
        elif line == self.EDIT_CMD:
            line = self._process_edit_cmd()
        elif line.startswith(self.SH_EXEC):
            line = self._process_sh_cmd(line.strip(self.SH_EXEC))
        elif line.endswith(self.DOC_CMD):
            line = line.strip(self.DOC_CMD)
            if not line:
                line = 'dir()'
            elif keyword.iskeyword(line):
                line = 'help("{}")'.format(line)
            else:
                line = 'print({}.__doc__)'.format(line)
        return line

    def write(self, data):
        """Write out errors to stderr
        """
        sys.stderr.write(red(data))

    def resetbuffer(self):
        self.session_history.extend(self.buffer)
        return super(ImprovedConsole, self).resetbuffer()

    def _process_edit_cmd(self):
        # - setup the edit buffer
        fd, filename = mkstemp('.py')
        lines = '\n'.join('# {}'.format(line.strip('\n')) for line in self.session_history)
        os.write(fd, lines.encode('utf-8'))
        os.close(fd)

        # - shell out to the editor
        os.system('{} {}'.format(EDITOR, filename))

        # - process commands
        lines = open(filename)
        os.unlink(filename)
        for stmt in lines:
            self.write(cyan("... {}".format(stmt)))
            line = stmt.strip('\n')
            if not line.strip().startswith('#'):
                self.push(line)
                readline.add_history(line)
        return ''

    def _process_sh_cmd(self, cmd):
        cmd_exec = namedtuple('CmdExec', ['out', 'err', 'rc'])
        if cmd:
            cmd = cmd.format(**self.locals)
            try:
                process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
            except:
                self.showtraceback()
            else:
                out, err = process.communicate()
                rc = process.returncode
                print ('{}'.format(red(err.decode('utf-8')
                       if err else green(out.decode('utf-8'), bold=False))))
                builtins._ = cmd_exec(out, err, rc)
                del cmd_exec
        else:
            if os.environ.get('SSH_CONNECTION'):
                # I use the bash function similar to the one below in my
                # .bashrc to directly open a python prompt on remote
                # systems I log on to.
                #   function rpython { ssh -t $1 -- "python" }
                # Unfortunately, suspending this ssh session, does not place me
                # in a shell, so I need to create one:
                os.system(os.environ.get('SHELL', '/bin/bash'))
            else:
                os.kill(os.getpid(), signal.SIGSTOP)
        return ''


# Welcome message
HELP = cyan("""\
        Welcome to lonetwin's pimped up python prompt
    ( available at https://gist.github.com/lonetwin/5902720 )

You've got color, tab completion, pretty-printing, an editable input buffer
(via the '\e' command) and shell command execution (via the '!' command).

* A tab with preceding text will attempt auto-completion of keywords, name in
the current namespace, attributes and methods. If the preceding text has a
'/' filename completion will be attempted. Without preceding text four spaces
will be inserted.

* History will be saved in {HISTFILE} when you exit.

* The '\e' command will open {EDITOR} with the history for the current
session. On closing the editor any lines not starting with '#' will be
executed.

* The '!' command without anything following it will suspend this process, use
fg to get back.

  - If the '!' command is followed by any text, the text will be executed in
  {SHELL} and the output/error will be displayed.

  - You may pass strings from the global namespace to the command line using
  the `.format()` syntax assuming the globals are passed to format as kwargs.

  - Additionally '_' will contain a named tuple representing the
  (<stdout>, <stderror>, <return_code>) for the execution of the command.

  for example:
  >>> filename='/does/not/exist'
  >>> !ls {{filename}}
  ls: cannot access /does/not/exist: No such file or directory
  >>> _
  CmdExec(out='', err='ls: cannot access /does/not/exist: No such file or directory\n', rc=2)

* Simply typing out a defined name followed by a '?' will print out the
object's __doc__ attribute if one exists. (eg: []? /  str? / os.getcwd? )

""".format(**globals()))

# - create our pimped out console
pymp = ImprovedConsole()

banner="Welcome to the ImprovedConsole. Type in \h for list of features"

# - fire it up !
while True:
    try:
        pymp.interact(banner=banner)
    except:
        import traceback
        print(red("I'm sorry, ImprovedConsole could not handle that !\n"
                  "Please report an error with this traceback, I would really appreciate that !"))
        traceback.print_exc()

        print(red("I shall try to restore the crashed session.\n"
                  "If the crash occurs again, please exit the session"))
        banner=blue("Your crashed session has been restored")
    else:
        break

# Exit the Python shell on exiting the InteractiveConsole
sys.exit()
