"""
Lightweight undo / redo framework for the axes-from-DXF workflow.

Each *Action* records how to ``redo()`` and ``undo()`` a discrete step
(e.g. "create columns", "create axes", "move origin").

``UndoStack`` keeps an ordered list.  The dialog calls
``stack.push(action)`` which automatically executes ``redo()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Action(ABC):
    """One undoable / redoable operation."""

    description: str = ""

    @abstractmethod
    def redo(self) -> None:
        """Execute (or re-execute) the operation."""

    @abstractmethod
    def undo(self) -> None:
        """Reverse the operation."""


class UndoStack:
    """Linear undo / redo stack — no branching."""

    def __init__(self) -> None:
        self._done: list[Action] = []
        self._undone: list[Action] = []

    # ── state ───────────────────────────────────────────────────────
    @property
    def can_undo(self) -> bool:
        return len(self._done) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._undone) > 0

    @property
    def undo_text(self) -> str:
        return self._done[-1].description if self._done else ""

    @property
    def redo_text(self) -> str:
        return self._undone[-1].description if self._undone else ""

    # ── operations ──────────────────────────────────────────────────
    def push(self, action: Action) -> None:
        """Execute *action* and put it on the stack, clearing the redo list."""
        action.redo()
        self._done.append(action)
        self._undone.clear()

    def undo(self) -> None:
        if not self._done:
            return
        action = self._done.pop()
        action.undo()
        self._undone.append(action)

    def redo(self) -> None:
        if not self._undone:
            return
        action = self._undone.pop()
        action.redo()
        self._done.append(action)

    def clear(self) -> None:
        self._done.clear()
        self._undone.clear()
