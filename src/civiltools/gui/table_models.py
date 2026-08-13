"""
Pandas-backed table models — ported from civilTools/table_model.py for PySide6.

Each model wraps a pandas DataFrame and provides custom coloring
for pass/fail thresholds, exactly as in the original FreeCAD workbench.
"""

from __future__ import annotations

import json
import random
import colorsys
from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QColor, QFont


# ── Color defaults (RGB tuples, matching FreeCAD civilTools) ─────────
LOW = (0, 255, 255)             # cyan   — OK / pass
INTERMEDIATE = (255, 255, 127)  # yellow — warning / intermediate
HIGH = (255, 85, 127)           # red-pink — fail / exceed


# =====================================================================
#  Base Model
# =====================================================================

class PandasModel(QAbstractTableModel):
    """Base QAbstractTableModel backed by a ``pandas.DataFrame``."""

    def __init__(self, df: pd.DataFrame, kwargs: dict | None = None):
        super().__init__()
        self.df = df
        self.kwargs = kwargs or {}

    def rowCount(self, parent=None):
        return self.df.shape[0]

    def columnCount(self, parent=None):
        return self.df.shape[1]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self.df.columns[section])
        return section + 1

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        value = self.df.iat[index.row(), index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        return None


# =====================================================================
#  Torsion Model
# =====================================================================

class TorsionModel(PandasModel):
    """Torsion irregularity — ratio coloring: ≤1.2=OK, 1.2–1.4=warn, >1.4=fail."""

    HEADERS = ['Story', 'Label', 'OutputCase', 'Max Drift', 'Avg Drift', 'Ratio']

    def __init__(self, df: pd.DataFrame, kwargs=None):
        # Keep only relevant columns if they exist
        cols = [c for c in self.HEADERS if c in df.columns]
        super().__init__(df[cols].copy(), kwargs)
        self.i_ratio = list(self.df.columns).index('Ratio') if 'Ratio' in self.df.columns else -1
        self.i_max = list(self.df.columns).index('Max Drift') if 'Max Drift' in self.df.columns else -1
        self.i_avg = list(self.df.columns).index('Avg Drift') if 'Avg Drift' in self.df.columns else -1

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            if self.data(index, Qt.ItemDataRole.BackgroundRole) is not None:
                return QColor(0, 0, 0)
            return None
        row, col = index.row(), index.column()
        value = self.df.iat[row, col]

        if role == Qt.ItemDataRole.DisplayRole:
            if col in (self.i_max, self.i_avg, self.i_ratio):
                try:
                    return f"{float(value):.4f}"
                except (ValueError, TypeError):
                    pass
            return str(value)

        if role == Qt.ItemDataRole.BackgroundRole and self.i_ratio >= 0:
            try:
                ratio = float(self.df.iat[row, self.i_ratio])
            except (ValueError, TypeError):
                return None
            if ratio <= 1.2:
                return QColor(*LOW)
            elif ratio < 1.4:
                return QColor(*INTERMEDIATE)
            else:
                return QColor(*HIGH)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        return None


# =====================================================================
#  Mass Irregularity Model
# =====================================================================

class IrregularityOfMassModel(PandasModel):
    """Vertical mass irregularity — story mass > 1.5× adjacent story = fail."""

    HEADERS = ['Story', 'Mass (tonf)', '1.5 * Below', '1.5 * Above']

    def __init__(self, df: pd.DataFrame, kwargs=None):
        cols = [c for c in self.HEADERS if c in df.columns]
        super().__init__(df[cols].copy() if cols else df.copy(), kwargs)
        headers = list(self.df.columns)
        self.i_story = headers.index('Story') if 'Story' in headers else -1
        self.i_mass = headers.index('Mass (tonf)') if 'Mass (tonf)' in headers else -1
        self.i_below = headers.index('1.5 * Below') if '1.5 * Below' in headers else -1
        self.i_above = headers.index('1.5 * Above') if '1.5 * Above' in headers else -1

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            if self.data(index, Qt.ItemDataRole.BackgroundRole) is not None:
                return QColor(0, 0, 0)
            return None
        row, col = index.row(), index.column()
        value = self.df.iat[row, col]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.i_story:
                return str(value)
            try:
                return f"{float(value):.2f}"
            except (ValueError, TypeError):
                return str(value)

        if role == Qt.ItemDataRole.BackgroundRole and self.i_mass >= 0:
            if col in (self.i_below, self.i_above):
                try:
                    mass = float(self.df.iat[row, self.i_mass])
                    limit = float(self.df.iat[row, col])
                except (ValueError, TypeError):
                    return None
                return QColor(*HIGH) if mass > limit else QColor(*LOW)
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        return None


# =====================================================================
#  Drift Model
# =====================================================================

class DriftModel(PandasModel):
    """Drift check — color-code rows where drift exceeds allowable."""

    def __init__(self, df: pd.DataFrame, kwargs=None):
        cols = ['Story', 'OutputCase', 'Max Drift', 'Avg Drift', 'Allowable Drift']
        available = [c for c in cols if c in df.columns]
        super().__init__(df[available].copy(), kwargs)
        for c in ('Max Drift', 'Avg Drift', 'Allowable Drift'):
            if c in self.df.columns:
                self.df[c] = pd.to_numeric(self.df[c], errors='coerce')
        self.i_max = list(self.df.columns).index('Max Drift') if 'Max Drift' in self.df.columns else -1
        self.i_avg = list(self.df.columns).index('Avg Drift') if 'Avg Drift' in self.df.columns else -1
        self.i_allow = list(self.df.columns).index('Allowable Drift') if 'Allowable Drift' in self.df.columns else -1

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            if self.data(index, Qt.ItemDataRole.BackgroundRole) is not None:
                return QColor(0, 0, 0)
            return None
        row, col = index.row(), index.column()
        value = self.df.iat[row, col]

        if role == Qt.ItemDataRole.DisplayRole:
            if col in (self.i_max, self.i_avg, self.i_allow):
                try:
                    return f"{float(value):.4f}"
                except (ValueError, TypeError):
                    pass
            return str(value)

        if role == Qt.ItemDataRole.BackgroundRole:
            if col in (self.i_max, self.i_avg) and self.i_allow >= 0:
                try:
                    allow = float(self.df.iat[row, self.i_allow])
                    val = float(value)
                except (ValueError, TypeError):
                    return None
                if val > allow:
                    return QColor(*HIGH)
                return QColor(*LOW)
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        return None


# =====================================================================
#  Base Shear (Dynamic Scale) Model
# =====================================================================

class BaseShearModel(PandasModel):
    """Response spectrum scale factors — Case, V, Ratio, Scale."""

    def __init__(self, df: pd.DataFrame, kwargs=None):
        super().__init__(df.copy(), kwargs)
        cols = list(self.df.columns)
        self.i_ratio = cols.index('Ratio') if 'Ratio' in cols else -1
        self.i_scale = cols.index('Scale') if 'Scale' in cols else -1

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            if self.data(index, Qt.ItemDataRole.BackgroundRole) is not None:
                return QColor(0, 0, 0)
            return None
        row, col = index.row(), index.column()
        value = self.df.iat[row, col]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(value)
            if col in (self.i_ratio, self.i_scale):
                try:
                    return f"{float(value):.2f}"
                except (ValueError, TypeError):
                    return str(value)
            try:
                return f"{float(value):.0f}"
            except (ValueError, TypeError):
                return str(value)

        if role == Qt.ItemDataRole.BackgroundRole:
            return QColor(*LOW)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        return None


# =====================================================================
#  Joint Shear / BCC Model
# =====================================================================

class JointShearBCCModel(PandasModel):
    """Joint shear and beam-column capacity — ratio ≤1 = OK, >1 = fail."""

    def __init__(self, df: pd.DataFrame, kwargs=None):
        super().__init__(df.copy(), kwargs)
        cols = list(self.df.columns)
        self.ratio_cols = set()
        for name in (
            'JSMajRatio', 'JSMinRatio', 'BCMajRatio', 'BCMinRatio',
            'Ratio', 'Ratio_JS (ETABS)', 'Ratio_BC (ETABS)',
        ):
            if name in cols:
                self.ratio_cols.add(cols.index(name))

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            if self.data(index, Qt.ItemDataRole.BackgroundRole) is not None:
                return QColor(0, 0, 0)
            return None
        row, col = index.row(), index.column()
        value = self.df.iat[row, col]

        if role == Qt.ItemDataRole.DisplayRole:
            if col in self.ratio_cols:
                try:
                    return f"{float(value):.2f}"
                except (ValueError, TypeError):
                    return str(value)
            return str(value)

        if role == Qt.ItemDataRole.BackgroundRole:
            if col in self.ratio_cols:
                try:
                    v = float(value)
                    return QColor(*LOW) if v <= 1.0 else QColor(*HIGH)
                except (ValueError, TypeError):
                    return QColor(*INTERMEDIATE)
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        return None


# =====================================================================
#  Columns PMM Ratio Model
# =====================================================================

class ColumnsPMMModel(PandasModel):
    """Column P-M-M ratios — >1 = fail (red), ≤1 = OK (white)."""

    def __init__(self, df: pd.DataFrame, kwargs=None):
        super().__init__(df.copy(), kwargs)
        cols = list(self.df.columns)
        self.i_ratio = cols.index('PMMRatio') if 'PMMRatio' in cols else -1

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            if self.data(index, Qt.ItemDataRole.BackgroundRole) is not None:
                return QColor(0, 0, 0)
            return None
        row, col = index.row(), index.column()
        value = self.df.iat[row, col]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.i_ratio:
                try:
                    return f"{float(value):.3f}"
                except (ValueError, TypeError):
                    return str(value)
            return str(value)

        if role == Qt.ItemDataRole.BackgroundRole and self.i_ratio >= 0:
            try:
                ratio = float(self.df.iat[row, self.i_ratio])
                if ratio > 1.0:
                    return QColor(*HIGH)
                return QColor(*LOW)
            except (ValueError, TypeError):
                return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        return None


# =====================================================================
#  Columns Control Model (adjacent-story comparison)
# =====================================================================

# Color mapping matching civilTools CompareTwoColumnsColorEnum
_COLUMNS_CONTROL_COLORS: dict[str, str] = {
    'section_area': 'red',
    'corner_rebar_size': 'seagreen',
    'longitudinal_rebar_size': 'greenyellow',
    'total_rebar_area': 'green',
    'local_axes': 'magenta',
    'section_dimension': 'firebrick',
    'rebar_number': 'springgreen',
    'rebar_slop': 'yellow',
    'OK': 'lightskyblue',
    'material': 'gray',
    'not_checked': 'white',
}

_COLUMNS_CONTROL_LABELS: dict[str, str] = {
    'section_area': 'Section area',
    'corner_rebar_size': 'Corner bar size',
    'longitudinal_rebar_size': 'Longitudinal bar size',
    'total_rebar_area': 'Total rebar area',
    'local_axes': 'Local axes',
    'section_dimension': 'Section dimensions',
    'rebar_number': 'Number of rebars',
    'rebar_slop': 'Rebar slope',
    'material': 'Concrete material',
    'OK': 'OK',
    'not_checked': 'Not checked',
}

COLUMNS_CONTROL_LEGEND: list[tuple[str, str]] = [
    (_COLUMNS_CONTROL_COLORS[result], _COLUMNS_CONTROL_LABELS[result])
    for result in _COLUMNS_CONTROL_LABELS
]


class ColumnsControlModel(PandasModel):
    """Columns control — color-code cells by comparison result (enum-based).

    The ``kwargs`` dict must contain:
    - ``comparison_results``: dict of (row_label, col_name) -> result_name
    - ``columns_type_names_df``: DataFrame of column names (for header/index)
    - ``section_areas``: dict of section name -> area, for the edit delegate
    - ``etabs``: live EtabsModel connection, used to push section edits
    """

    def __init__(self, df: pd.DataFrame, kwargs: dict | None = None):
        super().__init__(df, kwargs)
        self._comparison = self.kwargs.get('comparison_results', {})
        self._names_df = self.kwargs.get('columns_type_names_df', df)
        self._section_areas = self.kwargs.get('section_areas', {})
        self._etabs = self.kwargs.get('etabs')

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._names_df.columns[section])
        return str(self._names_df.index[section])

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row, col = index.row(), index.column()
        value = self.df.iat[row, col]

        if role == Qt.ItemDataRole.DisplayRole:
            if pd.notna(value) and value != '':
                return str(value)
            return ""

        if role == Qt.ItemDataRole.BackgroundRole:
            row_label = self.df.index[row]
            col_name = self.df.columns[col]
            result_name = self._comparison.get((row_label, col_name), 'not_checked')
            color_name = _COLUMNS_CONTROL_COLORS.get(result_name, 'white')
            return QColor(color_name)

        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor(0, 0, 0)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        return None

    def _compare_result(self, row: int, col: int) -> str:
        """Compare the current above/below section pair using the actual frame names."""
        if row >= self._names_df.shape[0] - 1:
            return 'OK'

        above_frame = self._names_df.iat[row, col]
        below_frame = self._names_df.iat[row + 1, col]
        above_sec = self.df.iat[row, col]
        below_sec = self.df.iat[row + 1, col]

        if (
            pd.isna(above_frame) or str(above_frame) == ''
            or pd.isna(below_frame) or str(below_frame) == ''
            or pd.isna(above_sec) or str(above_sec) == ''
            or pd.isna(below_sec) or str(below_sec) == ''
        ):
            return 'not_checked'

        if self._etabs is None:
            return 'not_checked'

        try:
            result = self._etabs.prop_frame.compare_two_columns(
                str(below_frame),
                str(above_frame),
                self._section_areas,
                below_sec=str(below_sec),
                above_sec=str(above_sec),
            )
            return getattr(result, 'name', 'not_checked') or 'not_checked'
        except Exception:
            return 'not_checked'

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        frame_name = self._names_df.iat[index.row(), index.column()]
        if self._etabs is not None and pd.notna(frame_name) and frame_name != '':
            base |= Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole):
        """Update the table and recompute the comparison status for the edited stack."""
        if role != Qt.ItemDataRole.EditRole or not index.isValid() or not value:
            return False
        row, col = index.row(), index.column()
        frame_name = self._names_df.iat[row, col]
        if pd.isna(frame_name) or frame_name == '':
            return False

        matching_rows = [
            i for i in range(self._names_df.shape[0])
            if self._names_df.iat[i, col] == frame_name
        ]
        if not matching_rows:
            matching_rows = [row]

        for matching_row in matching_rows:
            self.df.iat[matching_row, col] = value

        affected_rows = set(matching_rows)
        affected_rows.update(r - 1 for r in matching_rows if r > 0)

        for affected_row in affected_rows:
            row_label = self.df.index[affected_row]
            col_name = self.df.columns[col]
            self._comparison[(row_label, col_name)] = self._compare_result(affected_row, col)

        # Recompute the actual above/below comparison for the edited stack.
        for affected_row in sorted(affected_rows):
            if affected_row < self._names_df.shape[0] - 1:
                row_label = self.df.index[affected_row]
                col_name = self.df.columns[col]
                self._comparison[(row_label, col_name)] = self._compare_result(affected_row, col)

        top_left = self.index(min(affected_rows), col)
        bottom_right = self.index(max(affected_rows), col)
        self.dataChanged.emit(
            top_left, bottom_right,
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole],
        )
        return True


