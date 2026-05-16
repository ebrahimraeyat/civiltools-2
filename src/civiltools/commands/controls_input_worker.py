# pyright: reportMissingImports=false, reportMissingModuleSource=false

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QThread, Signal

from etabs_api.controls_input import ControlsInput

__all__ = ["ControlWorker"]


class ControlWorker(QThread):
    """Background worker that runs input controls sequentially (COM/STA-safe)."""

    progress = Signal(int, int)
    control_started = Signal(str)
    control_finished = Signal(str, dict)
    all_finished = Signal(dict)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, etabs, controls_to_run: list[str], settings: dict[str, Any] | None = None, **_kwargs):
        super().__init__()
        self.etabs = etabs
        self.controls_to_run = controls_to_run
        self.settings = settings or {}
        self._is_cancelled = False
        self._skip_current = False   # skip only the running control
        self._controller: ControlsInput | None = None
        # Keep thread alive only while needed — do not block app exit
        self.setTerminationEnabled(True)

    def cancel(self) -> None:
        """Cancel all remaining controls and stop the run."""
        self._is_cancelled = True
        if self._controller is not None:
            self._controller.cancellation_token.cancel()

    def skip_current(self) -> None:
        """Interrupt only the running control; continue with the rest."""
        self._skip_current = True
        if self._controller is not None:
            self._controller.cancellation_token.cancel()

    def run(self) -> None:
        try:
            self._controller = ControlsInput(self.etabs)
            definitions = [self._controller.get_control_definition(item) for item in self.controls_to_run]
            total = len(definitions)
            if total == 0:
                self.all_finished.emit({})
                return
            results: dict[str, dict] = {}
            for completed, definition in enumerate(definitions, start=1):
                if self._is_cancelled:
                    self.cancelled.emit()
                    return
                # Reset token so a previous skip/cancel doesn't bleed into next control
                self._controller.cancellation_token.reset()
                self._skip_current = False
                self.control_started.emit(definition.key)
                result = self._controller._execute_control(definition, self.settings)
                results[definition.key] = result
                self.control_finished.emit(definition.key, result)
                self.progress.emit(completed, total)
                # If cancel() was called during this control, stop after recording result
                if self._is_cancelled:
                    self.cancelled.emit()
                    return
            self.all_finished.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))
