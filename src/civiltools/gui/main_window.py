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
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QToolBar, QMessageBox,
    QApplication, QLabel, QDockWidget, QInputDialog,
)
from civiltools.gui.toggle_button import Switch

_DARK_STYLESHEET = """
QMainWindow, QDialog, QWidget {
    background: #202124;
    color: #e8eaed;
}
QMenuBar {
    background: #2b2d31;
    color: #e8eaed;
}
QMenuBar::item:selected {
    background: #3c4043;
}
QMenu {
    background: #2b2d31;
    color: #e8eaed;
    border: 1px solid #3c4043;
}
QMenu::item:selected {
    background: #1e88e5;
}
QToolBar {
    background: #2b2d31;
    border-bottom: 1px solid #3c4043;
}
QStatusBar {
    background: #2b2d31;
    color: #e8eaed;
}
QTabWidget::pane {
    border: 1px solid #3c4043;
    background: #202124;
}
QTabBar::tab {
    background: #2b2d31;
    color: #e8eaed;
    padding: 6px 12px;
    border: 1px solid #3c4043;
}
QTabBar::tab:selected {
    background: #1e88e5;
    color: white;
}
QGroupBox, QTreeWidget, QTableWidget, QTextEdit, QScrollArea, QListWidget {
    background: #2b2d31;
    color: #e8eaed;
}
QHeaderView::section {
    background: #3c4043;
    color: white;
}
QPushButton {
    background: #3c4043;
    color: white;
    padding: 6px 10px;
    border-radius: 4px;
    border: none;
}
QPushButton:hover {
    background: #4e5358;
}
QPushButton:disabled {
    background: #2b2d31;
    color: #666;
}
QComboBox {
    background: #3c4043;
    color: #e8eaed;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 3px 6px;
}
QComboBox QAbstractItemView {
    background: #2b2d31;
    color: #e8eaed;
    selection-background-color: #1e88e5;
}
QLineEdit, QSpinBox, QDoubleSpinBox {
    background: #3c4043;
    color: #e8eaed;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 3px;
}
QCheckBox, QRadioButton {
    color: #e8eaed;
    padding: 3px;
}
QProgressBar {
    border: 1px solid #555;
    border-radius: 4px;
    text-align: center;
    color: white;
}
QProgressBar::chunk {
    background: #1e88e5;
}
QDockWidget {
    color: #e8eaed;
}
QDockWidget::title {
    background: #2b2d31;
}
QSplitter::handle {
    background: #3c4043;
}
"""

from civiltools import __version__, __app_name__
from civiltools.config import Settings
from civiltools.etabs.connection import EtabsConnection
from civiltools.commands import REGISTRY
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.gui import table_models
from civiltools.gui import delegates
from civiltools.gui.result_widget import ResultWidget
from civiltools.gui.result_persistence import persist_result_table
from civiltools.gui.connect_dialog import ConnectDialog
from civiltools.gui.param_dialog import ParamDialog
from civiltools.gui.icons import icon, COMMAND_ICONS, APP_ICON, CONNECT_ICON, REPORT_ICON, QUIT_ICON, HELP_ICON
from civiltools.gui.busy_dialog import BusyDialog
from civiltools.gui.log_widget import LogWidget, app_log


# Map command's table_model string → actual model class
_MODEL_MAP: dict[str, type] = {
    "PandasModel": table_models.PandasModel,
    "TorsionModel": table_models.TorsionModel,
    "IrregularityOfMassModel": table_models.IrregularityOfMassModel,
    "StoryStiffnessModel": table_models.StoryStiffnessModel,
    "DriftModel": table_models.DriftModel,
    "BaseShearModel": table_models.BaseShearModel,
    "JointShearBCCModel": table_models.JointShearBCCModel,
    "ColumnsPMMModel": table_models.ColumnsPMMModel,
    "ColumnsControlModel": table_models.ColumnsControlModel,
    "RebarModel": table_models.RebarModel,
    "RebarSummaryModel": table_models.RebarSummaryModel,
}

