#!/usr/bin/env python
# -*- coding: utf-8 -*-
# The MIT License (MIT)
#
# Copyright (c) 2015-2017 Steven Fernandez
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

"""pymp - lonetwin's pimped-up pythonrc

This file will be executed when the Python interactive shell is started, if
$PYTHONSTARTUP is in your environment and points to this file.

You could also simply make this file executable and call it directly.

This file create an InteractiveConsole instance, which provides:
  * execution history
  * colored prompts and pretty printing
  * auto-indentation
  * intelligent tab completion:¹
    - with preceding text
        + names in the current namespace
        + for objects, their attributes/methods
        + for strings with a '/', pathname completion
    - without preceding text four spaces
  * edit the session or a file in your $EDITOR (the '\e' command)
    - with arguments, opens the file in your $EDITOR
    - without argument, open your $EDITOR with the last executed commands
  * temporary escape to $SHELL or ability to execute a shell command and
    capturing the output in to the '_' variable (the '!' command)
  * convenient printing of doc stings (the '?' command) and search for
    entries in online docs (the '??' command)

Some ideas borrowed from:
  * http://eseth.org/2008/pimping-pythonrc.html
    (which co-incidentally reused something I wrote back in 2005 !! Ain't
     sharing great ?)
  * http://igotgenes.blogspot.in/2009/01/tab-completion-and-history-in-python.html

If you have any other good ideas please feel free to submit issues/pull requests.

¹ Since python 3.4 the default interpreter also has tab completion
enabled however it does not do pathname completion
"""

try:
    import builtins
except ImportError:
    import __builtin__ as builtins
import atexit
import glob
import inspect
import keyword
import os
import pkgutil
import pprint
import re
import readline
import rlcompleter
import signal
import subprocess
import sys
import webbrowser

from code import InteractiveConsole
from collections import namedtuple
from tempfile import NamedTemporaryFile

__version__ = "0.4"

