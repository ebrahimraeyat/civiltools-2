"""
Application entry point — creates QApplication and launches MainWindow.

Called from __main__.py after license check passes.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication

from civiltools import __app_name__
from civiltools.config import Settings

if TYPE_CHECKING:
    from civiltools.licensing.license_manager import LicenseInfo


def run_app(license_info: LicenseInfo | None = None):
    """Create the Qt application and show the main window.

    Parameters
    ----------
    license_info : LicenseInfo, optional
        License status passed from __main__.py.
    """
    app = QApplication.instance() or QApplication(sys.argv)

    settings = Settings()
    app.setApplicationName(__app_name__)
    app.setStyle(settings.get("theme", "fusion"))

    from civiltools.gui.dialogs import report_dialog
    from civiltools.gui.main_window import MainWindow

    print(f"Loaded report dialog: {report_dialog.__file__}")
    win = MainWindow(license_info=license_info, settings=settings)
    win.show()

    sys.exit(app.exec())
