=============================
lonetwin's pimped-up pythonrc
=============================

What is this ?
==============

This is a python script intended to improve on the default Python interactive
shell experience.

Unlike ipython_, bpython_ or any of the many other options out there, this is
not designed to be used as a separate interactive environment. The intent is to
keep it as a single file and use it as any other rcfile. This script relies
solely on the standard python library and will always remain that way.

Demo
=====
|demo|

Usage
=====

The `pythonrc` file will be executed when the Python interactive shell is
started, if `$PYTHONSTARTUP` is in your environment and points to the file.

You could also simply make the file executable and call it directly.

Additionally, this file will in turn, execute a virtual env specific rc file [#]_
if it exists, for the current session, enabling you to *pre-populate* sessions
specific to virtual environments.

Features
========

The file creates an InteractiveConsole_ instance and executes it. This instance
provides:

  * execution history
  * colored prompts and pretty printing
  * auto-indentation
  * intelligent tab completion [#]_

    - without preceding text four spaces
    - with preceding text

      + names in the current namespace
      + for objects, their attributes/methods
      + for strings with a `/`, pathname completion
      + module name completion in an import statement

  * edit the session or a file in your `$EDITOR` (the ``\e`` command)

    - without no arguments, opens your `$EDITOR` with the session hstory
    - with filename argument, opens the file in your `$EDITOR`
    - with object as an argument, opens the source code for the object in `$EDITOR`

  * list the source code for objects when available (the ``\l`` command)
  * temporary escape to `$SHELL` or ability to execute a shell command and
    capturing the output in to the `_` variable (the ``!`` command)
  * convenient printing of doc stings (the ``?`` command) and search for entries in
    online docs (the ``??`` command)
  * auto-execution of a virtual env specific (`.venv_rc.py`) file at startup

If you have any other good ideas please feel free to submit pull requests or issues.
There's an section below which shows you how to add new commands.


Configuration
=============

The code attempts to be easy to read and modify to suit personal preferences.
You can change any of the `commands` or the options like the path to the history
file, its size etc in the config dict at the top of the rc file. For instance,
if you prefer to set the default edit command to `%edit` instead of the default
``\e``, you just have to change the entry in the config dict.

Note that, the `init_readline()` method also reads your `.inputrc` file if it
exists. This allows you to share the same `readline` behavior as all other tools
that use readline. For instance, in my personal `~/.inputrc` I have the
following::

    # - when performing completion in the middle of a word, do not insert characters
    # from the completion that match characters after point in the word being
    # completed
    set skip-completed-text on

    # - displays possible completions using different colors according to file type.
    set colored-stats on

    # - show completed prefix in a different color
    set colored-completion-prefix on

    # - jump temporarily to matching open parenthesis
    set blink-matching-paren on

    set expand-tilde on
    set history-size -1
    set history-preserve-point on

    "\e[A": history-search-backward
    "\e[B": history-search-forward


Adding new commands
===================

It is relatively simple to add new commands to the `ImprovedConsole` class:

1. Add the string that would invoke your new command to the `config` dict.
2. Create a method in the `ImprovedConsole` class which receives a string
   argument and returns either a string that can be evaluated as a python
   expression or `None`. The method may do anything it fancies.
3. Add an entry mapping the command to the method in the `commands` dict.

That's all !

The way commands work is, the text entered at the prompt is examined against the
`commands_re` regular expression. This regular expression is simply the grouping
of all valid commands, obtained from the keys of the `commands` dict.

If a match is found the corresponding function from the `commands` dict is
called with the rest of the text following the command provided as the argument
to the function.

You may choose to resolve this string argument to an object in the session
namespace by using the helper function `lookup()`.

Whatever text is returned by the function is then passed on for further
evaluation by the python interpreter.

Various helper functions exist like all the globally defined color functions
(initialized by the `init_colors` method), the `_doc_to_usage` decorator,
`_mktemp_buffer` and `_exec_from_file` whose intent ought to be hopefully
obvious.

Here's a complete example demonstrating the idea, by specifying a new command
``\s`` which prints the size of the specified object or of all objects in the
current namespace.

::

    config = dict(
        ...
        SIZE_OF = '\s',
    )
    ...

    class ImprovedConsole(...)
        ...

        def __init__(...):
           ...
           self.commands = {
               ...
               config['SIZE_OF']: self.print_sizeof,
               ...
           }
        ...


        @_doc_to_usage
        def print_sizeof(self, arg=''):
            """{SIZE_OF} <object>

            Print the size of specified object or of all objects in current
            namespace
            """
            if arg:
                obj = self.lookup(arg)
                if obj:
                    return print(sys.getsizeof(obj))
                else:
                    return self.print_sizeof('-h')
            print({k: sys.getsizeof(v) for k, v in self.locals.items()})


A little history
================

Ever since around 2005_, I've been obsessed with tweaking my python interactive
console to have it behave the way I prefer. Despite multiple attempts I've failed to
embrace ipython on the command line because some of ipython's approach just
don't *fit my head*. Additionally, ipython is a full environment and I just need
some conveniences added to the default environment. This is why I started
maintaining my own pythonrc. I started eventually sharing it as a gist_ back in
2014 and now about 38 revisions later, I think it might just make sense to set
it up as a project so that I can accept pull requests, bug reports or
suggestions in case somebody bothers to use it and contribute back.


Known Issue
===========

The console is *not* `__main__`. The issue was first reported by @deeenes in the
gist_ I used to maintain. In essence, this code fails::

    >>> import timeit
    >>>
    >>> def getExecutionTime():
    ...     t = timeit.Timer("sayHello()", "from __main__ import sayHello")
    ...     return t.timeit(2)
    ...
    >>> def sayHello():
    ...     print("Hello")
    ...
    >>> print(getExecutionTime())
    Traceback (most recent call last):
      File "<console>", line 1, in <module>
      File "<console>", line 3, in getExecutionTime
      File "/usr/lib64/python2.7/timeit.py", line 202, in timeit
        timing = self.inner(it, self.timer)
      File "<timeit-src>", line 3, in inner
    ImportError: cannot import name sayHello
    >>>

There are two possible workarounds for this:

* When within the console, if you have to reference local names via
  `__main__`, remember to do it via `__main__.pymp.locals` instead, something
  like (for the example above)::

      ...
      def getExecutionTime():
          t = timeit.Timer("sayHello()", "from __main__ import pymp; sayHello = pymp.locals['sayHello']")
      ...

* Or in the pythonrc file, change the initialization of `ImprovedConsole` to
  accept `locals()`. That is something like this::

      pymp = ImprovedConsole(locals=locals())

  Although the downside of this is, doing it will pollute your console
  namespace with everything in the pythonrc file.


.. [#] Named `.venv_rc.py` by default, but like almost everything else, is configurable
.. [#] Since python 3.4 the default interpreter also has tab completion enabled however it does not do pathname completion
.. _ipython: https://ipython.org/
.. _bpython: https://bpython-interpreter.org/
.. _InteractiveConsole: https://docs.python.org/3.6/library/code.html#code.InteractiveConsole
.. _2005: http://code.activestate.com/recipes/438813/
.. _gist: https://gist.github.com/lonetwin/5902720
.. |demo| image:: https://asciinema.org/a/134711.png
          :target: https://asciinema.org/a/134711?speed=2
