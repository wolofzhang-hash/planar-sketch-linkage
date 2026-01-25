# -*- coding: utf-8 -*-
"""Undo/Redo command stack.

This codebase supports two ways to define a command:

1) **Subclass style** (legacy, used throughout controller.py)::

       class MyCmd(Command):
           name = "Do thing"
           def do(self): ...
           def undo(self): ...

2) **Callable style** (lightweight)::

       Command(do=lambda: ..., undo=lambda: ..., desc="Do thing")

Both styles share the same interface: ``do()`` and ``undo()`` methods and a
human readable description (``desc`` or ``name``).
"""

from __future__ import annotations

from typing import Callable, Optional


class Command:
    """A reversible action.

    - If constructed with callables, ``do()`` / ``undo()`` will call them.
    - If subclassed, override ``do()`` / ``undo()``.
    """

    def __init__(
        self,
        do: Optional[Callable[[], None]] = None,
        undo: Optional[Callable[[], None]] = None,
        desc: str = "",
    ):
        self._do_cb = do
        self._undo_cb = undo
        self.desc = desc or getattr(self, "name", "")

    def do(self):
        if self._do_cb is None:
            raise NotImplementedError("Command.do() not implemented")
        self._do_cb()

    def undo(self):
        if self._undo_cb is None:
            raise NotImplementedError("Command.undo() not implemented")
        self._undo_cb()


class CommandStack:
    def __init__(self, on_change: Optional[Callable[[], None]] = None):
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._on_change = on_change

    def clear(self):
        self._undo.clear()
        self._redo.clear()
        self._changed()

    def _changed(self):
        if self._on_change:
            self._on_change()

    def push(self, cmd: Command, execute: bool = True):
        if execute:
            cmd.do()
        self._undo.append(cmd)
        self._redo.clear()
        self._changed()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self):
        if not self._undo:
            return
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        self._changed()

    def redo(self):
        if not self._redo:
            return
        cmd = self._redo.pop()
        cmd.do()
        self._undo.append(cmd)
        self._changed()

    def undo_text(self) -> str:
        if not self._undo:
            return ""
        cmd = self._undo[-1]
        return getattr(cmd, "desc", "") or getattr(cmd, "name", "")

    def redo_text(self) -> str:
        if not self._redo:
            return ""
        cmd = self._redo[-1]
        return getattr(cmd, "desc", "") or getattr(cmd, "name", "")
