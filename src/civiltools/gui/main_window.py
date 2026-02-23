"""
Main application window — table-centric design.

The central area is a QTabWidget where each command's result opens
as a new tab (like FreeCAD's MDI area with ResultWidget sub-windows).

The 3D viewer is NOT the central widget — it's available only for
specific commands (wall loads, axes, etc.) and opens in a dock/dialog.

Menus:
  File    — Connect to Software, Quit
  Control — Torsion, Drift, Joint Shear, Design Columns, Dynamic Scale
  Tools   — Report (future)
  Help    — Help Panel, About
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QToolBar, QMessageBox,
    QApplication, QLabel,
)

from civiltools import __version__, __app_name__
from civiltools.config import Settings
from civiltools.etabs.connection import EtabsConnection
from civiltools.commands import REGISTRY
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.gui import table_models
from civiltools.gui.result_widget import ResultWidget
from civiltools.gui.connect_dialog import ConnectDialog
from civiltools.gui.param_dialog import ParamDialog
from civiltools.gui.icons import icon, COMMAND_ICONS, APP_ICON, CONNECT_ICON, REPORT_ICON, QUIT_ICON, HELP_ICON


# Map command's table_model string → actual model class
_MODEL_MAP: dict[str, type] = {
    "PandasModel": table_models.PandasModel,
    "TorsionModel": table_models.TorsionModel,
    "DriftModel": table_models.DriftModel,
    "BaseShearModel": table_models.BaseShearModel,
    "JointShearBCCModel": table_models.JointShearBCCModel,
    "ColumnsPMMModel": table_models.ColumnsPMMModel,
    "ColumnsControlModel": table_models.ColumnsControlModel,
    "RebarModel": table_models.RebarModel,
    "RebarSummaryModel": table_models.RebarSummaryModel,
}


class MainWindow(QMainWindow):
    """civilTools main window — table-centric, like FreeCAD MDI area."""

    def __init__(self, license_info=None, settings: Settings | None = None):
        super().__init__()
        self._settings = settings or Settings()
        self._license_info = license_info
        self._conn = EtabsConnection()

        # Window title
        title = f"{__app_name__} {__version__}"
        if license_info:
            if license_info.is_licensed:
                title += " — Licensed"
            elif license_info.is_trial:
                title += f" — Trial ({license_info.days_remaining}d remaining)"
        self.setWindowTitle(title)
        self.setWindowIcon(icon(APP_ICON))
        self.resize(1200, 800)

        # ── Central widget: Tab area for results ────────────────────
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self._tabs)

        # Welcome tab
        welcome = QLabel(
            f"<h2>Welcome to {__app_name__} {__version__}</h2>"
            "<p>Connect to ETABS first, then use <b>Control</b> menu "
            "to run checks.</p>"
            "<p><b>Steps:</b></p>"
            "<ol>"
            "<li>File → Connect to Software</li>"
            "<li>Control → Torsion / Drift / Joint Shear / …</li>"
            "<li>Results appear as tabs here</li>"
            "</ol>"
        )
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.setWordWrap(True)
        welcome.setStyleSheet("padding: 40px; font-size: 14px;")
        self._tabs.addTab(welcome, "Welcome")

        # ── Help panel (right dock) — optional ──────────────────────
        try:
            from civiltools.help.help_engine import HelpEngine
            from civiltools.help.help_panel import HelpPanel

            self._help_engine = HelpEngine()
            self.help_panel = HelpPanel(
                self,
                engine=self._help_engine,
                lang=self._settings.get("language", "en"),
            )
            self.addDockWidget(
                Qt.DockWidgetArea.RightDockWidgetArea, self.help_panel
            )
            self.help_panel.hide()
        except Exception:
            self.help_panel = None

        # ── Menus & toolbar ─────────────────────────────────────────
        self._create_menus()
        self._create_toolbar()

        # Status bar with connection indicator
        self._conn_label = QLabel("  Not connected  ")
        self._conn_label.setStyleSheet(
            "color: #888; font-weight: bold; padding: 2px 8px;"
        )
        self.statusBar().addPermanentWidget(self._conn_label)
        self.statusBar().showMessage("Ready — connect to ETABS to begin")

    # ── Tab management ──────────────────────────────────────────────

    def _close_tab(self, index: int):
        widget = self._tabs.widget(index)
        self._tabs.removeTab(index)
        if widget:
            widget.deleteLater()

    def _add_result_tab(
        self, result: CommandResult, cmd_class: type[BaseCommand]
    ):
        """Create a ResultWidget tab from a CommandResult."""
        if result.error:
            QMessageBox.warning(self, result.title or "Error", result.error)
            return

        # Get the appropriate model class
        model_name = getattr(cmd_class, "table_model", "PandasModel")
        model_class = _MODEL_MAP.get(model_name, table_models.PandasModel)

        # Build DataFrame
        if result.dataframe is not None:
            df = result.dataframe
        elif result.headers and result.rows:
            df = pd.DataFrame(result.rows, columns=result.headers)
        else:
            QMessageBox.information(
                self, result.title, "No data to display."
            )
            return

        widget = ResultWidget(
            df=df,
            model_class=model_class,
            title=result.title,
            summary=result.summary,
            ok=result.ok,
            parent=self._tabs,
            kwargs=result.kwargs if result.kwargs else None,
        )

        # Set tab icon from command
        cmd_icon_name = COMMAND_ICONS.get(getattr(cmd_class, 'command_id', ''), '')
        tab_icon = icon(cmd_icon_name) if cmd_icon_name else QIcon()
        idx = self._tabs.addTab(widget, tab_icon, result.title)
        self._tabs.setCurrentIndex(idx)

    # ── ETABS connection ────────────────────────────────────────────

    def _show_connect(self):
        dlg = ConnectDialog(self._conn, self)
        dlg.exec()
        self._update_conn_status()

    def _update_conn_status(self):
        if self._conn.is_connected:
            model = (
                Path(self._conn.model_path).name
                if self._conn.model_path
                else ""
            )
            self._conn_label.setText(
                f"  {self._conn.software}: {model}  "
            )
            self._conn_label.setStyleSheet(
                "color: #006400; font-weight: bold; padding: 2px 8px;"
            )
            self.statusBar().showMessage(
                f"Connected to {self._conn.software}"
            )
        else:
            self._conn_label.setText("  Not connected  ")
            self._conn_label.setStyleSheet(
                "color: #888; font-weight: bold; padding: 2px 8px;"
            )

    # ── Command execution ───────────────────────────────────────────

    def _run_command(self, command_id: str):
        """Execute a registered command and display results."""
        cmd_class = REGISTRY.get(command_id)
        if not cmd_class:
            QMessageBox.critical(
                self, "Error", f"Unknown command: {command_id}"
            )
            return

        if getattr(cmd_class, 'requires_etabs', True) and not self._conn.is_connected:
            QMessageBox.warning(
                self,
                "Not Connected",
                "Please connect to ETABS first.\n\n"
                "File → Connect to Software",
            )
            return

        # ── Dialog-based command (loads .ui file) ───────────────────
        if cmd_class.dialog_class:
            result = self._run_dialog_command(cmd_class)
            if result is None:
                return  # user cancelled
        else:
            # ── Param-based fallback ────────────────────────────────
            cmd_params = cmd_class.parameters()
            user_params: dict[str, Any] = {}
            if cmd_params:
                dlg = ParamDialog(cmd_class.label, cmd_params, self)
                if dlg.exec() != dlg.DialogCode.Accepted:
                    return
                user_params = dlg.get_values()

            self.statusBar().showMessage(f"Running {cmd_class.label}…")
            QApplication.processEvents()

            try:
                result = cmd_class.execute(self._conn.etabs, user_params)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Command Error",
                    f"{cmd_class.label} failed:\n\n{exc}",
                )
                self.statusBar().showMessage("Command failed")
                return

        # Display result
        self._add_result_tab(result, cmd_class)
        self.statusBar().showMessage(
            f"{cmd_class.label} — {'OK' if result.ok else 'Issues found'}"
        )

    def _run_dialog_command(self, cmd_class) -> CommandResult | None:
        """Instantiate and show a .ui-based dialog, return its result."""
        import importlib

        module_path, class_name = cmd_class.dialog_class.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        dlg_cls = getattr(mod, class_name)

        dlg = dlg_cls(self._conn.etabs, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            # Some dialogs produce a secondary result (e.g. drift "Show Separate")
            result_y = getattr(dlg, "result_y", None)
            if result_y is not None:
                self._add_result_tab(result_y, cmd_class)
            return dlg.result
        return None

    # ── Menu creation ───────────────────────────────────────────────

    def _create_menus(self):
        mb = self.menuBar()

        # ── File ────────────────────────────────────────────────────
        file_menu = mb.addMenu("&File")

        act_connect = file_menu.addAction(icon(CONNECT_ICON), "&Connect to Software\u2026")
        act_connect.setShortcut("Ctrl+Shift+C")
        act_connect.triggered.connect(self._show_connect)

        file_menu.addSeparator()

        act_quit = file_menu.addAction(icon(QUIT_ICON), "&Quit")
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)

        # ── Dynamic menus from REGISTRY ─────────────────────────────
        # Menu order matches civilTools: Edit, Control, Assign, Define, Tools, Shear Wall
        menu_order = ["Edit", "Control", "Assign", "Define", "Tools", "Shear Wall"]
        menus: dict[str, Any] = {}
        for menu_name in menu_order:
            menu_cmds = [
                (cid, cls) for cid, cls in REGISTRY.items()
                if cls.menu_path == menu_name
            ]
            if not menu_cmds:
                continue
            m = mb.addMenu(f"&{menu_name}")
            menus[menu_name] = m
            for cmd_id, cmd_cls in menu_cmds:
                cmd_icon = icon(COMMAND_ICONS.get(cmd_id, ""))
                act = m.addAction(cmd_icon, cmd_cls.label)
                if cmd_cls.tooltip:
                    act.setToolTip(cmd_cls.tooltip)
                act.triggered.connect(
                    lambda checked=False, cid=cmd_id: self._run_command(cid)
                )

        # ── Tools — extra entries ───────────────────────────────────
        tools_menu = menus.get("Tools")
        if tools_menu is None:
            tools_menu = mb.addMenu("&Tools")
        tools_menu.addSeparator()
        act_report = tools_menu.addAction(icon(REPORT_ICON), "Generate &Report\u2026")
        act_report.setShortcut("Ctrl+R")
        act_report.triggered.connect(self._generate_report)

        # ── Help ────────────────────────────────────────────────────
        help_menu = mb.addMenu("&Help")
        if self.help_panel:
            act_help = help_menu.addAction(icon(HELP_ICON), "&Help Panel")
            act_help.setShortcut(QKeySequence.StandardKey.HelpContents)
            act_help.triggered.connect(lambda: self._show_help())
        help_menu.addSeparator()
        act_about = help_menu.addAction(icon(HELP_ICON), "&About")
        act_about.triggered.connect(self._show_about)

    def _create_toolbar(self):
        tb = QToolBar("Commands")
        tb.setObjectName("CommandsToolbar")
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.setIconSize(tb.iconSize() * 1.2)  # slightly larger icons

        # Connect button
        act_conn = QAction(icon(CONNECT_ICON), "Connect", self)
        act_conn.setToolTip("Connect to ETABS (Ctrl+Shift+C)")
        act_conn.triggered.connect(self._show_connect)
        tb.addAction(act_conn)
        tb.addSeparator()

        # Key command buttons (subset — full list in menus)
        toolbar_cmds = [
            "settings", "earthquake_factor", "torsion", "drift",
            "joint_shear", "design_columns", "columns_control", "dynamic_scale", "live_load"
        ]
        for cmd_id in toolbar_cmds:
            cmd_cls = REGISTRY.get(cmd_id)
            if cmd_cls is None:
                continue
            cmd_icon = icon(COMMAND_ICONS.get(cmd_id, ""))
            act = QAction(cmd_icon, cmd_cls.label, self)
            act.setToolTip(cmd_cls.tooltip or cmd_cls.label)
            act.triggered.connect(
                lambda checked=False, cid=cmd_id: self._run_command(cid)
            )
            tb.addAction(act)

    # ── Report ──────────────────────────────────────────────────────

    def _generate_report(self):
        if not self._conn.is_connected:
            QMessageBox.warning(
                self,
                "Not Connected",
                "Please connect to ETABS first.\n\n"
                "File → Connect to Software",
            )
            return

        from civiltools.gui.dialogs.report_dialog import ReportDialog

        dlg = ReportDialog(self._conn.etabs, parent=self)
        dlg.exec()

    # ── Help ────────────────────────────────────────────────────────

    def _show_help(self, context: str = ""):
        if self.help_panel:
            if context:
                self.help_panel.show_context(context)
            else:
                self.help_panel.show()
                self.help_panel.raise_()

    def _show_about(self):
        n_cmds = len(REGISTRY)
        QMessageBox.information(
            self,
            "About",
            f"<h3>{__app_name__} {__version__}</h3>"
            "<p>Standalone structural engineering application.</p>"
            f"<p><b>{n_cmds} commands</b> across 6 menus:</p>"
            "<ul>"
            "<li><b>Edit:</b> Project Settings, Frame Sections</li>"
            "<li><b>Control:</b> Torsion, Drift, Joint Shear, Columns, "
            "Deflection, Weakness, Stiffness, Story Forces, Diaphragm</li>"
            "<li><b>Assign:</b> Earthquake Factor, Beam J, Modifiers, Ev, Wall Load</li>"
            "<li><b>Define:</b> Load Combinations, Spectrum, Section Cuts, Explode Seismic</li>"
            "<li><b>Tools:</b> Match Property, Offset, Report</li>"
            "<li><b>Shear Wall:</b> 25% Stiffness File</li>"
            "</ul>"
            "<p><b>Stack:</b> Python 3.12+ · PySide6 (Qt 6) · etabs_api</p>"
            "<p>Standalone replacement for the FreeCAD-based civilTools "
            "workbench.</p>",
        )
