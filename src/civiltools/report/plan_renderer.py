"""
Matplotlib-based story plan renderer — draws beam/column layouts
with section name labels for each building story.

All functions use the Agg backend and are process-safe, suitable for
use inside ``ProcessPoolExecutor``.
"""

from __future__ import annotations

import io
import math
from typing import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from civiltools.report.data_extractor import FrameInfo


# ── Colours ──────────────────────────────────────────────────────────────
BEAM_COLOR = "#334155"        # slate-700
BEAM_WIDTH = 1.6
COL_COLOR = "#1e3a5f"         # dark navy
COL_MARKER = 8                # marker size in points
LABEL_COLOR = "#1a1a1a"
LABEL_SIZE = 7.0              # increased from 5.0 for legibility
TITLE_SIZE = 10
BG_COLOR = "white"
GRID_ALPHA = 0.1


def render_story_plan(
    frames: Sequence[FrameInfo],
    story_name: str,
    dpi: int = 150,
) -> bytes:
    """Render a plan view of beams and columns with section labels.

    Parameters
    ----------
    frames : sequence of FrameInfo
        Beams and columns for the story.
    story_name : str
        Story name for the plot title.
    dpi : int
        Output resolution.

    Returns
    -------
    bytes
        PNG image bytes.
    """
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_aspect("equal")
    ax.set_facecolor(BG_COLOR)
    ax.set_title(f"Story: {story_name} - Beam / Column Plan",
                 fontsize=TITLE_SIZE, fontweight="bold", pad=10)

    if not frames:
        ax.text(0.5, 0.5, "No frame data available",
                ha="center", va="center", transform=ax.transAxes)
        return _fig_to_bytes(fig, dpi)

    beams = [f for f in frames if f.frame_type == "beam"]
    columns = [f for f in frames if f.frame_type == "column"]

    # ── Draw beams ────────────────────────────────────────────────────
    labelled_sections: set[tuple[float, float, str]] = set()

    for b in beams:
        ax.plot(
            [b.x1, b.x2], [b.y1, b.y2],
            color=BEAM_COLOR, linewidth=BEAM_WIDTH, solid_capstyle="round",
        )
        # Label at midpoint
        mx = (b.x1 + b.x2) / 2
        my = (b.y1 + b.y2) / 2
        angle = math.degrees(math.atan2(b.y2 - b.y1, b.x2 - b.x1))
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180

        # Avoid duplicate labels at nearly the same position
        key = (round(mx, 1), round(my, 1), b.section)
        if key not in labelled_sections:
            labelled_sections.add(key)
            ax.text(
                mx, my, b.section,
                fontsize=LABEL_SIZE, color=LABEL_COLOR,
                ha="center", va="bottom",
                rotation=angle, rotation_mode="anchor",
                bbox=dict(boxstyle="round,pad=0.1", fc="white",
                          ec="none", alpha=0.7),
            )

    # ── Draw columns (markers only, no labels) ───────────────────────
    for c in columns:
        cx = (c.x1 + c.x2) / 2
        cy = (c.y1 + c.y2) / 2
        ax.plot(cx, cy, "s", color=COL_COLOR, markersize=COL_MARKER,
                zorder=5)

    # ── Axis formatting ───────────────────────────────────────────────
    ax.grid(True, alpha=GRID_ALPHA, linestyle="--")
    ax.set_xlabel("X (m)", fontsize=8)
    ax.set_ylabel("Y (m)", fontsize=8)
    ax.tick_params(labelsize=6)
    ax.autoscale()
    ax.margins(0.08)
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
