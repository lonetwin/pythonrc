#!/usr/bin/env python
# -*- coding: utf-8 -*-
# The MIT License (MIT)
#
# Copyright (c) 2015-2020 Steven Fernandez
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

# Keep a copy of the initial namespace, we'll need it later
CLEAN_NS = globals().copy()

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
  * auto-execution of a virtual env specific (`.venv_rc.py`) file at startup

If you have any other good ideas please feel free to submit issues/pull requests.

¹ Since python 3.4 the default interpreter also has tab completion
enabled however it does not do pathname completion
"""


# Fix for Issue #5
# - Exit if being called from within ipython
try:
    import sys
    __IPYTHON__ and sys.exit(0)
except NameError:
    pass

import atexit
import glob
import importlib
import inspect
import keyword
import os
import pkgutil
import pprint
import re
import readline
import rlcompleter
import shlex
import signal
import subprocess
import webbrowser

from code import InteractiveConsole
from functools import partial, lru_cache, cached_property
from itertools import chain
from operator import attrgetter
from tempfile import NamedTemporaryFile
from types import SimpleNamespace

__version__ = "0.9.0"


config = SimpleNamespace(
    ONE_INDENT  = '    ',  # what should we use for indentation ?
    HISTFILE    = os.path.expanduser("~/.python_history"),
    HISTSIZE    = -1,
    EDITOR      = os.getenv('EDITOR', 'vi'),
    SHELL       = os.getenv('SHELL', '/bin/bash'),
    EDIT_CMD    = r'\e',
    SH_EXEC     = '!',
    DOC_CMD     = '?',
    DOC_URL     = "https://docs.python.org/{sys.version_info.major}/search.html?q={term}",
    HELP_CMD    = r'\h',
    LIST_CMD    = r'\l',
    AUTO_INDENT = True,     # - Should we auto-indent by default
    VENV_RC     = os.getenv("VENV_RC", ".venv_rc.py"),
    # - option to pass to the editor to open a file at a specific
    # `line_no`. This is used when the EDIT_CMD is invoked with a python
    # object to open the source file for the object.
    LINE_NUM_OPT="+{line_no}",
    # - Run-time toggle for auto-indent command (eg: when pasting code)
    TOGGLE_AUTO_INDENT_CMD = r'\\',
    # - should path completion expand ~ using os.path.expanduser()
    COMPLETION_EXPANDS_TILDE = True,
    # - when executing edited history, should we also print comments
    POST_EDIT_PRINT_COMMENTS = True,
)

# Color functions. These get initialized in init_color_functions() later
red = green = yellow = blue = purple = cyan = grey = str


class ImprovedCompleter(rlcompleter.Completer):
    """A smarter rlcompleter.Completer"""

    def __init__(self, namespace=None):
        super().__init__(namespace)
        # - remove '/' and '~' from delimiters to help with path completion
        completer_delims = readline.get_completer_delims()
        completer_delims = completer_delims.replace('/', '')
        if config.COMPLETION_EXPANDS_TILDE:
            completer_delims = completer_delims.replace('~', '')
        readline.set_completer_delims(completer_delims)
        self.matches = []

    @lru_cache(None)
    def pkg_contents(self, pkg):
        """Given a package name, return a list of it's sub-modules."""
        spec = importlib.util.find_spec(pkg)
        locs = [spec.origin] if not spec.parent else spec.submodule_search_locations
        return [pkg.name for pkg in pkgutil.walk_packages(locs, f'{pkg}.', onerror=lambda _: None)]

    @cached_property
    def pkglist(self):
        return frozenset(item.name for item in pkgutil.iter_modules() if item.ispkg)

    @cached_property
    def modlist(self):
        modlist = chain(sys.builtin_module_names, map(attrgetter('name'), pkgutil.iter_modules()))
        return frozenset(name for name in modlist if not name.startswith('_'))

    def exceptions(self, exc_cls=Exception):
        exc_names = [exc.__name__ for exc in exc_cls.__subclasses__()]
        for sub_cls in exc_cls.__subclasses__():
            exc_names.extend(self.exceptions(sub_cls))
        return exc_names

    def startswith_filter(self, text, names, striptext=None):
        filtered = [name for name in names if name.startswith(text)]
        if striptext:
            return [name.replace(striptext, '') for name in filtered]
        return filtered

    def get_path_matches(self, text):
        return [f'{item}{os.path.sep}' if os.path.isdir(item) else item
                for item in glob.iglob(f'{text}**')]

    def get_import_matches(self, text, words):
        if any([(len(words) == 2 and not text),
                (len(words) == 3 and text and 'import'.startswith(text))]):
            return ['import ']

        if len(words) <= 2:
            # import p<tab> / from p<tab>
            modname, _, _ = text.partition('.')
            if modname in self.pkglist:
                return self.startswith_filter(text, self.pkg_contents(modname))
            return self.startswith_filter(text, self.modlist)

        if len(words) >= 3 and words[2] == 'import':
            # from pkg.sub import na<tab>
            namespace = words[1]
            pkg, _, _ = namespace.partition('.')
            if pkg in self.pkglist:
                # from pkg.sub import na<tab>
                match_text = '.'.join((namespace, text))
                if (
                    matches := self.startswith_filter(
                        match_text, self.pkg_contents(pkg), striptext=f'{namespace}.'
                    )
                ):
                    return matches

            # from module import na<ta>
            mod = importlib.import_module(namespace)
            return self.startswith_filter(text, getattr(mod, '__all__', dir(mod)))

    def complete(self, text, state, line=None):
        if not line:
            line = readline.get_line_buffer()

        if line == '' or line.isspace():
            return None if state else config.ONE_INDENT

        words = line.split()
        if state == 0:
            # - this is the first completion is being attempted for
            # text, we need to populate self.matches, just like
            # super().complete()
            if line.startswith(('from ', 'import ')):
                self.matches = self.get_import_matches(text, words)
            elif words[0] in ('raise', 'except'):
                self.matches = self.startswith_filter(text.lstrip('('), self.exceptions())
            elif os.path.sep in text:
                self.matches = self.get_path_matches(
                    os.path.expanduser(text) if config.COMPLETION_EXPANDS_TILDE else text
                )
            elif "." in text:
                self.matches = self.attr_matches(text)
            else:
                self.matches = self.global_matches(text)

            if self.matches and self.matches[-1] is None:
                match = self.matches[0]
                if keyword.iskeyword(match) and match in ('raise', 'except'):
                    self.matches = self.exceptions()

                if match and match.endswith(os.path.sep):
                    self.matches = self.get_path_matches(match)

            self.matches.append(None)

        try:
            return self.matches[state]
        except IndexError:
            return None


