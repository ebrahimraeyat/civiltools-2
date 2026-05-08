"""
ETABS COM connection — standalone replacement for find_etabs.py.

Connects to a running ETABS instance via comtypes, then wraps it
in the existing ``etabs_obj.EtabsModel`` from the etabs_api package.

The etabs_api directory is added to ``sys.path`` at connect time so all
its internal relative imports work correctly.
"""

from __future__ import annotations

import site
import sys
from pathlib import Path
from typing import Any

# Software process-name mapping
_EXE_NAMES: dict[str, list[str]] = {
    "ETABS":   ["ETABS.exe"],
    "SAP2000": ["SAP2000.exe"],
    "SAFE":    ["SAFE.exe"],
}

# COM class name for each software (used by GetObjectProcess / GetObject)
_COM_CLASS: dict[str, str] = {
    "ETABS":   "CSI.ETABS.API.ETABSObject",
    "SAP2000": "CSI.SAP2000.API.SapObject",
    "SAFE":    "CSI.SAFE.API.ETABSObject",
}


def _get_etabs_api_path() -> Path:
    """Get etabs_api path from default location."""

    # Default path
    default = Path(r"G:\etabs_api\src")
    if default.exists():
        return default
    
    # Fallback for other users
    sitepackages = site.getsitepackages()
    for sp in sitepackages:
        candidate = Path(sp) / "etabs_api"
        if candidate.exists():
            return candidate
    return Path()  # Not found