# =====================================================================
#  Structure Model (earthquake factor properties table)
# =====================================================================

# Row indices
_CFACTOR, _K, _CDRIFT, _KDRIFT, _TAN, _TEXP, _TEXP125, _RU, _HMAX, _OMEGA0, _CD, _BTEIF = range(12)
# Column indices
_X, _Y, _X1, _Y1 = range(4)

_ROW_HEADERS = {
    _CFACTOR: 'C',
    _K: 'K',
    _CDRIFT: 'C_drift',
    _KDRIFT: 'K_drift',
    _TAN: 't_an',
    _TEXP: 't_exp',
    _TEXP125: '1.25 x t_exp',
    _RU: 'Ru',
    _HMAX: 'H_max',
    _OMEGA0: 'omega_0',
    _CD: 'Cd',
    _BTEIF: 'B',
}

_COL_HEADERS = {_X: 'X Dir', _Y: 'Y Dir', _X1: 'X1 Dir', _Y1: 'Y1 Dir'}


class StructureModel(QAbstractTableModel):
    """Seismic properties table — shows C, K, periods, etc. for each direction.

    Ported from civilTools/models.py StructureModel.
    """

    def __init__(self, build):
        super().__init__()
        self.build = build

    def set_rows(self, build):
        """Refresh model with a new Building instance without recreating the view/model."""
        self.beginResetModel()
        self.build = build
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 12

    def columnCount(self, parent=QModelIndex()):
        return 2 if self.build.building2 is None else 4

    def _column_data(self, column):
        """Return (system, t_exp, t_an, k, k_drift, b_teif, c, c_drift) for column."""
        bld = self.build
        if column == _X:
            src = bld
            attr_x = True
        elif column == _Y:
            src = bld
            attr_x = False
        elif column == _X1 and bld.building2:
            src = bld.building2
            attr_x = True
        elif column == _Y1 and bld.building2:
            src = bld.building2
            attr_x = False
        else:
            return None

        if attr_x:
            system = src.x_system
            t_exp, t_an = src.tx_exp, src.tx_an
            k, k_drift = src.kx, src.kx_drift
            b_teif = src.bx
        else:
            system = src.y_system
            t_exp, t_an = src.ty_exp, src.ty_an
            k, k_drift = src.ky, src.ky_drift
            b_teif = src.by

        c = ''
        c_drift = ''
        results = src.results if src is bld else src.results
        results_drift = src.results_drift if src is bld else src.results_drift
        idx = 1 if attr_x else 2
        if results[0]:
            c = results[idx]
        if results_drift[0]:
            c_drift = results_drift[idx]

        return system, t_exp, t_an, k, k_drift, b_teif, c, c_drift

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row, col = index.row(), index.column()
        cd = self._column_data(col)
        if cd is None:
            return None
        system, t_exp, t_an, k, k_drift, b_teif, c, c_drift = cd

        if role == Qt.ItemDataRole.DisplayRole:
            if row == _HMAX:
                return str(system.max_height)
            if row == _RU:
                return str(system.Ru)
            if row == _OMEGA0:
                return str(system.phi0)
            if row == _CD:
                return str(system.cd)
            if row == _TEXP:
                return f'{t_exp:.4f}'
            if row == _TEXP125:
                return f'{t_exp * 1.25:.4f}'
            if row == _TAN:
                return f'{t_an:.4f}'
            if row == _K:
                return f'{k:.4f}'
            if row == _CFACTOR:
                try:
                    return f'{c:.4f}'
                except (ValueError, TypeError):
                    return str(c)
            if row == _KDRIFT:
                return f'{k_drift:.4f}'
            if row == _CDRIFT:
                try:
                    return f'{c_drift:.4f}'
                except (ValueError, TypeError):
                    return str(c_drift)
            if row == _BTEIF:
                return f'{b_teif:.4f}'
            return None

        if role == Qt.ItemDataRole.BackgroundRole:
            if row in (_K, _CFACTOR):
                return QColor(100, 255, 100)
            if row in (_KDRIFT, _CDRIFT):
                return QColor(100, 100, 255)
            if row == _TAN:
                return QColor(255, 255, 20)
            return QColor(230, 230, 250)

        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor(0, 0, 0)

        if role == Qt.ItemDataRole.FontRole and row in (_K, _CFACTOR, _KDRIFT, _CDRIFT):
            font = QFont()
            font.setBold(True)
            font.setItalic(True)
            font.setPointSize(12)
            return font

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if orientation == Qt.Orientation.Horizontal:
                return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.BackgroundRole and orientation == Qt.Orientation.Vertical:
            if section in (_K, _CFACTOR):
                return QColor(120, 255, 120)
            if section in (_KDRIFT, _CDRIFT):
                return QColor(120, 120, 255)
            if section == _TAN:
                return QColor(250, 250, 100)
            return QColor(230, 230, 250)

        if role == Qt.ItemDataRole.FontRole and orientation == Qt.Orientation.Vertical:
            if section in (_K, _CFACTOR, _KDRIFT, _CDRIFT):
                font = QFont()
                font.setBold(True)
                font.setPointSize(12)
                return font

        if role == Qt.ItemDataRole.ToolTipRole:
            if section == _TEXP125:
                return 'مقدار حداکثر زمان تناوب تحلیلی که در محاسبه نیروی زلزله میتوان استفاده کرد.'
            if section == _HMAX:
                return 'حداکثر ارتفاع مجاز سیستم مقاوم نیروی جانبی'

        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Vertical:
                return _ROW_HEADERS.get(section, '')
            return _COL_HEADERS.get(section, '')

        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsEnabled
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled


