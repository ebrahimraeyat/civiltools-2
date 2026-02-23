"""
Command registry — all structural commands auto-register here.

Each command is a subclass of ``BaseCommand``.  The ``REGISTRY`` dict
maps command_id → command class for easy menu / toolbar wiring.
"""

from civiltools.commands.base import BaseCommand, CommandResult

REGISTRY: dict[str, type[BaseCommand]] = {}


def register(cls: type[BaseCommand]) -> type[BaseCommand]:
    """Class decorator — registers a command by its *command_id*."""
    REGISTRY[cls.command_id] = cls
    return cls


# Import command modules so they register themselves on import.
from civiltools.commands import (  # noqa: E402, F401
    # ── Original 5 ──────────────────────────────────────────────
    torsion,
    drift,
    joint_shear,
    design_columns,
    dynamic_scale,
    # ── Edit ────────────────────────────────────────────────────
    settings,
    edit_commands,
    # ── Control ─────────────────────────────────────────────────
    aj_correction,
    weakness,
    story_stiffness,
    beam_deflection,
    columns_100_30,
    columns_control,
    high_pressure_columns,
    story_forces,
    diaphragm_forces,
    # ── Assign ──────────────────────────────────────────────────
    earthquake_factor,
    beam_j,
    assign_commands,
    live_load,
    # ── Define ──────────────────────────────────────────────────
    explode_seismic,
    define_commands,
    define_axes,
    # ── Tools ───────────────────────────────────────────────────
    tools_commands,
    extract_rebars,
    # ── Shear Wall ──────────────────────────────────────────────
    shearwall_commands,
)

__all__ = ["BaseCommand", "CommandResult", "REGISTRY", "register"]
