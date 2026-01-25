# -*- coding: utf-8 -*-
"""Qt event safety helpers.

In some environments, an uncaught exception inside a Qt event handler can terminate the app.
This decorator prints the traceback and keeps the app alive.
"""

from __future__ import annotations

import traceback
from typing import Callable, TypeVar, Any

T = TypeVar("T")


def safe_event(fn: Callable[..., T]) -> Callable[..., T | None]:
    """Decorator for Qt event handlers."""

    def wrapper(self: Any, e: Any) -> T | None:
        try:
            return fn(self, e)
        except Exception:
            traceback.print_exc()
            try:
                e.ignore()
            except Exception:
                pass
            return None

    return wrapper