# =====================================================================
#  Rebar Model  (from AutoCAD DWG extraction)
# =====================================================================

class RebarModel(PandasModel):
    """Rebar list — incomplete rows coloured red."""

    _RED_BG = QColor(255, 210, 210)
    _RED_FG = QColor(180, 0, 0)

    def __init__(self, df: pd.DataFrame, kwargs: dict | None = None):
        super().__init__(df, kwargs)
        # Locate the hidden `_complete` column (bool)
        self._complete_col = (
            list(self.df.columns).index('_complete')
            if '_complete' in self.df.columns else -1
        )

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        value = self.df.iat[row, col]

        # Hide the internal _complete column
        if col == self._complete_col:
            if role == Qt.ItemDataRole.DisplayRole:
                return ""
            return None

        is_bad = False
        if self._complete_col >= 0:
            is_bad = not bool(self.df.iat[row, self._complete_col])

        if role == Qt.ItemDataRole.DisplayRole:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return "—"
            return str(value)

        if role == Qt.ItemDataRole.BackgroundRole and is_bad:
            return self._RED_BG

        if role == Qt.ItemDataRole.ForegroundRole and is_bad:
            return self._RED_FG

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        return None

    def columnCount(self, parent=None):
        # Hide the _complete column from the view
        n = self.df.shape[1]
        if self._complete_col >= 0:
            return n - 1
        return n


class RebarSummaryModel(PandasModel):
    """Table model for rebar summary-by-size with a highlighted TOTAL row."""

    _TOTAL_BG = QColor(220, 235, 255)
    _TOTAL_FG = QColor(0, 0, 0)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        value = self.df.iat[row, col]
        is_total = str(self.df.iat[row, 0]) == "TOTAL"

        if role == Qt.ItemDataRole.DisplayRole:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return "—"
            if isinstance(value, float):
                return f"{value:,.1f}"
            return str(value)

        if role == Qt.ItemDataRole.BackgroundRole and is_total:
            return self._TOTAL_BG

        if role == Qt.ItemDataRole.FontRole and is_total:
            from PySide6.QtGui import QFont
            f = QFont()
            f.setBold(True)
            return f

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        return None