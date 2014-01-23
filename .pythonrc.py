# -*- coding: utf-8 -*-
"""lonetwin's pimped-up pythonrc

A custom pythonrc which provides colored prompts, intelligent tab completion
pretty-printing, shortcut to open your $EDITOR with the last executed command
and it also retains history.

Ideas borrowed from:
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
import readline, rlcompleter
import atexit
import pprint
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

    def __init__(self):
        self.tab = '    '
        rlcompleter.Completer.__init__(self)

    def complete(self, text, state):
        if text == '':
            return None if state > 0 else self.tab
        else:
            return rlcompleter.Completer.complete(self, text, state)


# you could change this line to bind another key instead of tab.
readline.parse_and_bind('tab: complete')
readline.set_completer(IrlCompleter().complete)

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
    inner = lambda text, bold=False: "\033[%sm%s\033[0m" % ('1;%s' % code if bold else code, text)
    return inner


# add any colors you might need.
_red   = _color_fn('31')
_green = _color_fn('32')
_cyan  = _color_fn('36')

# sys.ps1 = _green('>>> ')
# sys.ps2 = _red('... ')

# Enable Pretty Printing for stdout
# - get terminal size for passing width param to pprint. Queried just once at
# startup
_rows, _cols = subprocess.check_output(['/usr/bin/stty' ' size'], shell=True).strip().split()

def my_displayhook(value):
    if value is not None:
        try:
            import __builtin__
            __builtin__._ = value
        except ImportError:
            __builtins__._ = value

        import re
        formatted = pprint.pformat(value, width=_cols)
        if issubclass(type(value), dict):
            for k in value.keys():
                formatted = re.sub(
                        r"'(%s)': " % k,
                        lambda m: "'%s': " % _red(m.group(1), bold=True),
                        formatted)
        print formatted

sys.displayhook = my_displayhook

# Start an external editor with \e
EDITOR = os.environ.get('EDITOR', 'vi')
EDIT_CMD = '\e'

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
            lines = line.split( '\n' )
            self.write(_cyan(">>> %s\n" % '\n... '.join(lines)))
            for stmt in lines[:-1]:
                self.push(stmt)
            line = lines[-1]
        return line

    def write(self, data):
        sys.stderr.write(_red(data, bold=True))

__c = EditableBufferInteractiveConsole()

# Welcome message
WELCOME = _cyan("""\
You've got color, tab completion and pretty-printing. History will be saved
in %s when you exit.

Typing '\e' will open your $EDITOR with the last executed statement
""" % HISTFILE)

__c.interact(banner=WELCOME)

# Exit the Python shell on exiting the InteractiveConsole
sys.exit()
