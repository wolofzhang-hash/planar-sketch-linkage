from __future__ import annotations

import os
import tempfile
from typing import Any


class ProjectPathService:
    """Resolve project/session directories consistently across UI tabs.

    Keeps one shared temp project dir per window for unsaved projects so that
    cases/runs are always read from the same location.
    """

    def __init__(self, ctrl: Any):
        self.ctrl = ctrl
        self._session_project_dir = ""

    def project_dir(self) -> str:
        win = getattr(self.ctrl, "win", None)
        if win is not None:
            project_dir = getattr(win, "project_dir", None)
            if project_dir:
                return project_dir
            current_file = getattr(win, "current_file", None)
            if current_file:
                return os.path.dirname(current_file)
        if win is not None:
            shared = getattr(win, "_session_project_dir", None)
            if shared:
                self._session_project_dir = shared
                return shared
        if not self._session_project_dir:
            try:
                self._session_project_dir = tempfile.mkdtemp(prefix="planar_sketch_session_")
                if win is not None:
                    setattr(win, "_session_project_dir", self._session_project_dir)
            except Exception:
                return tempfile.gettempdir()
        return self._session_project_dir