class EtabsConnection:
    """Manages a single ETABS COM session."""

    def __init__(self, etabs_api_path: Path | str | None = None):
        self._api_path = Path(etabs_api_path) if etabs_api_path else _get_etabs_api_path()
        self._etabs: Any = None        # etabs_obj.EtabsModel instance
        self._connected = False
        self._model_path: str = ""
        self._software: str = "ETABS"
        self._error: str = ""
        self._version: str = ""
        self._pid: int | None = None
        self._hwnd: int = 0

    # ------------------------------------------------------------------
    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def etabs(self) -> Any:
        """The live ``EtabsModel`` object (or *None*)."""
        return self._etabs

    @property
    def model_path(self) -> str:
        return self._model_path

    @property
    def software(self) -> str:
        return self._software

    @property
    def last_error(self) -> str:
        return self._error

    # ------------------------------------------------------------------
    def connect(self, software: str = "ETABS") -> bool:
        """Attempt to attach to a running ETABS / SAFE / SAP2000 instance.

        Returns *True* on success.
        """
        self._software = software
        self._error = ""
        self._ensure_api_path()

        try:
            from etabs_api import etabs_obj  # noqa: E402  (path set above)
            etabs = etabs_obj.EtabsModel(
                attach_to_instance=True,
                backup=False,
                software=software,
            )
            if etabs.success and hasattr(etabs, "SapModel"):
                self._etabs = etabs
                self._connected = True
                self._version = ""  # reset; fetched lazily via .version
                try:
                    self._model_path = etabs.SapModel.GetModelFilename()
                except Exception:
                    self._model_path = ""
                self._remember_connected_instance()
                return True
            else:
                self._error = (
                    f"No running {software} instance found. "
                    f"Please open {software} and load a model first."
                )
                self._connected = False
                return False
        except Exception as exc:
            self._error = str(exc)
            self._connected = False
            return False

    def disconnect(self):
        self._etabs = None
        self._connected = False
        self._model_path = ""
        self._version = ""
        self._pid = None
        self._hwnd = 0

    # ------------------------------------------------------------------
    def list_instances(self, software: str = "ETABS") -> list[dict]:
        """Return all running instances of *software*.

        Each entry is a dict::

            {
                "pid":      int,          # process ID
                "hwnd":     int,          # main window handle (0 if minimised)
                "title":    str,          # window title
                "exe_path": str,          # full path to executable
                "com_class": str,         # COM class name for pid_moniker
            }
        """
        import psutil
        import win32gui
        import win32process

        exe_names = {n.lower() for n in _EXE_NAMES.get(software, [])}
        com_class = _COM_CLASS.get(software, f"CSI.{software}.API.{software}Object")

        # Collect matching PIDs → exe_path
        pid_map: dict[int, str] = {}
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                if proc.info["name"].lower() in exe_names:
                    pid_map[proc.info["pid"]] = proc.info["exe"] or ""
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Map PIDs → (hwnd, title) via EnumWindows
        pid_to_hwnd: dict[int, tuple[int, str]] = {}

        def _enum_cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in pid_map and pid not in pid_to_hwnd:
                title = win32gui.GetWindowText(hwnd)
                if title:
                    pid_to_hwnd[pid] = (hwnd, title)

        win32gui.EnumWindows(_enum_cb, None)

        results: list[dict] = []
        for pid, exe_path in pid_map.items():
            hwnd, title = pid_to_hwnd.get(pid, (0, f"{software} (PID {pid})"))
            results.append({
                "pid":       pid,
                "hwnd":      hwnd,
                "title":     title,
                "exe_path":  exe_path,
                "com_class": com_class,
            })
        return results

    def connect_pid(self, pid: int, software: str = "ETABS") -> bool:
        """Connect to a *specific* running instance identified by *pid*.

        Uses ``EtabsModel(pid_moniker=[class_name, pid])`` so the user can
        choose between multiple open instances.
        """
        self._software = software
        self._error = ""
        self._ensure_api_path()

        com_class = _COM_CLASS.get(software, f"CSI.{software}.API.{software}Object")
        try:
            from etabs_api import etabs_obj  # noqa: E402
            etabs = etabs_obj.EtabsModel(
                attach_to_instance=True,
                backup=False,
                software=software,
                pid_moniker=[com_class, pid],
            )
            if etabs.success and hasattr(etabs, "SapModel"):
                self._etabs = etabs
                self._connected = True
                self._version = ""
                self._pid = pid
                try:
                    self._model_path = etabs.SapModel.GetModelFilename()
                except Exception:
                    self._model_path = ""
                self._hwnd = self._find_window_for_pid(pid)
                return True
            else:
                self._error = f"Could not attach to {software} (PID {pid})."
                self._connected = False
                return False
        except Exception as exc:
            self._error = str(exc)
            self._connected = False
            return False

    def connect_file(self, model_path: str | Path, software: str = "ETABS") -> bool:
        """Start a new software instance and open *model_path*.

        Returns *True* on success.
        """
        self._software = software
        self._error = ""
        self._ensure_api_path()

        path = Path(model_path)
        if not path.exists() or path.suffix.lower() != ".edb":
            self._error = f"Invalid EDB file: {path}"
            self._connected = False
            return False

        try:
            from etabs_api import etabs_obj  # noqa: E402

            etabs = etabs_obj.EtabsModel(
                attach_to_instance=False,
                backup=False,
                software=software,
                model_path=str(path),
            )
            if etabs.success and hasattr(etabs, "SapModel"):
                self._etabs = etabs
                self._connected = True
                self._version = ""
                self._model_path = str(path)
                self._pid = None
                self._hwnd = 0
                self._remember_connected_instance()
                return True

            self._error = f"Could not open model file: {path}"
            self._connected = False
            return False
        except Exception as exc:
            self._error = str(exc)
            self._connected = False
            return False

    # ------------------------------------------------------------------
    def refresh(self) -> bool:
        """Lightweight poll: update model_path and detect if ETABS closed.

        Returns *True* if still connected, *False* if the session is lost.
        Does NOT try to reconnect — just probes the existing COM handle.
        """
        if not self._connected or self._etabs is None:
            return False
        try:
            self._model_path = self._etabs.SapModel.GetModelFilename()
            return True
        except Exception:
            # COM handle is dead — ETABS was closed
            self._connected = False
            self._etabs = None
            self._model_path = ""
            self._version = ""
            self._pid = None
            self._hwnd = 0
            return False

    @property
    def version(self) -> str:
        """ETABS version string (e.g. '21.2.0'), empty if not connected."""
        if not self._connected or self._etabs is None:
            return ""
        if self._version:
            return self._version
        try:
            info = self._etabs.SapModel.GetProgramInfo()
            # info → (ProgramName, Version, ComputerName, UserName, SapVersion, ProgLevel)
            self._version = str(info[1])
        except Exception:
            self._version = ""
        return self._version

    def activate_window(self) -> bool:
        """Bring the connected ETABS window to the foreground when possible."""
        if not self._connected:
            return False

        try:
            import win32con
            import win32gui
        except Exception:
            return False

        hwnd = self._hwnd
        if not hwnd and self._pid:
            hwnd = self._find_window_for_pid(self._pid)
        if not hwnd:
            self._remember_connected_instance()
            hwnd = self._hwnd
        if not hwnd:
            return False

        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(hwnd)
            self._hwnd = hwnd
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    def _ensure_api_path(self):
        """Add etabs_api directory to ``sys.path`` if not already there."""
        p = str(self._api_path)
        if p not in sys.path:
            sys.path.insert(0, p)

    def _remember_connected_instance(self):
        """Best-effort capture of the attached ETABS PID / window handle."""
        try:
            instances = self.list_instances(self._software)
        except Exception:
            return

        if self._pid:
            for inst in instances:
                if inst.get("pid") == self._pid:
                    self._hwnd = inst.get("hwnd", 0) or 0
                    return

        if len(instances) == 1:
            inst = instances[0]
            self._pid = inst.get("pid")
            self._hwnd = inst.get("hwnd", 0) or 0

    def _find_window_for_pid(self, pid: int) -> int:
        """Return the first visible top-level window for *pid*."""
        try:
            import win32gui
            import win32process
        except Exception:
            return 0

        hwnd_found = 0

        def _enum_cb(hwnd, _):
            nonlocal hwnd_found
            if hwnd_found:
                return
            if not win32gui.IsWindowVisible(hwnd):
                return
            _, hwnd_pid = win32process.GetWindowThreadProcessId(hwnd)
            if hwnd_pid == pid and win32gui.GetWindowText(hwnd):
                hwnd_found = hwnd

        try:
            win32gui.EnumWindows(_enum_cb, None)
        except Exception:
            return 0
        return hwnd_found
