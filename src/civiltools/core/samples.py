"""
Sample building generator — 3-story RC frame for demo / testing.

Uses the core BuildingModel data classes (no OCC dependency).
"""

from __future__ import annotations

from civiltools.core import (
    BuildingModel, Story, GridAxis, StructuralElement,
    SectionProfile, Material,
)


def create_sample_building() -> BuildingModel:
    """Create a realistic 3-story RC frame building.

    Grid layout (plan view)::

        Y
        ^
        |  1───2───3
        12m  (6m + 6m)
        |  A───B───C───D
        +────────────────> X
              15m  (5+5+5m)

    Stories: Ground (3.5 m), 1st (3.2 m), 2nd (3.2 m)
    """
    model = BuildingModel(
        project_name="Sample Building",
        location="Tehran",
        designer="civilTools Demo",
    )

    # Grid coordinates
    x_coords = [0.0, 5.0, 10.0, 15.0]
    y_coords = [0.0, 6.0, 12.0]
    x_labels = ["A", "B", "C", "D"]
    y_labels = ["1", "2", "3"]

    # Stories
    model.stories = [
        Story("Ground Floor", 0.0, 3.5),
        Story("1st Floor", 3.5, 3.2),
        Story("2nd Floor", 6.7, 3.2),
    ]

    # Materials
    model.materials = {
        "C25": Material("C25", "concrete", fc=25.0, Es=30000.0, weight=25.0),
        "S400": Material("S400", "rebar", fy=400.0, Es=200000.0),
    }

    # Section profiles
    model.sections = {
        "Col50x50": SectionProfile("Col50x50", "rectangular",
                                   {"b": 0.50, "h": 0.50}),
        "Beam30x50": SectionProfile("Beam30x50", "rectangular",
                                    {"b": 0.30, "h": 0.50}),
    }

    # Grid axes — horizontal lines at Z = -0.05
    axis_z = -0.05
    overhang = 2.5
    for i, x in enumerate(x_coords):
        model.axes.append(GridAxis(
            x_labels[i], "X",
            (x, y_coords[0] - overhang, axis_z),
            (x, y_coords[-1] + overhang, axis_z),
        ))
    for j, y in enumerate(y_coords):
        model.axes.append(GridAxis(
            y_labels[j], "Y",
            (x_coords[0] - overhang, y, axis_z),
            (x_coords[-1] + overhang, y, axis_z),
        ))

    # Beam/column dimensions
    col_bx, col_by = 0.50, 0.50
    beam_w, beam_d = 0.30, 0.50

    for story in model.stories:
        sn = story.name
        zb = story.elevation
        zt = story.top

        # ── Columns at grid intersections ─────────────────────────────
        for i, x in enumerate(x_coords):
            for j, y in enumerate(y_coords):
                model.elements.append(StructuralElement(
                    uid=model.next_uid("C"),
                    element_type="column",
                    story=sn,
                    label=f"C-{x_labels[i]}{y_labels[j]}",
                    section="Col50x50",
                    material="C25",
                    start_point=(x, y, zb),
                    end_point=(x, y, zt),
                    width=col_bx,
                    depth=col_by,
                ))

        # ── Beams along X ─────────────────────────────────────────────
        for j, y in enumerate(y_coords):
            for k in range(len(x_coords) - 1):
                model.elements.append(StructuralElement(
                    uid=model.next_uid("BX"),
                    element_type="beam",
                    story=sn,
                    label=f"BX-{x_labels[k]}{x_labels[k+1]}-{y_labels[j]}",
                    section="Beam30x50",
                    material="C25",
                    start_point=(x_coords[k], y, zt),
                    end_point=(x_coords[k + 1], y, zt),
                    width=beam_w,
                    depth=beam_d,
                ))

        # ── Beams along Y ─────────────────────────────────────────────
        for i, x in enumerate(x_coords):
            for k in range(len(y_coords) - 1):
                model.elements.append(StructuralElement(
                    uid=model.next_uid("BY"),
                    element_type="beam",
                    story=sn,
                    label=f"BY-{y_labels[k]}{y_labels[k+1]}-{x_labels[i]}",
                    section="Beam30x50",
                    material="C25",
                    start_point=(x, y_coords[k], zt),
                    end_point=(x, y_coords[k + 1], zt),
                    width=beam_w,
                    depth=beam_d,
                ))

        # ── Floor slab ────────────────────────────────────────────────
        model.elements.append(StructuralElement(
            uid=model.next_uid("F"),
            element_type="floor",
            story=sn,
            label=f"Slab-{sn}",
            material="C25",
            start_point=(x_coords[0], y_coords[0], zt),
            end_point=(x_coords[-1], y_coords[-1], zt),
            thickness=0.25,
        ))

        # ── Walls (perimeter, with openings) ──────────────────────────
        wall_h = story.height - beam_d

        if sn == "Ground Floor":
            openings_s = [{"offset": 1.5, "z_offset": 1.0, "width": 1.5, "height": 1.5}]
            openings_w = [{"offset": 1.5, "z_offset": 0.0, "width": 1.2, "height": 2.5}]
        else:
            openings_s = [{"offset": 1.0, "z_offset": 0.8, "width": 2.0, "height": 1.8}]
            openings_w = [{"offset": 1.5, "z_offset": 0.8, "width": 1.5, "height": 1.5}]

        model.elements.append(StructuralElement(
            uid=model.next_uid("W"),
            element_type="wall",
            story=sn,
            label="W-S-AB",
            material="C25",
            start_point=(0, 0, zb),
            end_point=(5, 0, zb),
            thickness=0.20,
            openings=openings_s,
            properties={"height": wall_h},
        ))

        model.elements.append(StructuralElement(
            uid=model.next_uid("W"),
            element_type="wall",
            story=sn,
            label="W-W-12",
            material="C25",
            start_point=(0, 0, zb),
            end_point=(0, 6, zb),
            thickness=0.20,
            openings=openings_w,
            properties={"height": wall_h},
        ))

        model.elements.append(StructuralElement(
            uid=model.next_uid("W"),
            element_type="wall",
            story=sn,
            label="W-E-12",
            material="C25",
            start_point=(15, 0, zb),
            end_point=(15, 6, zb),
            thickness=0.20,
            properties={"height": wall_h},
        ))

        model.elements.append(StructuralElement(
            uid=model.next_uid("W"),
            element_type="wall",
            story=sn,
            label="W-N-CD",
            material="C25",
            start_point=(10, 12, zb),
            end_point=(15, 12, zb),
            thickness=0.20,
            openings=[{"offset": 1.0, "z_offset": 0.8, "width": 2.0, "height": 1.8}],
            properties={"height": wall_h},
        ))

    # Seismic parameters
    model.seismic_params = {
        "code": "Standard 2800 4th Ed.",
        "zone": 3,
        "soil_type": "III",
        "importance_factor": 1.0,
        "R_x": 7.0,
        "R_y": 7.0,
        "Ct": 0.07,
    }

    return model
