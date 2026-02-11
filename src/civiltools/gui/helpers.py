"""Small Qt helper utilities."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QDialog


def set_children_enabled(parent: QWidget, enabled: bool):
    """Enable or disable all child widgets of *parent*."""
    for child in parent.findChildren(QWidget):
        child.setEnabled(enabled)


def has_attribs(obj, attribs, function=any) -> bool:
    """Return True if *obj* has any (or all) of *attribs*."""
    return function(hasattr(obj, attr) for attr in attribs)


def set_dialog_icon(dialog: QDialog, icon_name: str):
    """Set a window icon on a dialog from the icons directory."""
    from civiltools.gui.icons import icon
    qicon = icon(icon_name)
    if not qicon.isNull():
        dialog.setWindowIcon(qicon)
