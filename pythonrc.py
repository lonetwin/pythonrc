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
$PYTHONSTARTUP is in your environment and points to this file. You could
also make this file executable and call it directly.

This file creates an InteractiveConsole instance, which provides:
  * execution history
  * colored prompts and pretty printing
  * auto-indentation
  * intelligent tab completion:¹
  * source code listing for objects
  * session history editing using your $EDITOR, as well as editing of
    source files for objects or regular files
  * temporary escape to $SHELL or ability to execute a shell command and
    capturing the result into the '_' variable
  * convenient printing of doc stings and search for entries in online docs

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
from functools import partial
from tempfile import NamedTemporaryFile


# Fix for Issue #5
# - Exit if being called from within ipython
try:
    if get_ipython():
        sys.exit(0)
except NameError:
    pass


__version__ = "0.5"


config = dict(
    HISTFILE = os.path.expanduser("~/.python_history"),
    HISTSIZE = -1,
    EDITOR   = os.getenv('EDITOR', 'vi'),
    SHELL    = os.getenv('SHELL', '/bin/bash'),
    EDIT_CMD = '\e',
    SH_EXEC  = '!',
    DOC_CMD  = '?',
    DOC_URL  = "https://docs.python.org/{sys.version_info.major}/search.html?q={term}",
    HELP_CMD = '\h',
    LIST_CMD = '\l',
)


