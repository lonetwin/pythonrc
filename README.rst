=============================
lonetwin's pimped-up pythonrc
=============================

What is this ?
==============

This is a python script intended to improve on the default Python interactive
shell experience. Unlike, ipython_, bpython_ or any of the many other options
out there, this is not intended to be used as a module. The intent is to keep it
as a single file and use it as any other rcfile.

Usage
=====

The ``pythonrc`` file will be executed when the Python interactive shell is
started, if ``$PYTHONSTARTUP`` is in your environment and points to the file.

You could also simply make the file executable and call it directly.

Features
========

The file creates an InteractiveConsole_ instance and executes it. This instance
provides:
  * colored prompts and pretty printing
  * intelligent tab completion [1]_ :
    - with preceding text
        + names in the current namespace
        + for objects, their attributes/methods
        + for strings with a ``/``, pathname completion
        + module name completion in an import statement
    - without preceding text four spaces
  * shortcut to open your ``$EDITOR`` with the last executed command (the ``\e``
    command)
  * temporary escape to ``$SHELL`` or ability to execute a shell command and
    capturing the output in to the ``_`` variable (the ``!`` command)
  * execution history
  * convenient printing of doc stings (the ``?`` command)

If you have any other good ideas please feel free to submit pull requests or
issues.


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


.. [1] Since python 3.4 the default interpreter also has tab completion enabled however it does not do pathname completion
.. _ipython: https://ipython.org/
.. _bpython: https://bpython-interpreter.org/
.. _InteractiveConsole: https://docs.python.org/3.6/library/code.html#code.InteractiveConsole
.. _2005: http://code.activestate.com/recipes/438813/
.. _gist: https://gist.github.com/lonetwin/5902720

