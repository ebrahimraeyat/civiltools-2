---
id: viewer
title: 3D Viewer
title_fa: نمایشگر سه‌بعدی
context: viewer
order: 5
---

# 3D Viewer

The 3D viewer is based on OpenCASCADE (via PythonOCC) and provides
interactive visualization of the structural model.

## Navigation

| Action         | Mouse/Key             |
|----------------|-----------------------|
| Rotate         | Middle-click + drag   |
| Pan            | Middle-click + Shift  |
| Zoom           | Scroll wheel          |
| Fit All        | Press `V` or toolbar  |
| Select element | Left-click            |

## Story Visibility

Use the **Story Panel** dock (right side) to toggle visibility of
individual stories and element types:

- **Columns**: Vertical elements
- **Beams**: Horizontal frame elements
- **Walls**: Shear wall panels
- **Floors**: Slab elements
- **Axes**: Grid reference lines

Check/uncheck story checkboxes to show or hide entire floors.

## Display Modes

- **Shaded**: Default solid rendering with transparency
- **Wireframe**: Edge-only display for better visibility
- Toggle via **View → Wireframe** or toolbar button

## View Presets

The toolbar provides quick view presets:
- **Top** (XY plane — plan view)
- **Front** (XZ plane)
- **Right** (YZ plane)
- **Iso** (isometric 3D view)

## Colors

| Element   | Color            |
|-----------|------------------|
| Columns   | Steel Blue       |
| Beams     | Dark Orange      |
| Walls     | Light Gray       |
| Floors    | Light Green      |
| Axes      | Red dashed lines |

Colors can be customized in **Settings → Display**.