class ImprovedConsole(InteractiveConsole):
    """
    Welcome to lonetwin's pimped up python prompt

    You've got color, tab completion, auto-indentation, pretty-printing
    and more !

    * A tab with preceding text will attempt auto-completion of
      keywords, names in the current namespace, attributes and methods.
      If the preceding text has a '/', filename completion will be
      attempted. Without preceding text four spaces will be inserted.

    * History will be saved in {HISTFILE} when you exit.

    * If you create a file named {VENV_RC} in the current directory, the
      contents will be executed in this session before the prompt is
      shown.

    * Typing out a defined name followed by a '{DOC_CMD}' will print out
      the object's __doc__ attribute if one exists.
      (eg: []? / str? / os.getcwd? )

    * Typing '{DOC_CMD}{DOC_CMD}' after something will search for the
      term at {DOC_URL}
      (eg: try webbrowser.open??)

    * Open the your editor with current session history, source code of
      objects or arbitrary files, using the '{EDIT_CMD}' command.

    * List source code for objects using the '{LIST_CMD}' command.

    * Execute shell commands using the '{SH_EXEC}' command.

    Try `<cmd> -h` for any of the commands to learn more.

    The EDITOR, SHELL, command names and more can be changed in the
    config declaration at the top of this file. Make this your own !
    """

    def __init__(self, *args, **kwargs):
        self.session_history = []  # This holds the last executed statements
        self.buffer = []           # This holds the statement to be executed
        self._indent = ''
        super(ImprovedConsole, self).__init__(*args, **kwargs)
        self.init_color_functions()
        self.init_readline()
        self.init_prompt()
        self.init_pprint()
        # - dict mapping commands to their handler methods
        self.commands = {
            config.EDIT_CMD: self.process_edit_cmd,
            config.LIST_CMD: self.process_list_cmd,
            config.SH_EXEC: self.process_sh_cmd,
            config.HELP_CMD: self.process_help_cmd,
            config.TOGGLE_AUTO_INDENT_CMD: self.toggle_auto_indent
        }
        # - regex to identify and extract commands and their arguments
        self.commands_re = re.compile(
            r'(?P<cmd>{})\s*(?P<args>[^(]*)'.format(
                '|'.join(re.escape(cmd) for cmd in self.commands)
            )
        )

    def _doc_to_usage(method):
        def inner(self, arg):
            arg = arg.strip()
            if arg.startswith(('-h', '--help')):
                return self.writeline(blue(method.__doc__.strip()))
            return method(self, arg)
        return inner

    def init_color_functions(self):
        """Populates globals dict with some helper functions for colorizing text
        """
        def colorize(color_code, text, bold=True, readline_workaround=False):
            reset = '\033[0m'
            color = '\033[{0}{1}m'.format('1;' if bold else '', color_code)
            # - reason for readline_workaround: http://bugs.python.org/issue20359
            if readline_workaround:
                return f"\001{color}\002{text}\001{reset}\002"
            return f"{color}{text}{reset}"

        g = globals()
        for code, color in enumerate(
            ['red', 'green', 'yellow', 'blue', 'purple', 'cyan', 'grey'], 31
        ):
            g[color] = partial(colorize, code)

    def init_readline(self):
        """Activates history and tab completion
        """
        # - 1. history stuff
        # - mainly borrowed from site.enablerlcompleter() from py3.4+,
        # we can't simply call site.enablerlcompleter() because its
        # implementation overwrites the history file for each python
        # session whereas we prefer appending history from every
        # (potentially concurrent) session.

        # Reading the initialization (config) file may not be enough to set a
        # completion key, so we set one first and then read the file.
        readline_doc = getattr(readline, '__doc__', '')
        if readline_doc is not None and 'libedit' in readline_doc:
            readline.parse_and_bind('bind ^I rl_complete')
        else:
            readline.parse_and_bind('tab: complete')

        try:
            readline.read_init_file()
        except OSError:
            # An OSError here could have many causes, but the most likely one
            # is that there's no .inputrc file (or .editrc file in the case of
            # Mac OS X + libedit) in the expected location.  In that case, we
            # want to ignore the exception.
            pass

        def append_history(len_at_start):
            current_len = readline.get_current_history_length()
            readline.append_history_file(current_len - len_at_start, config.HISTFILE)

        if readline.get_current_history_length() == 0:
            # If no history was loaded, default to .python_history.
            # The guard is necessary to avoid doubling history size at
            # each interpreter exit when readline was already configured
            # see: http://bugs.python.org/issue5845#msg198636
            try:
                readline.read_history_file(config.HISTFILE)
            except IOError:
                pass
            len_at_start = readline.get_current_history_length()
            atexit.register(append_history, len_at_start)

        readline.set_history_length(config.HISTSIZE)

        # - 2. enable auto-indenting
        if config.AUTO_INDENT:
            readline.set_pre_input_hook(self.auto_indent_hook)

        # - 3. completion
        # - replace default completer
        self.completer = ImprovedCompleter(self.locals)
        readline.set_completer(self.completer.complete)

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
            sys.ps1 = prompt_color(f'[{this_host}]>>> ', readline_workaround=True)
            sys.ps2 = red(f'[{this_host}]... ', readline_workaround=True)

    def init_pprint(self):
        """Activates pretty-printing of output values.
        """
        keys_re = re.compile(r'([\'\("]+(.*?[\'\)"]: ))+?')
        color_dict = partial(keys_re.sub, lambda m: purple(m.group()))
        format_func = pprint.pformat
        if sys.version_info.major >= 3 and sys.version_info.minor > 3:
            format_func = partial(pprint.pformat, compact=True)

        def pprint_callback(value):
            if value is not None:
                try:
                    rows, cols = os.get_teminal_size()
                except AttributeError:
                    try:
                        rows, cols = map(int, subprocess.check_output(['stty', 'size']).split())
                    except Exception:
                        cols = 80
                formatted = format_func(value, width=cols)
                print(color_dict(formatted) if issubclass(type(value), dict) else blue(formatted))
            self.locals['_'] = value

        sys.displayhook = pprint_callback

    def auto_indent_hook(self):
        """Hook called by readline between printing the prompt and
        starting to read input.
        """
        readline.insert_text(self._indent)
        readline.redisplay()

    @_doc_to_usage
    def toggle_auto_indent(self, _):
        """{config.TOGGLE_AUTO_INDENT_CMD} - Toggles the auto-indentation behavior
        """
        hook = None if config.AUTO_INDENT else self.auto_indent_hook
        msg = '# Auto-Indent has been {}abled\n'.format('en' if hook else 'dis')
        config.AUTO_INDENT = bool(hook)

        if hook is None:
            msg += ('# End of blocks will be detected after 3 empty lines\n'
                    f'# Re-type {config.TOGGLE_AUTO_INDENT_CMD} on a line by itself to enable')

        readline.set_pre_input_hook(hook)
        print(grey(msg, bold=False))
        return ''

    def raw_input(self, prompt=''):
        """Read the input and delegate if necessary.
        """
        line = super(ImprovedConsole, self).raw_input(prompt)
        empty_lines = 3 if line else 1
        while not config.AUTO_INDENT and empty_lines < 3:
            line = super(ImprovedConsole, self).raw_input(prompt)
            empty_lines += 1 if not line else 3
        return self._cmd_handler(line)

    def _cmd_handler(self, line):
        if (matches := self.commands_re.match(line)):
            command, args = matches.groups()
            line = self.commands[command](args)
        elif line.endswith(config.DOC_CMD):
            if line.endswith(config.DOC_CMD * 2):
                # search for line in online docs
                # - strip off the '??' and the possible tab-completed
                # '(' or '.' and replace inner '.' with '+' to create the
                # search query string
                line = line.rstrip(f'{config.DOC_CMD}.(').replace('.', '+')
                webbrowser.open(config.DOC_URL.format(sys=sys, term=line))
                line = ''
            else:
                line = line.rstrip(f'{config.DOC_CMD}.(')
                if not line:
                    line = 'dir()'
                elif keyword.iskeyword(line):
                    line = f'help("{line}")'
                else:
                    line = f'print({line}.__doc__)'
        elif config.AUTO_INDENT and (line.startswith(config.ONE_INDENT) or self._indent):
            if line.strip():
                # if non empty line with an indent, check if the indent
                # level has been changed
                leading_space = line[:line.index(line.lstrip()[0])]
                if self._indent != leading_space:
                    # indent level changed, update self._indent
                    self._indent = leading_space
            else:
                # - empty line, decrease indent
                self._indent = self._indent[:-len(config.ONE_INDENT)]
                line = self._indent
        elif line.startswith('%'):
            self.writeline('Y U NO LIKE ME?')
            return line
        return line or ''

    def push(self, line):
        """Wrapper around InteractiveConsole's push method for adding an
        indent on start of a block.
        """
        if (more := super(ImprovedConsole, self).push(line)):
            if line.endswith((':', '[', '{', '(')):
                self._indent += config.ONE_INDENT
        else:
            self._indent = ''
        return more

    def write(self, data):
        """Write out data to stderr
        """
        sys.stderr.write(data if data.startswith('\033[') else red(data))

    def writeline(self, data):
        """Same as write but adds a newline to the end
        """
        return self.write(f'{data}\n')

    def resetbuffer(self):
        self._indent = previous = ''
        for line in self.buffer:
            # - replace multiple empty lines with one before writing to session history
            stripped = line.strip()
            if stripped or stripped != previous:
                self.session_history.append(line)
            previous = stripped
        return super(ImprovedConsole, self).resetbuffer()

    def _mktemp_buffer(self, lines):
        """Writes lines to a temp file and returns the filename.
        """
        with NamedTemporaryFile(mode='w+', suffix='.py', delete=False) as tempbuf:
            tempbuf.write('\n'.join(lines))
        return tempbuf.name

    def showtraceback(self, *args):
        """Wrapper around super(..).showtraceback()

        We do this to detect whether any subsequent statements after a
        traceback occurs should be skipped. This is relevant when
        executing multiple statements from an edited buffer.
        """
        self._skip_subsequent = True
        return super(ImprovedConsole, self).showtraceback(*args)

    def _exec_from_file(self, open_fd, quiet=False, skip_history=False,
                        print_comments=config.POST_EDIT_PRINT_COMMENTS):
        self._skip_subsequent = False
        previous = ''
        for stmt in open_fd:
            # - skip over multiple empty lines
            stripped = stmt.strip()
            if stripped == previous == '':
                continue

            # - if line is a comment, print (if required) and move to
            # next line
            if stripped.startswith('#'):
                if print_comments and not quiet:
                    self.write(grey(f"... {stmt}", bold=False))
                continue

            # - process line only if we haven't encountered an error yet
            if not self._skip_subsequent:
                line = stmt.strip('\n')
                if line and not line[0].isspace():
                    # - end of previous statement, submit buffer for
                    # execution
                    source = "\n".join(self.buffer)
                    more = self.runsource(source, self.filename)
                    if not more:
                        self.resetbuffer()

            if not quiet:
                self.write(cyan(f"... {stmt}", bold=(not self._skip_subsequent)))

            if self._skip_subsequent:
                self.session_history.append(stmt)
            else:
                self.buffer.append(line)
                if not skip_history:
                    readline.add_history(line)
            previous = stripped
        self.push('')

    def lookup(self, name, namespace=None):
        """Lookup the (dotted) object specified with the string `name`
        in the specified namespace or in the current namespace if
        unspecified.
        """
        name, _, components = name.partition('.')
        obj = getattr(namespace, name, namespace) if namespace else self.locals.get(name)
        return self.lookup(components, obj) if components else obj

    @_doc_to_usage
    def process_edit_cmd(self, arg=''):
        """{config.EDIT_CMD} [object|filename]

        Open {config.EDITOR} with session history, provided filename or
        object's source file.

        - without arguments, a temporary file containing session history is
          created and opened in {config.EDITOR}. On quitting the editor, all
          the non commented lines in the file are executed, if the
          editor exits with a 0 return code (eg: if editor is `vim`, and
          you exit using `:cq`, nothing from the buffer is executed and
          you are returned to the prompt).

        - with a filename argument, the file is opened in the editor. On
          close, you are returned bay to the interpreter.

        - with an object name argument, an attempt is made to lookup the
          source file of the object and it is opened if found. Else the
          argument is treated as a filename.
        """
        line_num_opt = ''
        if arg:
            try:
                if (obj := self.lookup(arg)):
                    filename = inspect.getsourcefile(obj)
                    _, line_no = inspect.getsourcelines(obj)
                    line_num_opt = config.LINE_NUM_OPT.format(line_no=line_no)
                else:
                    filename = arg
            except (IOError, TypeError, NameError) as e:
                return self.writeline(e)
        else:
            # - make a list of all lines in history, commenting any non-blank lines.
            history = self.session_history or open(config.HISTFILE)
            filename = self._mktemp_buffer(
                f'# {line}' if line.strip() else ''
                for line in (line.strip('\n') for line in history)
            )

        # - shell out to the editor
        rc = os.system(f'{config.EDITOR} {line_num_opt} {filename}')

        # - if arg was not provided (ie: we edited history), execute
        # un-commented lines in the current namespace
        if not arg:
            if rc == 0:
                # - if HISTFILE contents were edited (ie: EDIT_CMD in a
                # brand new session), don't print commented out lines
                print_comments = (False if history != self.session_history
                                  else config.POST_EDIT_PRINT_COMMENTS)
                with open(filename) as edits:
                    self._exec_from_file(edits, print_comments=print_comments)
            else:
                self.writeline(f'{config.EDITOR} exited with an error code. Skipping execution.')
            os.unlink(filename)

    @_doc_to_usage
    def process_sh_cmd(self, cmd):
        """{config.SH_EXEC} [cmd [args ...] | {{fmt string}}]

        Escape to {config.SHELL} or execute `cmd` in {config.SHELL}

        - without arguments, the current interpreter will be suspended
          and you will be dropped in a {config.SHELL} prompt. Use fg to return.

        - with arguments, the text will be executed in {config.SHELL} and the
          output/error will be displayed. Additionally '_' will contain
          a named tuple with the (<stdout>, <stderror>, <return_code>)
          for the execution of the command.

          You may pass strings from the global namespace to the command
          line using the `.format()` syntax. for example:

        >>> filename = '/does/not/exist'
        >>> !ls {{filename}}
        ls: cannot access /does/not/exist: No such file or directory
        >>> _
        CompletedProcess(arg=['ls'], returncode=0, stdout=b'', stderr=b'ls:
        cannot access /does/not/exist: No such file or directory\n')
        """
        if cmd:
            try:
                cmd = cmd.format(**self.locals)
                cmd = shlex.split(cmd)
                if cmd[0] == 'cd':
                    os.chdir(os.path.expanduser(os.path.expandvars(' '.join(cmd[1:]) or '${HOME}')))
                else:
                    completed = subprocess.run(cmd, capture_output=True, env=os.environ, text=True)
                    out, rc = completed.stdout, completed.returncode
                    print(red(out) if rc else green(out, bold=False))
                    self.locals['_'] = completed
            except Exception:
                self.showtraceback()
        else:
            if os.getenv('SSH_CONNECTION'):
                # I use the bash function similar to the one below in my
                # .bashrc to directly open a python prompt on remote
                # systems I log on to.
                #   function rpython { ssh -t $1 -- "python" }
                # Unfortunately, suspending this ssh session, does not place me
                # in a shell, so I need to create one:
                os.system(config.SHELL)
            else:
                os.kill(os.getpgrp(), signal.SIGSTOP)

    @_doc_to_usage
    def process_list_cmd(self, arg):
        """{config.LIST_CMD} <object> - List source code for object, if possible.
        """
        if not arg:
            return self.writeline('source list command requires an '
                                  f'argument (eg: {config.LIST_CMD} foo)')
        try:
            src_lines, offset = inspect.getsourcelines(self.lookup(arg))
        except (IOError, TypeError, NameError) as e:
            self.writeline(e)
        else:
            for line_no, line in enumerate(src_lines, offset + 1):
                self.write(cyan(f"{line_no:03d}: {line}"))

    def process_help_cmd(self, arg):
        if arg:
            if keyword.iskeyword(arg):
                self.push(f'help("{arg}")')
            elif arg in self.commands:
                self.commands[arg]('-h')
            else:
                self.push(f'help({arg})')
        else:
            print(cyan(self.__doc__).format(**config.__dict__))

    def interact(self):
        """A forgiving wrapper around InteractiveConsole.interact()
        """
        venv_rc_done = cyan('(no venv rc found)')
        try:
            with open(config.VENV_RC) as venv_rc:
                self._exec_from_file(venv_rc, quiet=True, skip_history=True)
            # - clear out session_history for venv_rc commands
            self.session_history = []
            venv_rc_done = green('Successfully executed venv rc !')
        except IOError:
            pass

        banner = (f"Welcome to the ImprovedConsole (version {__version__})\n"
                  f"Type in {config.HELP_CMD} for list of features.\n"
                  f"{venv_rc_done}")

        retries = 2
        while retries:
            try:
                super(ImprovedConsole, self).interact(banner=banner)
            except SystemExit:
                # Fixes #2: exit when 'quit()' invoked
                break
            except Exception:
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
    pymp = ImprovedConsole(locals=CLEAN_NS)
    pymp.locals['__pymp__'] = pymp
    pymp.interact()