config = dict(
    HISTFILE = os.path.expanduser("~/.python_history"),
    HISTSIZE = 1000,
    EDITOR   = os.environ.get('EDITOR', 'vi'),
    SHELL    = os.environ.get('SHELL', '/bin/bash'),
    EDIT_CMD = '\e',
    SH_EXEC  = '!',
    DOC_CMD  = '?',
    DOC_URL  = "https://docs.python.org/{sys.version_info.major}/search.html?q={term}",
    HELP_CMD = '\h',
    LIST_CMD = '\l',
)


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

    def __init__(self, tab='    ', *args, **kwargs):
        self.session_history = [] # This holds the last executed statements
        self.buffer = []          # This holds the statement to be executed
        self.tab = tab
        self._indent = ''
        super(ImprovedConsole, self).__init__(*args, **kwargs)
        self.init_readline()
        self.init_prompt()
        self.init_pprint()

    def init_readline(self):
        """Activates history and tab completion
        """
        # - init history
        if os.path.exists(config['HISTFILE']):
            readline.read_history_file(config['HISTFILE'])

        readline.set_history_length(config['HISTSIZE'])
        atexit.register(lambda :readline.write_history_file(config['HISTFILE']))

        # - turn on tab completion
        readline.parse_and_bind('tab: complete')

        # - enable auto-indenting
        readline.set_pre_input_hook(self.auto_indent_hook)

        # - other useful stuff
        readline.parse_and_bind('set skip-completed-text on')
        readline.set_completer(self.improved_rlcompleter())

    def init_prompt(self):
        """Activates color on the prompt based on python version.

        Also adds the hosts IP if running on a remote host over a
        ssh connection.
        """
        prompt_color = green if sys.version_info.major == 2 else yellow
        sys.ps1 = prompt_color('>>> ', readline_workaround=True)
        sys.ps2 = red('... ', readline_workaround=True)
        # - if we are over a remote connection, modify the ps1
        if os.environ.get('SSH_CONNECTION'):
            this_host = os.environ['SSH_CONNECTION'].split()[-2]
            sys.ps1 = prompt_color('[{}]>>> '.format(this_host), readline_workaround=True)
            sys.ps2 = red('[{}]... '.format(this_host), readline_workaround=True)

    def init_pprint(self):
        """Activates pretty-printing of output values.
        """
        try:
            rows, cols = subprocess.check_output('stty size', shell=True).strip().split()
        except:
            cols = 80
        keys_re = re.compile(r'([\'\("]+(.*?[\'\)"]: ))+?')
        def pprint_callback(value):
            if value is not None:
                builtins._ = value
                formatted = pprint.pformat(value, width=cols)
                if issubclass(type(value), dict):
                    formatted = keys_re.sub(lambda m: purple(m.group()), formatted)
                    print(formatted)
                else:
                    print(blue(formatted))
        sys.displayhook = pprint_callback

    def improved_rlcompleter(self):
        """Enhances the default rlcompleter

        The function enhances the default rlcompleter by also doing
        pathname completion and module name completion for import
        statements. Additionally, it inserts a tab instead of attempting
        completion if there is no preceding text.
        """
        completer = rlcompleter.Completer(namespace=self.locals)
        # - remove / from the delimiters to help identify possibility for path completion
        readline.set_completer_delims(readline.get_completer_delims().replace('/', ''))
        modlist = frozenset(name for _, name, _ in pkgutil.iter_modules())
        def complete_wrapper(text, state):
            line = readline.get_line_buffer().strip()
            if line == '':
                return None if state > 0 else self.tab
            if state == 0:
                if line.startswith('import') or line.startswith('from'):
                    completer.matches = [name for name in modlist if name.startswith(text)]
                else:
                    match = completer.complete(text, state)
                    if match is None and '/' in text:
                        completer.matches = glob.glob(text+'*')
            try:
                match = completer.matches[state]
                return '{}{}'.format(match, ' ' if keyword.iskeyword(match) else '')
            except IndexError:
                return None
        return complete_wrapper

    def auto_indent_hook(self):
        """Hook called by readline between printing the prompt and
        starting to read input.
        """
        readline.insert_text(self._indent)
        readline.redisplay()

    def raw_input(self, *args):
        """Read the input and delegate if necessary.
        """
        line = InteractiveConsole.raw_input(self, *args)
        if line == config['HELP_CMD']:
            print(HELP)
            line = ''
        elif line.startswith(config['EDIT_CMD']):
            line = self.process_edit_cmd(line.strip(config['EDIT_CMD']))
        elif line.startswith(config['SH_EXEC']):
            line = self.process_sh_cmd(line.strip(config['SH_EXEC']))
        elif line.startswith(config['LIST_CMD']):
            # - strip off the possible tab-completed '('
            line = line.rstrip(config['LIST_CMD'] + '(')
            line = self.process_list_cmd(line.strip(config['LIST_CMD']))
        elif line.endswith(config['DOC_CMD']):
            if line.endswith(config['DOC_CMD']*2):
                # search for line in online docs
                # - strip off the '??' and the possible tab-completed
                # '(' or '.' and replace inner '.' with '+' to create the
                # query search string
                line = line.rstrip(config['DOC_CMD'] + '.(').replace('.', '+')
                webbrowser.open(config['DOC_URL'].format(sys=sys, term=line))
                line = ''
            else:
                line = line.rstrip(config['DOC_CMD'] + '.(')
                if not line:
                    line = 'dir()'
                elif keyword.iskeyword(line):
                    line = 'help("{}")'.format(line)
                else:
                    line = 'print({}.__doc__)'.format(line)
        elif line.startswith(self.tab) or self._indent:
            if line.strip():
                # if non empty line with an indent, check if the indent
                # level has been changed
                leading_space = line[:line.index(line.lstrip()[0])]
                if self._indent != leading_space:
                    # indent level changed, update self._indent
                    self._indent = leading_space
            else:
                # - empty line, decrease indent
                self._indent = self._indent[:-len(self.tab)]
                line = self._indent
        return line or ''

    def push(self, line):
        """Wrapper around InteractiveConsole's push method for adding an
        indent on start of a block.
        """
        more = super(ImprovedConsole, self).push(line)
        if more:
            if line.endswith(":"):
                self._indent += self.tab
        else:
            self._indent = ''
        return more

    def write(self, data):
        """Write out data to stderr
        """
        sys.stderr.write(red(data))

    def writeline(self, data):
        return self.write('{}\n'.format(data))

    def resetbuffer(self):
        self._indent = ''
        previous = ''
        for line in self.buffer:
            # - replace multiple empty lines with one before writing to session history
            stripped = line.strip()
            if stripped or stripped != previous:
                self.session_history.append(line)
            previous = stripped
        return super(ImprovedConsole, self).resetbuffer()

    def _doc_to_usage(method):
        def inner(self, arg):
            arg = arg.strip()
            if arg.startswith('-h') or arg.startswith('--help'):
                return self.writeline(blue(method.__doc__.format(**config)))
            else:
                return method(self, arg)
        return inner

    def _mktemp_buffer(self, lines):
        """Writes lines to a temp file and returns the filename.
        """
        with NamedTemporaryFile(suffix='.py', delete=False) as tempbuf:
            tempbuf.writelines(lines)
        return tempbuf.name

    def _exec_from_file(self, filename):
        previous = ''
        for stmt in open(filename):
            # - skip over multiple empty lines
            stripped = stmt.strip()
            if stripped == '' and stripped == previous:
                continue
            self.write(cyan("... {}".format(stmt)))
            if not stripped.startswith('#'):
                line = stmt.strip('\n')
                self.push(line)
                readline.add_history(line)
            previous = stripped

    @_doc_to_usage
    def process_edit_cmd(self, arg=''):
        """{EDIT_CMD} [filename] - Open {EDITOR} with session history or provided filename"""
        if arg:
            filename = arg
        else:
            # - make a list of all lines in session history, commenting
            # any non-blank lines.
            lines = []
            for line in self.session_history:
                line = line.strip('\n')
                if line:
                    lines.append('# {}'.format(line))
                else:
                    lines.append(line)
            filename = self._mktemp_buffer(lines)

        # - shell out to the editor
        os.system('{} {}'.format(config['EDITOR'], filename))

        # - if arg was not provided (we edited session history), execute
        # it in the current namespace
        if not arg:
            self._exec_from_file(filename)
            os.unlink(filename)

    @_doc_to_usage
    def process_sh_cmd(self, cmd):
        """{SH_EXEC} [cmd] - Escape to {SHELL} or execute `cmd` in {SHELL}"""
        cmd_exec = namedtuple('CmdExec', ['out', 'err', 'rc'])
        if cmd:
            cmd = cmd.format(**self.locals)
            if cmd.split()[0] == "cd":
                try:
                    args = cmd.split()
                    if len(args) > 2:
                        raise ValueError("Too many arguments passed to cd")
                    os.chdir(os.path.expanduser(os.path.expandvars(args[1])))
                except:
                    self.showtraceback()
            else:
                try:
                    process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
                os.system(config['SHELL'])
            else:
                os.kill(os.getpid(), signal.SIGSTOP)

    @_doc_to_usage
    def process_list_cmd(self, arg):
        """{LIST_CMD} <object> - List source code for object, if possible."""
        try:
            if not arg:
                self.writeline('source list command requires an argument '
                               '(eg: {} foo)\n'.format(config['LIST_CMD']))
            src_lines, _ = inspect.getsourcelines(eval(arg, {}, self.locals))
        except (IOError, TypeError, NameError) as e:
            self.writeline(e)
        else:
            for line_no, line in enumerate(src_lines):
                self.write(cyan("... {}".format(line)))


