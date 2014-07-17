# -*- coding: utf-8 -*-
"""lonetwin's pimped-up pythonrc

A custom pythonrc which provides:
  * colored prompts
  * intelligent tab completion
    (for objects and their attributes/methods in the current namespace as well
     as file-system paths)
  * pretty-printing
  * shortcut to open your $EDITOR with the last executed command
    (the '\e' command)
  * temporary escape to shell or executing a shell command and capturing the
    output (the '!' command)
  * execution history

Some ideas borrowed from:
  * http://eseth.org/2008/pimping-pythonrc.html
    (which co-incidentally reused something I wrote back in 2005 !! Ain't
     sharing great ?)
  * http://igotgenes.blogspot.in/2009/01/tab-completion-and-history-in-python.html

This file is executed when the Python interactive shell is started if
$PYTHONSTARTUP is in your environment and points to this file.

If you have any other good ideas please feel free to leave a comment.
"""
import sys
import os
import signal
import readline, rlcompleter
import atexit
import pprint
import glob
import subprocess
from tempfile import mkstemp
from code import InteractiveConsole

# Intelligent Tab completion support borrowed from
# http://igotgenes.blogspot.in/2009/01/tab-completion-and-history-in-python.html
class IrlCompleter(rlcompleter.Completer):
    """
    This class enables a "tab" insertion if there's no text for
    completion.

    The default "tab" is four spaces. You can initialize with '\t' as
    the tab if you wish to use a genuine tab.
    """

    def __init__(self, tab='    ', namespace = None):
        self.tab = tab
        # - remove / from the delimiters to enable path completion
        readline.set_completer_delims(
                readline.get_completer_delims().replace('/', ''))
        rlcompleter.Completer.__init__(self, namespace)

    def complete(self, text, state):
        if text == '':
            return None if state > 0 else self.tab
        else:
            matches = rlcompleter.Completer.complete(self, text, state)
            if matches is None:
                if '/' in text:
                    try:
                        matches = glob.glob(text+'*')[state]
                    except IndexError:
                        return None
        return matches



# Enable History
HISTFILE="%s/.pyhistory" % os.environ["HOME"]

# Read the existing history if there is one
if os.path.exists(HISTFILE):
    readline.read_history_file(HISTFILE)

# Set maximum number of items that will be written to the history file
readline.set_history_length(300)

atexit.register(lambda :readline.write_history_file(HISTFILE))

# Enable Color Prompts
# - borrowed from fabric (also used in botosh)
def _color_fn(code):
    def inner(text, bold=False, readline_workaround=False):
        # - reason for readline_workaround: http://bugs.python.org/issue20359
        if readline_workaround:
            return "\001\033[%sm\002%s\001\033[0m\002" % ('1;%d' % code if bold else str(code), text)
        else:
            return "\033[%sm%s\033[0m" % ('1;%d' % code if bold else str(code), text)
    return inner


# add any colors you might need.
_red   = _color_fn(31)
_green = _color_fn(32)
_cyan  = _color_fn(36)
_blue  = _color_fn(34)

# - if we are a remote connection, modify the ps1
if os.environ.get('SSH_CONNECTION'):
    this_host = os.environ['SSH_CONNECTION'].split()[-2]
    sys.ps1 = _green('[%s]>>> ' % this_host, readline_workaround=True)
    sys.ps2 = _red('[%s]... '   % this_host, readline_workaround=True)
else:
    sys.ps1 = _green('>>> ', readline_workaround=True)
    sys.ps2 = _red('... ', readline_workaround=True)

# Enable Pretty Printing for stdout
# - get terminal size for passing width param to pprint. Queried just once at
# startup
try:
    _rows, _cols = subprocess.check_output('stty size', shell=True).strip().split()
except:
    _cols = 80

def my_displayhook(value):
    import re
    import __builtin__
    if value is not None:
        __builtin__._ = value

        formatted = pprint.pformat(value, width=_cols)
        if issubclass(type(value), dict):
            formatted = re.sub(
                    r'["\'\\]+(\w+)["\'\\]+: ',
                    lambda m: "'%s': " % _red(m.group(1), bold=True),
                    formatted)
            print(formatted)
        else:
            print(_blue(formatted, bold=True))

sys.displayhook = my_displayhook

# Start an external editor with \e
EDITOR = os.environ.get('EDITOR', 'vi')
EDIT_CMD = '\e'
SH_EXEC  = '!'

class EditableBufferInteractiveConsole(InteractiveConsole, object):
    def __init__(self, *args, **kwargs):
        self.last_buffer = [] # This holds the last executed statements
        self.buffer = []      # This holds the statement to be executed
        super(EditableBufferInteractiveConsole, self).__init__(*args, **kwargs)

    def resetbuffer(self):
        self.last_buffer.extend(self.buffer)
        return super(EditableBufferInteractiveConsole, self).resetbuffer()

    def raw_input(self, *args):
        line = super(EditableBufferInteractiveConsole, self).raw_input(*args)
        if line == EDIT_CMD:
            fd, tmpfl = mkstemp('.py')
            for line in self.last_buffer:
                os.write(fd, '%s\n' % (line if line.startswith('#') else '# %s' % line))
            os.close(fd)
            os.system('%s %s' % (EDITOR, tmpfl))
            line = open(tmpfl).read()
            os.unlink(tmpfl)
            tmpfl = ''
            lines = line.split('\n')
            self.write(_cyan(">>> %s\n" % '\n... '.join(line for line in lines if not line.startswith('#'))))
            for stmt in lines[:-1]:
                if not stmt.startswith('#'):
                    self.push(stmt)
            line = lines[-1]

        if line.startswith(SH_EXEC):
            import __builtin__
            cmd = line.strip(SH_EXEC)
            if cmd:
                out, err = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        shell=True).communicate()
                print (err and _red(err)) or (out and _green(out))
                __builtin__._ = (out, err)
            else:
                if os.environ.get('SSH_CONNECTION'):
                    # I use the bash function below in my .bashrc to directly
                    # open a python prompt on remote systems I log on to.
                    #   function rpython { ssh -t $1 -- "python" }
                    # Unfortunately, suspending this ssh session, does not
                    # place me in a shell, so I need to create one:
                    os.system(os.environ.get('SHELL', '/bin/bash'))
                else:
                    os.kill(os.getpid(), signal.SIGSTOP)
            line = ''
        return line

    def write(self, data):
        sys.stderr.write(_red(data, bold=True))

# Welcome message
WELCOME = _cyan("""\
You've got color, tab completion, pretty-printing, an editable input buffer
(via the '\e' command) and shell command execution (via the '!' command).

History will be saved in %s when you exit.

The '\e' command will open %s with the history for the current
session. On closing the editor any lines not starting with '#' will be executed
(only one statement can be executed at a time)

The '!' command without anything following it will suspend this process, use fg
to get back.

If the '!' command is followed by any text, the text will be executed in %s
and the output/error will be displayed. Additionally '_' will contain the tuple
(<stdout>, <stderror>) for the execution of the command.
""" % (HISTFILE, EDITOR, os.environ.get('SHELL', '$SHELL')))

# - create our pimped out console
__c = EditableBufferInteractiveConsole()

# - turn on the completer
# you could change this line to bind another key instead of tab.
readline.parse_and_bind('tab: complete')
readline.set_completer(IrlCompleter(tab='\t', namespace=__c.locals).complete)

# - fire it up !
__c.interact(banner=WELCOME)

# Exit the Python shell on exiting the InteractiveConsole
sys.exit()
