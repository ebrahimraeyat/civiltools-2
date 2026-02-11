"""
ETABS COM connection — standalone replacement for find_etabs.py.

Connects to a running ETABS instance via comtypes, then wraps it
in the existing ``etabs_obj.EtabsModel`` from the etabs_api package.

The etabs_api directory is added to ``sys.path`` at connect time so all
its internal relative imports work correctly.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_ETABS_API_DEFAULT = Path(
    r"C:\Users\ebrahim\AppData\Roaming\FreeCAD\Mod\etabs_api"
)


class EtabsConnection:
    """Manages a single ETABS COM session."""

    def __init__(self, etabs_api_path: Path | str | None = None):
        self._api_path = Path(etabs_api_path) if etabs_api_path else _ETABS_API_DEFAULT
        self._etabs: Any = None        # etabs_obj.EtabsModel instance
        self._connected = False
        self._model_path: str = ""
        self._software: str = "ETABS"
        self._error: str = ""

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
            import etabs_obj  # noqa: E402  (path set above)
            etabs = etabs_obj.EtabsModel(
                attach_to_instance=True,
                backup=False,
                software=software,
            )
            if etabs.success and hasattr(etabs, "SapModel"):
                self._etabs = etabs
                self._connected = True
                try:
                    self._model_path = etabs.SapModel.GetModelFilename()
                except Exception:
                    self._model_path = ""
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

    # ------------------------------------------------------------------
    def _ensure_api_path(self):
        """Add etabs_api directory to ``sys.path`` if not already there."""
        p = str(self._api_path)
        if p not in sys.path:
            sys.path.insert(0, p)
