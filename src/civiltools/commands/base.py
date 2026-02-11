"""
Base command class and result container.

Every structural check command inherits from ``BaseCommand`` and
implements ``execute()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandResult:
    """Data returned by a command — displayed in a table tab."""

    title: str = ""
    headers: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    summary: str = ""
    ok: bool = True
    error: str = ""
    dataframe: Any = None   # optional pd.DataFrame for model-based display

    # Optional: column format hints  ("float:2", "int", "str", "percent")
    col_formats: list[str] = field(default_factory=list)

    # Extra kwargs passed to the table model constructor
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandParam:
    """Describes one user-input parameter for a command."""

    name: str
    label: str
    param_type: str = "float"     # "float", "int", "str", "combo"
    default: Any = None
    choices: list[str] | None = None   # for 'combo' type
    tooltip: str = ""


class BaseCommand:
    """Abstract base for all structural commands."""

    command_id: str = ""
    label: str = ""
    menu_path: str = "Control"    # menu where it appears
    tooltip: str = ""
    icon: str = ""
    table_model: str = "PandasModel"    # name of model class in table_models
    dialog_class: str = ""              # e.g. "civiltools.gui.dialogs.torsion_dialog.TorsionDialog"
    requires_etabs: bool = True         # False for standalone commands (e.g. AutoCAD-only)

    @classmethod
    def parameters(cls) -> list[CommandParam]:
        """Return list of user-input parameters (empty = no dialog)."""
        return []

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        """Run the command against a live ETABS connection.

        *etabs* is an ``EtabsModel`` instance from etabs_api.
        *params* is a dict of user-supplied parameter values.
        """
        raise NotImplementedError
