"""Item delegates for editable result tables."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QSize, QTimer, Qt
from PySide6.QtWidgets import QComboBox, QMessageBox, QStyledItemDelegate, QWidget


class ColumnsControlDelegate(QStyledItemDelegate):
    """Edit column sections — mirrors FreeCAD ColumnsControlDelegate."""

    def createEditor(self, parent, option, index):
        """Show only valid section choices for the current column stack."""
        source_model = _source_model(index.model())
        source_index = _to_source_index(index.model(), index)
        row, col = source_index.row(), source_index.column()
        try:
            frame_name = source_model._names_df.iat[row, col]
        except Exception:
            return None
        if source_model._etabs is None or not _has_section(frame_name):
            return None

        etabs = source_model._etabs
        section_areas = source_model._section_areas or {}
        current_section = str(
            index.model().data(index, Qt.ItemDataRole.DisplayRole) or ""
        )
        lower_section = ""
        if row < source_model._names_df.shape[0] - 1:
            lower_section = str(source_model.df.iat[row + 1, col] or "")

        sections: list[str] = []
        if row == source_model._names_df.shape[0] - 1:
            sections = [str(s) for s in section_areas.keys()]
        else:
            below_name = source_model._names_df.iat[row + 1, col]
            if _has_section(below_name):
                for candidate in section_areas.keys():
                    try:
                        ret = etabs.prop_frame.compare_two_columns(
                            str(below_name), str(frame_name), section_areas, above_sec=str(candidate)
                        )
                    except Exception:
                        continue
                    if ret is not None and getattr(ret, 'name', None) == 'OK':
                        sections.append(str(candidate))
            if not sections:
                sections = [str(s) for s in section_areas.keys()]

        default_section = lower_section if lower_section in sections else current_section
        if default_section and default_section not in sections:
            sections.insert(0, default_section)
        elif default_section and default_section in sections:
            pass

        combo = QComboBox(parent)
        combo.setEditable(False)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.blockSignals(True)
        combo.addItems(sections)
        current_index = combo.findText(default_section or current_section)
        if current_index != -1:
            combo.setCurrentIndex(current_index)
        combo.blockSignals(False)
        return combo

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            value = index.model().data(index, Qt.ItemDataRole.DisplayRole) or ""
            editor.blockSignals(True)
            editor.setCurrentText(str(value))
            editor.blockSignals(False)

    def setModelData(self, editor, model, index):
        # FreeCAD: model.setData(...) then unlock + FrameObj.SetSection(...)
        if not isinstance(editor, QComboBox):
            return
        selected_section = editor.currentText()
        if not selected_section:
            return

        source_model = _source_model(model)
        source_index = _to_source_index(model, index)
        row, col = source_index.row(), source_index.column()
        try:
            frame_name = source_model._names_df.iat[row, col]
        except Exception:
            return
        if not _has_section(frame_name):
            return

        # Update the table immediately so the editor can close without waiting on COM.
        source_model.setData(source_index, selected_section, Qt.ItemDataRole.EditRole)

        etabs = source_model._etabs
        if etabs is None:
            return
        name = str(frame_name)
        section = str(selected_section)

        def apply_section():
            try:
                etabs.unlock_model()
                etabs.SapModel.FrameObj.SetSection(name, section)
            except Exception:
                pass

        # Finish closing the editor, then apply on the next event-loop tick.
        QTimer.singleShot(0, apply_section)

    def sizeHint(self, option, index):
        fm = option.fontMetrics
        return QSize(fm.horizontalAdvance("2IPE14FPL200X10WP"), fm.height())

    def editorEvent(self, event, model, option, index):
        is_right_click = (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.RightButton
        )
        if is_right_click:
            self._show_section_comparison(model, index)
            return True
        return super().editorEvent(event, model, option, index)

    def _show_section_comparison(self, model, index) -> None:
        source_model = _source_model(model)
        source_index = _to_source_index(model, index)
        row, col = source_index.row(), source_index.column()
        if row >= source_model._names_df.shape[0] - 1:
            return

        above_section = source_model.df.iat[row, col]
        below_section = source_model.df.iat[row + 1, col]
        if not _has_section(above_section) or not _has_section(below_section):
            return

        parent = self.parent()
        parent_widget = parent if isinstance(parent, QWidget) else None
        try:
            from civiltools.gui.dialogs.column_section_comparison_dialog import (
                ColumnSectionComparisonDialog,
            )

            dialog = ColumnSectionComparisonDialog(
                source_model._etabs,
                str(above_section),
                str(below_section),
                parent_widget,
            )
            dialog.exec()
        except Exception as exc:
            QMessageBox.warning(
                parent_widget,
                "Section Comparison",
                f"Could not display the column sections:\n{exc}",
            )


def _source_model(model):
    """Unwrap the result table proxy model."""
    return model.sourceModel() if hasattr(model, "sourceModel") else model


def _to_source_index(model, index: QModelIndex) -> QModelIndex:
    """Map a possibly proxied index to the DataFrame-backed model."""
    return model.mapToSource(index) if hasattr(model, "mapToSource") else index


def _has_section(value) -> bool:
    return value is not None and value == value and value != ""
