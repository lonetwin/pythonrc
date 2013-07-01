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
def _wrap_with(code):
    def inner(text, bold=False):
        c = code
        if bold:
            c = "1;%s" % c
        return "\033[%sm%s\033[0m" % (c, text)
    return inner

# add any colors you might need.
_red   = _wrap_with('31')
_green = _wrap_with('32')
_cyan  = _wrap_with('36')

sys.ps1 = _green('>>> ')
sys.ps2 = _red('... ')

# Enable Pretty Printing for stdout
def my_displayhook(value):
    if value is not None:
        try:
            import __builtin__
            __builtin__._ = value
        except ImportError:
            __builtins__._ = value

        pprint.pprint(value)
sys.displayhook = my_displayhook


# Start an external editor with \e
EDITOR = os.environ.get('EDITOR', 'vi')
EDIT_CMD = '\e'

class EditableBufferInteractiveConsole(InteractiveConsole, object):
    def __init__(self, *args, **kwargs):
        super(EditableBufferInteractiveConsole, self).__init__(*args, **kwargs)
        self.last_buffer = [] # This holds the last executed statement

    def runsource(self, source, *args):
        if source.strip():
            self.last_buffer = [ source.encode('utf-8') ]
        return super(EditableBufferInteractiveConsole, self).runsource(source, *args)

    def raw_input(self, *args):
        line = super(EditableBufferInteractiveConsole, self).raw_input(*args)
        if line == EDIT_CMD:
            fd, tmpfl = mkstemp('.py')
            os.write(fd, b'\n'.join(self.last_buffer))
            os.close(fd)
            os.system('%s %s' % (EDITOR, tmpfl))
            line = open(tmpfl).read()
            os.unlink(tmpfl)
            tmpfl = ''
            lines = line.split( '\n' )
            for stmt in lines[:-1]:
                self.push(stmt)
            line = lines[-1]
            self.write(_cyan(">>> %s\n" % '\n... '.join(lines)))
        return line

__c = EditableBufferInteractiveConsole(locals=locals())

# Welcome message
WELCOME = _cyan("""\
You've got color, tab completion and pretty-printing. History will be saved
in %s when you exit.

Typing '\e' will open your $EDITOR with the last executed statement
""" % HISTFILE)

__c.interact(banner=WELCOME)

# Exit the Python shell on exiting the InteractiveConsole
sys.exit()