class ImprovedConsole(InteractiveConsole, object):
    """
    Welcome to lonetwin's pimped up python prompt

    You've got color, tab completion, auto-indentation, pretty-printing
    and more !

    * A tab with preceding text will attempt auto-completion of
      keywords, names in the current namespace, attributes and methods.
      If the preceding text has a '/', filename completion will be
      attempted. Without preceding text four spaces will be inserted.

    * History will be saved in {HISTFILE} when you exit.

    * Typing out a defined name followed by a '{DOC_CMD}' will print out
      the object's __doc__ attribute if one exists.
      (eg: []? / str? / os.getcwd? )

    * Typing '{DOC_CMD}{DOC_CMD}' after something will search for the term at
      {DOC_URL}
      (eg: try webbrowser.open??)

    * Open the your editor with current session history, source code of
      objects or arbitrary files, using the '{EDIT_CMD}' command.

    * List source code for objects using the '{LIST_CMD}' command.

    * Execute shell commands using the '{SH_EXEC}' command.

    Try `<cmd> -h` for any of the commands to learn more.

    The EDITOR, SHELL, command names and more can be changed in the
    config dict at the top of this file. Make this your own !
    """

    def __init__(self, tab='    ', *args, **kwargs):
        self.session_history = []  # This holds the last executed statements
        self.buffer = []           # This holds the statement to be executed
        self.tab = tab
        self._indent = ''
        super(ImprovedConsole, self).__init__(*args, **kwargs)
        self.init_color_functions()
        self.init_readline()
        self.init_prompt()
        self.init_pprint()

    def init_color_functions(self):
        """Populates globals dict with some helper functions for colorizing text
        """
        def colorize(color_code, text, bold=True, readline_workaround=False):
            code_str = '1;{}'.format(color_code) if bold else color_code
            # - reason for readline_workaround: http://bugs.python.org/issue20359
            if readline_workaround:
                return "\001\033[{}m\002{}\001\033[0m\002".format(code_str, text)
            else:
                return "\033[{}m{}\033[0m".format(code_str, text)

        g = globals()
        for code, color in enumerate(['red', 'green', 'yellow', 'blue', 'purple', 'cyan'], 31):
            g[color] = partial(colorize, code)

    def init_readline(self):
        """Activates history and tab completion
        """
        # - init history
        if os.path.exists(config['HISTFILE']):
            readline.read_history_file(config['HISTFILE'])

        readline.set_history_length(config['HISTSIZE'])
        atexit.register(partial(readline.write_history_file, config['HISTFILE']))

        # - turn on tab completion
        readline.parse_and_bind('tab: complete')
        readline.set_completer(self.improved_rlcompleter())

        # - enable auto-indenting
        readline.set_pre_input_hook(self.auto_indent_hook)

        # - other useful stuff
        readline.read_init_file()

    def init_prompt(self):
        """Activates color on the prompt based on python version.

        Also adds the hosts IP if running on a remote host over a
        ssh connection.
        """
        prompt_color = green if sys.version_info.major == 2 else yellow
        sys.ps1 = prompt_color('>>> ', readline_workaround=True)
        sys.ps2 = red('... ', readline_workaround=True)
        # - if we are over a remote connection, modify the ps1
        if os.getenv('SSH_CONNECTION'):
            _, _, this_host, _ = os.getenv('SSH_CONNECTION').split()
            sys.ps1 = prompt_color('[{}]>>> '.format(this_host), readline_workaround=True)
            sys.ps2 = red('[{}]... '.format(this_host), readline_workaround=True)

    def init_pprint(self):
        """Activates pretty-printing of output values.
        """
        keys_re = re.compile(r'([\'\("]+(.*?[\'\)"]: ))+?')
        color_dict = partial(keys_re.sub, lambda m: purple(m.group()))
        format_func = pprint.pformat
        if sys.version_info.major > 3 and sys.version.minor > 3:
            format_func = partial(pprint.pformat, compact=True)

        def pprint_callback(value):
            if value is not None:
                try:
                    rows, cols = os.get_teminal_size()
                except AttributeError:
                    try:
                        rows, cols = map(int, subprocess.check_output(['stty', 'size']).split())
                    except:
                        cols = 80
                builtins._ = value
                formatted = format_func(value, width=cols)
                print(color_dict(formatted) if issubclass(type(value), dict) else blue(formatted))

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
            print(cyan(self.__doc__).format(**config))
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
        elif line.startswith('%'):
            self.writeline('Y U NO LIKE ME?')
            return line
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
        """Same as write but adds a newline to the end
        """
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
                return self.writeline(blue(method.__doc__.strip().format(**config)))
            else:
                return method(self, arg)
        return inner

    def _mktemp_buffer(self, lines):
        """Writes lines to a temp file and returns the filename.
        """
        with NamedTemporaryFile(mode='w+', suffix='.py', delete=False) as tempbuf:
            tempbuf.write('\n'.join(lines))
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

    def lookup(self, name, namespace=None):
        """Lookup the (dotted) object specified with the string `name`
        in the specified namespace or in the current namespace if
        unspecified.
        """
        components = name.split('.', 1)
        if namespace is None:
            obj = self.locals.get(components.pop(0))
        else:
            obj = getattr(namespace, components.pop(0), namespace)
        return self.lookup(components[0], obj) if components else obj

    @_doc_to_usage
    def process_edit_cmd(self, arg=''):
        """{EDIT_CMD} [object|filename]

        Open {EDITOR} with session history, provided filename or
        object's source file.

        - without arguments, a temporary file containing session history is
          created and opened in {EDITOR}. On quitting the editor, all
          the non commented lines in the file are executed.

        - with a filename argument, the file is opened in the editor. On
          close, you are returned bay to the interpreter.

        - with an object name argument, an attempt is made to lookup the
          source file of the object and it is opened if found. Else the
          argument is treated as a filename.
        """
        if arg:
            obj = self.lookup(arg)
            try:
                filename = inspect.getsourcefile(obj) if obj else arg
            except (IOError, TypeError, NameError) as e:
                return self.writeline(e)
        else:
            # - make a list of all lines in session history, commenting
            # any non-blank lines.
            filename = self._mktemp_buffer("# {}".format(line) if line else ''
                                           for line in (line.strip('\n') for line in self.session_history))

        # - shell out to the editor
        os.system('{} {}'.format(config['EDITOR'], filename))

        # - if arg was not provided (we edited session history), execute
        # it in the current namespace
        if not arg:
            self._exec_from_file(filename)
            os.unlink(filename)

    @_doc_to_usage
    def process_sh_cmd(self, cmd):
        """{SH_EXEC} [cmd [args ...] | {{fmt string}}]

        Escape to {SHELL} or execute `cmd` in {SHELL}

        - without arguments, the current interpreter will be suspended
          and you will be dropped in a {SHELL} prompt. Use fg to return.

        - with arguments, the text will be executed in {SHELL} and the
          output/error will be displayed. Additionally '_' will contain
          a named tuple with the (<stdout>, <stderror>, <return_code>)
          for the execution of the command.

          You may pass strings from the global namespace to the command
          line using the `.format()` syntax. for example:

        >>> filename = '/does/not/exist'
        >>> !ls {{{{filename}}}}
        ls: cannot access /does/not/exist: No such file or directory
        >>> _
        CmdExec(out='', err='ls: cannot access /does/not/exist: No such file or directory\n', rc=2)
        """
        if cmd:
            try:
                cmd = cmd.format(**self.locals)
                if cmd.split()[0] == "cd":
                    args = cmd.split()
                    if len(args) > 2:
                        raise ValueError("Too many arguments passed to cd")
                    os.chdir(os.path.expanduser(os.path.expandvars(args[1])))
                else:
                    cmd_exec = namedtuple('CmdExec', ['out', 'err', 'rc'])
                    process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    out, err = process.communicate()
                    rc = process.returncode
                    print (red(err.decode('utf-8')) if err else green(out.decode('utf-8'), bold=False))
                    builtins._ = cmd_exec(out, err, rc)
                    del cmd_exec
            except:
                self.showtraceback()
        else:
            if os.getenv('SSH_CONNECTION'):
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
        """
        {LIST_CMD} <object> - List source code for object, if possible.
        """
        try:
            if not arg:
                self.writeline('source list command requires an argument '
                               '(eg: {} foo)\n'.format(config['LIST_CMD']))
            src_lines, offset = inspect.getsourcelines(self.lookup(arg))
        except (IOError, TypeError, NameError) as e:
            self.writeline(e)
        else:
            for line_no, line in enumerate(src_lines):
                self.write(cyan("{0:03d}: {1}".format(offset + line_no + 1, line)))

    def interact(self):
        """A forgiving wrapper around InteractiveConsole.interact()
        """
        banner = ("Welcome to the ImprovedConsole (version {version})\n"
                  "Type in {HELP_CMD} for list of features.").format(version=__version__,
                                                                    **config)
        retries = 2
        while retries:
            try:
                super(ImprovedConsole, self).interact(banner=banner)
            except SystemExit:
                # Fixes #2: exit when 'quit()' invoked
                break
            except:
                import traceback
                retries -= 1
                print(red("I'm sorry, ImprovedConsole could not handle that !\n"
                          "Please report an error with this traceback, "
                          "I would really appreciate that !"))
                traceback.print_exc()

                print(red("I shall try to restore the crashed session.\n"
                          "If the crash occurs again, please exit the session"))
                banner = blue("Your crashed session has been restored")
            else:
                # exit with a Ctrl-D
                break

        # Exit the Python shell on exiting the InteractiveConsole
        sys.exit()


if not os.getenv('SKIP_PYMP'):
    # - create our pimped out console and fire it up !
    pymp = ImprovedConsole().interact()
