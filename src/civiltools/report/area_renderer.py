"""
Matplotlib-based area load plan renderer — draws floor areas
colour-coded by their load group with a descriptive legend.

All functions use the Agg backend and are process-safe for
``ProcessPoolExecutor``.
"""

from __future__ import annotations

import io
from typing import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon
from matplotlib.gridspec import GridSpec

from civiltools.report.data_extractor import AreaInfo, FrameInfo, LoadSetDef


# ── Colour palette for up to 12 load sets ────────────────────────────────
_PALETTE = [
    "#aec6cf",   # pastel blue
    "#ffb347",   # pastel orange
    "#77dd77",   # pastel green
    "#ff6961",   # pastel red
    "#cb99c9",   # pastel purple
    "#fdfd96",   # pastel yellow
    "#836953",   # pastel brown
    "#89cff0",   # baby blue
    "#f49ac2",   # pastel magenta
    "#cfcfc4",   # pastel grey
    "#b39eb5",   # pastel violet
    "#ffcc99",   # peach
]


def render_area_load_plan(
    areas: Sequence[AreaInfo],
    load_set_defs: dict[str, LoadSetDef],
    frames: Sequence[FrameInfo] | None = None,
    story_name: str = "",
    dpi: int = 150,
) -> bytes:
    """Render a plan view of floor areas coloured by load group.

    The legend shows only load set names. A coloured table below the
    plan lists the load patterns and values for each set present in
    this story.

    Parameters
    ----------
    areas : sequence of AreaInfo
        Area polygons with their assigned load set.
    load_set_defs : dict
        ``{set_name: LoadSetDef}`` with load descriptions.
    frames : sequence of FrameInfo, optional
        Beams/columns drawn as thin context lines.
    story_name : str
        Story name for the title.
    dpi : int
        Output resolution.

    Returns
    -------
    bytes
        PNG image bytes.
    """
    if not areas:
        fig, ax = plt.subplots(figsize=(12, 10))
        ax.set_aspect("equal")
        ax.set_facecolor("white")
        ax.set_title(f"Story: {story_name} - Area Load Plan",
                     fontsize=10, fontweight="bold", pad=10)
        ax.text(0.5, 0.5, "No area load data available",
                ha="center", va="center", transform=ax.transAxes)
        return _fig_to_bytes(fig, dpi)

    # ── Assign colours to load sets ───────────────────────────────────
    unique_sets = sorted({a.load_set for a in areas})
    set_colors = {
        name: _PALETTE[i % len(_PALETTE)]
        for i, name in enumerate(unique_sets)
    }

    # Build the figure: plan on top, load table below
    n_sets = len(unique_sets)
    table_height_ratio = max(1, min(n_sets, 6))
    fig = plt.figure(figsize=(12, 10 + table_height_ratio * 0.35))
    gs = GridSpec(2, 1, height_ratios=[10, table_height_ratio], hspace=0.15)
    ax = fig.add_subplot(gs[0])
    ax_table = fig.add_subplot(gs[1])

    ax.set_aspect("equal")
    ax.set_facecolor("white")
    ax.set_title(f"Story: {story_name} - Area Load Plan",
                 fontsize=10, fontweight="bold", pad=10)

    # ── Draw context frame lines ──────────────────────────────────────
    if frames:
        for f in frames:
            if f.frame_type == "beam":
                ax.plot(
                    [f.x1, f.x2], [f.y1, f.y2],
                    color="#c0c0c0", linewidth=0.6, zorder=1,
                )
            else:
                cx = (f.x1 + f.x2) / 2
                cy = (f.y1 + f.y2) / 2
                ax.plot(cx, cy, "s", color="#c0c0c0", markersize=3, zorder=1)

    # ── Draw area polygons ────────────────────────────────────────────
    for area in areas:
        verts = [(x, y) for x, y in area.vertices]
        if len(verts) < 3:
            continue
        color = set_colors.get(area.load_set, "#dddddd")
        ax.add_patch(plt.Polygon(
            verts, closed=True,
            facecolor=color, edgecolor="#555555",
            linewidth=0.5, alpha=0.65, zorder=2,
        ))

    # ── Legend (names only) ───────────────────────────────────────────
    legend_handles = []
    for name in unique_sets:
        color = set_colors[name]
        legend_handles.append(
            mpatches.Patch(facecolor=color, edgecolor="#555555",
                           alpha=0.65, label=name)
        )

    if legend_handles:
        ax.legend(
            handles=legend_handles,
            loc="upper left",
            bbox_to_anchor=(1.01, 1.0),
            fontsize=7,
            framealpha=0.9,
            title="Load Sets",
            title_fontsize=8,
        )

    # ── Plan axes ─────────────────────────────────────────────────────
    ax.grid(True, alpha=0.08, linestyle="--")
    ax.set_xlabel("X (m)", fontsize=8)
    ax.set_ylabel("Y (m)", fontsize=8)
    ax.tick_params(labelsize=6)
    ax.autoscale()
    ax.margins(0.08)

    # ── Coloured table below the plan ─────────────────────────────────
    ax_table.axis("off")
    table_data = []
    cell_colors = []
    for name in unique_sets:
        color = set_colors[name]
        lsd = load_set_defs.get(name)
        if lsd:
            patterns = ", ".join(
                f"{p} = {v:.0f}" for p, v in lsd.loads.items()
            )
        else:
            patterns = ""
        table_data.append([name, f"{patterns} kg/m\u00b2"])
        cell_colors.append([color, "#ffffff"])

    if table_data:
        tbl = ax_table.table(
            cellText=table_data,
            colLabels=["Load Set", "Load Patterns (kg/m\u00b2)"],
            cellColours=cell_colors,
            colColours=["#d0d0d0", "#d0d0d0"],
            loc="center",
            cellLoc="left",
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(7)
        tbl.scale(1, 1.3)
        # Make header row bold
        for (row, col), cell in tbl.get_celld().items():
            if row == 0:
                cell.set_text_props(fontweight="bold")

    fig.tight_layout(pad=1.0)
    return _fig_to_bytes(fig, dpi)


def _fig_to_bytes(fig, dpi: int) -> bytes:
    """Serialize a matplotlib figure to PNG bytes."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                transparent=False, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
