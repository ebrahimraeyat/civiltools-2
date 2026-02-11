"""
DXF import, AutoCAD COM interaction, column/axis detection.

Submodules
----------
- **dxf_reader** — parse DXF files via ezdxf
- **autocad_reader** — read selected entities from a live AutoCAD session
- **column_detector** — detect rectangular columns from blocks, hatches, polylines
- **axis_builder** — create X/Y grid axes from column centres
- **undo** — lightweight undo/redo stack for the axes workflow
"""