# Welcome message
HELP = cyan("""\
        Welcome to lonetwin's pimped up python prompt
    ( available at https://gist.github.com/lonetwin/5902720 )

You've got color, tab completion, auto-indentation, pretty-printing, an
editable input buffer (via the '\e' command), doc string printing (via
the '?' command), online doc search (via the '??' command) and shell
command execution (via the '!' command).

* A tab with preceding text will attempt auto-completion of keywords, name in
the current namespace, attributes and methods. If the preceding text has a
'/' filename completion will be attempted. Without preceding text four spaces
will be inserted.

* History will be saved in {HISTFILE} when you exit.

* The '\e' command without arguments will open {EDITOR} with the history
for the current session. On closing the editor any lines not starting
with '#' will be executed.

* The '\e' command with an filename argument will open the filename in
{EDITOR}.

* The '\l' command with an argument will try to list the source code for
the object provided as the argument.

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

* Typing '??' after something will search for the term at
  {DOC_URL}
  (eg: try webbrowser.open??)
""".format(**config))

# - create our pimped out console
pymp = ImprovedConsole()
banner = "Welcome to the ImprovedConsole. Type in \h for list of features"

# - fire it up !
retries=2
while retries:
    try:
        pymp.interact(banner=banner)
    except SystemExit:
        # Fixes #2: exit when 'quit()' invoked
        break
    except:
        import traceback
        retries -= 1
        print(red("I'm sorry, ImprovedConsole could not handle that !\n"
                  "Please report an error with this traceback, I would really appreciate that !"))
        traceback.print_exc()

        print(red("I shall try to restore the crashed session.\n"
                  "If the crash occurs again, please exit the session"))
        banner=blue("Your crashed session has been restored")
    else:
        # exit with a Ctrl-D
        break

# Exit the Python shell on exiting the InteractiveConsole
sys.exit()
