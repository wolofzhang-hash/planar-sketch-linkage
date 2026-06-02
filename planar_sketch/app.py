# -*- coding: utf-8 -*-
"""Application entry point."""

from __future__ import annotations

import sys
from PyQt6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.i18n import set_ui_language
from .common_ui.theme import apply_theme


def main():
    app = QApplication(sys.argv)
    # Language is controlled by software settings; default to Chinese before settings load.
    set_ui_language("zh", app)
    apply_theme(app)
    w = MainWindow()
    w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