_DELEGATE_MAP: dict[str, type] = {
    "ColumnsControlModel": delegates.ColumnsControlDelegate,
}

_LEGEND_MAP: dict[str, list[tuple[str, str]]] = {
    "ColumnsControlModel": table_models.COLUMNS_CONTROL_LEGEND,
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

        # ── Log panel (bottom dock) ─────────────────────────────────
        self._log_widget = LogWidget(settings=self._settings, parent=self)
        log_dock = QDockWidget("Log", self)
        log_dock.setObjectName("LogDock")
        log_dock.setWidget(self._log_widget)
        log_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, log_dock)
        app_log.attach(self._log_widget)
        app_log.info(f"{__app_name__} {__version__} started")

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

        # ── Dark/Light theme toggle in status bar ───────────────────
        _theme_label = QLabel("  ☀  ")
        _theme_label.setToolTip("Light / Dark theme")
        self._theme_switch = Switch(track_radius=9, thumb_radius=7)
        self._theme_switch.setChecked(self._settings.get("dark_theme", False))
        self._theme_switch.setToolTip("Toggle dark / light theme")
        self._theme_switch.toggled.connect(self._apply_theme)
        _dark_label = QLabel("  🌙  ")
        self.statusBar().addPermanentWidget(_theme_label)
        self.statusBar().addPermanentWidget(self._theme_switch)
        self.statusBar().addPermanentWidget(_dark_label)
        # Apply saved theme on start
        self._apply_theme(self._settings.get("dark_theme", False))

        # Add Tools → Settings: Webhook URL entry
        # (handled via existing settings dialog or inline in Help > About)

        # ── 10-second polling timer ────────────────────────────────
        # FreeCAD had no background COM poll. Pause it for tabs that call
        # ETABS on every click (Columns Control) to avoid UI freezes.
        self._poll_busy: bool = False
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(10_000)
        self._poll_timer.timeout.connect(self._poll_etabs_status)
        self._poll_timer.start()
        self._tabs.currentChanged.connect(self._sync_poll_with_current_tab)

    # ── Tab management ──────────────────────────────────────────────

    def _close_tab(self, index: int):
        widget = self._tabs.widget(index)
        self._tabs.removeTab(index)
        if widget:
            widget.deleteLater()
        self._sync_poll_with_current_tab(self._tabs.currentIndex())

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
        delegate_class = _DELEGATE_MAP.get(model_name)
        legend_items = _LEGEND_MAP.get(model_name)
        cell_selected = None
        pause_poll = False
        if model_name == "ColumnsControlModel":
            # FreeCAD ControlColumnResultWidget.row_clicked → etabs.view.show_frame
            cell_selected = self._columns_control_selection_handler(result.kwargs)
            pause_poll = True

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
            delegate_class=delegate_class,
            legend_items=legend_items,
            sortable=model_name != "ColumnsControlModel",
            cell_selected=cell_selected,
            title=result.title,
            summary=result.summary,
            ok=result.ok,
            parent=self._tabs,
            kwargs=result.kwargs if result.kwargs else None,
        )
        widget._pause_etabs_poll = pause_poll  # type: ignore[attr-defined]

        # Set tab icon from command
        cmd_icon_name = COMMAND_ICONS.get(getattr(cmd_class, 'command_id', ''), '')
        tab_icon = icon(cmd_icon_name) if cmd_icon_name else QIcon()
        idx = self._tabs.addTab(widget, tab_icon, result.title)
        self._tabs.setCurrentIndex(idx)
        self._sync_poll_with_current_tab(idx)
        self._persist_result_table(widget, result, cmd_class)

    def _persist_result_table(
        self,
        widget: ResultWidget,
        result: CommandResult,
        cmd_class: type[BaseCommand],
    ) -> None:
        """Persist eligible ETABS result tabs without affecting the UI flow."""
        if (
            not getattr(cmd_class, "requires_etabs", True)
            or not self._conn.is_connected
            or not self._conn.model_path
            or not getattr(cmd_class, "command_id", "")
        ):
            return
        try:
            persist_result_table(
                widget._model,
                self._conn.model_path,
                cmd_class.command_id,
                result.title or cmd_class.label,
                result.params,
            )
        except Exception as exc:
            app_log.warning(f"Could not cache {cmd_class.label} results: {exc}")

    def _sync_poll_with_current_tab(self, index: int) -> None:
        """Stop background COM polling while Columns Control is active."""
        widget = self._tabs.widget(index) if index >= 0 else None
        pause = bool(getattr(widget, "_pause_etabs_poll", False))
        if pause:
            self._poll_timer.stop()
            self._poll_busy = False
        elif self._conn.is_connected and not self._poll_timer.isActive():
            self._poll_timer.start()

    def _columns_control_selection_handler(self, kwargs: dict):
        """Select the clicked frame in ETABS (no RefreshView — that freezes UI)."""
        etabs = kwargs.get("etabs")
        names_df = kwargs.get("columns_type_names_df")
        if etabs is None or names_df is None:
            return None

        last_name: list[str | None] = [None]

        def show_frame(row: int, col: int):
            try:
                frame_name = names_df.iat[row, col]
            except Exception:
                return
            if pd.isna(frame_name) or frame_name == "":
                return
            name = str(frame_name)
            if last_name[0] == name:
                return
            last_name[0] = name
            # Keep COM on the UI/STA thread. Skip RefreshView — it is the main
            # freeze source when ETABS is busy; SetSelected still highlights.
            try:
                sap = etabs.SapModel
                sap.SelectObj.ClearSelection()
                sap.FrameObj.SetSelected(name, True)
            except Exception:
                pass

        return show_frame

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
            ver = self._conn.version
            ver_str = f" v{ver}" if ver else ""
            self._conn_label.setText(
                f"  {self._conn.software}{ver_str}: {model}  "
            )
            self._conn_label.setStyleSheet(
                "color: #006400; font-weight: bold; padding: 2px 8px;"
            )
            self.statusBar().showMessage(
                f"Connected to {self._conn.software}{ver_str} — {model}"
            )
            app_log.info(f"Connected to {self._conn.software}{ver_str}: {model}")
        else:
            self._conn_label.setText("  Not connected  ")
            self._conn_label.setStyleSheet(
                "color: #888; font-weight: bold; padding: 2px 8px;"
            )

    # ── Polling ───────────────────────────────────────────────

    def _poll_etabs_status(self):
        """Called every 10 s by QTimer. Probes ETABS COM without blocking UI."""
        if self._poll_busy:
            return
        self._poll_busy = True
        try:
            if not self._conn.is_connected:
                # Not connected — try a silent auto-connect
                ok = self._conn.connect("ETABS")
                if ok:
                    self._update_conn_status()
                return
            # Already connected — refresh model path and detect if ETABS closed
            prev_path = self._conn.model_path
            still_alive = self._conn.refresh()
            if not still_alive:
                self._update_conn_status()
                self.statusBar().showMessage(
                    "ETABS connection lost — File → Connect to Software to reconnect"
                )
                app_log.warning("ETABS connection lost")
                return
            # Update status bar only when something changed
            if self._conn.model_path != prev_path:
                self._update_conn_status()
        finally:
            self._poll_busy = False

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
            # Try a silent auto-connect before asking the user to connect manually
            if self._conn.connect("ETABS"):
                self._update_conn_status()

        if getattr(cmd_class, 'requires_etabs', True) and not self._conn.is_connected:
            QMessageBox.warning(
                self,
                "Not Connected",
                "Could not connect to ETABS automatically.\n\n"
                "Please open ETABS with a model loaded, then use\n"
                "File → Connect to Software.",
            )
            return

        # ── Dialog-based command (loads .ui file) ───────────────────
        self._poll_busy = True   # prevent COM re-entrancy from the 10s timer
        try:
            if cmd_class.dialog_class:
                with app_log.capture_output(cmd_class.label):
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
                app_log.info(f"Running: {cmd_class.label}")

                try:
                    with BusyDialog(cmd_class.label, parent=self) as dlg:
                        with app_log.capture_output(cmd_class.label):
                            result = dlg.run(lambda: cmd_class.execute(self._conn.etabs, user_params))
                except Exception as exc:
                    app_log.error(f"{cmd_class.label} failed: {exc}")
                    QMessageBox.critical(
                        self,
                        "Command Error",
                        f"{cmd_class.label} failed:\n\n{exc}",
                    )
                    self.statusBar().showMessage("Command failed")
                    return
                result.params = user_params
        finally:
            self._poll_busy = False

        # Display result
        self._add_result_tab(result, cmd_class)
        self.statusBar().showMessage(
            f"{cmd_class.label} — {'OK' if result.ok else 'Issues found'}"
        )
        if result.ok:
            app_log.info(f"{cmd_class.label} — completed OK")
        else:
            app_log.warning(
                f"{cmd_class.label} — completed with issues: "
                + (result.summary or result.error or "see results tab")
            )

    def _run_dialog_command(self, cmd_class) -> CommandResult | None:
        """Instantiate and show a .ui-based dialog, return its result."""
        import importlib

        module_path, class_name = cmd_class.dialog_class.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        dlg_cls = getattr(mod, class_name)

        dlg = dlg_cls(self._conn.etabs, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self.showNormal()
            self.raise_()
            self.activateWindow()

            # Some dialogs produce a secondary result (e.g. drift "Show Separate")
            result_y = getattr(dlg, "result_y", None)
            if result_y is not None:
                result_y.params = getattr(dlg, "report_params", {})
                self._add_result_tab(result_y, cmd_class)

            result = dlg.result
            if result is not None:
                result.params = getattr(dlg, "report_params", {})
            if result is None and self._tabs.count():
                self._tabs.setCurrentIndex(0)

            if getattr(dlg, "bring_etabs_to_front_after_accept", False):
                self._conn.activate_window()

            return result
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
        menu_order = ["Edit", "Control", "Assign", "Define", "Tools", "Shear Wall", "Wind"]
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

        tools_menu.addSeparator()
        act_webhook = tools_menu.addAction("\U0001f517  Configure &Webhook URL\u2026")
        act_webhook.setToolTip(
            "Set a Telegram or Discord webhook URL for sending logs.\n"
            "Leave blank to use the default e-mail method."
        )
        act_webhook.triggered.connect(self._configure_webhook)

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
            "joint_shear", "design_columns", "columns_control", "dynamic_scale", "live_load",
            "controls_input",
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
    # ── Webhook configuration ─────────────────────────────────────

    def _configure_webhook(self):
        """
        Let the user enter a Telegram or Discord webhook URL.
        Stored in Settings under the key ``webhook_url``.
        Examples
        --------
        Telegram : https://api.telegram.org/bot<TOKEN>/sendDocument?chat_id=<ID>
        Discord  : https://discord.com/api/webhooks/<id>/<token>
        """
        current = self._settings.get("webhook_url", "")
        text, ok = QInputDialog.getText(
            self,
            "Configure Webhook URL",
            "Enter Telegram or Discord webhook URL\n"
            "(leave blank to use the default e-mail action):",
            text=current,
        )
        if not ok:
            return
        self._settings.set("webhook_url", text.strip())
        if text.strip():
            app_log.info(f"Webhook URL configured: {text.strip()[:40]}…")
        else:
            app_log.info("Webhook URL cleared — will use e-mail for log sending")
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

    # ── Theme ───────────────────────────────────────────────────────

    def _apply_theme(self, dark: bool) -> None:
        app = QApplication.instance()
        if dark:
            app.setStyleSheet(_DARK_STYLESHEET)
        else:
            app.setStyleSheet("")
        self._settings.set("dark_theme", dark)

    def closeEvent(self, event):  # noqa: N802
        self._poll_timer.stop()
        super().closeEvent(event)
