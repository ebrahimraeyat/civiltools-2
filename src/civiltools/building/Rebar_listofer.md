I have two existing Python scripts that extract rebar and stirrup information from AutoCAD drawings using COM (pywin32). They work with simple Text/MText, Block Reference and Dimension objects (see attached files: `extract_stirrups_from_dwg.py` and `rebar_from_dwg.py`).

Now I need to develop a NEW algorithm specifically for **longitudinal rebars** that are represented as **BLOCKS with ATTRIBUTES** and an associated **LEADER**. The new code should be based on the structure and helper functions from the provided files, but adapted to handle blocks and leaders.

**Input data specification:**

1. **Block Reference**: Name = `"buble"` (inserted in model space).
   - It has three visible attributes (tags and example values):
     - `DES1`: e.g., `"2T25"` → count = 2, diameter = 25 mm.
     - `DES2`: e.g., `"L=240"` → total length = 240 cm.
     - `PO`: e.g., `"25"` → position number (ignore it).
   

2. **Leader**: A straight leader object (AcDbLeader) attached to the block.
   - The last (or maybe first) vertex of the leader is at the block's insertion point.
   - The first (or maybe last) vertex (or the point near the arrow) gives the actual location where the rebar should be drawn.

3. **Shape identifier**: This is  an attribute inside the same block ( tag `"Des3"`). The identifier follows these patterns:
   - `TI` → straight bar (no bend)
   - `TL` → L‑shape (bend at one end)
   - `TU` → U‑shape (bend at both ends)
   - Optionally followed by a number (e.g., `TL40`, `TI30`, `TU15`). If present, that number is the **bend length in centimeters**. 
   
   If possible, extract the shape type (I, L, U) from the rebar shape. If it is difficult obtaint it from `"Des3"` tag of attribute.
   Also calculate bend length using the standard hook formula: calculate_hook_parameters function in line 510 of rebar_from_dwg, converted to cm (i.e., `16 * diameter / 10` cm). for `TI`, bend length = 0.
   I want to calculate the shape type only for drawing, 

**Processing logic required:**

1. Iterate through all Block References in the drawing (AcDbBlockReference).
2. Filter blocks with Name = `"buble"`. give it as parameter in function or None
3. For each such block:
   - Read attribute values by tag (`DES1`, `DES2`, `PO`).
   - Parse `DES1` to get `count` (int) and `diameter` (int, in mm). The format is like `2T25`, where `T` is the diameter symbol (could also be `∅`, `Ø`, etc., but here it's usually `T`).
   - Parse `DES2` to get `length` (int, in cm) from `L=240`.
   - Find the associated **Leader**. Since the block may not directly reference the leader, you need to search all leaders in model space and find the one whose last/first vertex is closest to the block insertion point (within a tolerance, e.g., 5 units relative to leader length). The leader's start point (first vertex) becomes the `anchor_point` for drawing the rebar.
   - Determine the **direction** of the rebar: vector from block insertion point to leader start point (or vice versa, depending on the leader's direction). Usually the arrow points from the annotation block toward the rebar. So the rebar should be drawn from the arrow tip (start point) **along** that direction, with the given total length.
   - Find the **shape identifier** (TI/TL/TU + optional number). First check if the block has an attribute with tag "Des3" (or similar). If not, search nearby Text/MText objects (using a proximity factor, e.g., 20× text height) that match the pattern. Extract the bend length (if present) or compute it.
   - **Drawing** (using AutoCAD COM methods like `AddLine`, `AddLightWeightPolyline`, `AddArc`):
     - For `TI`: Draw a single straight line of length `length` cm from the `anchor_point` along the direction vector.
     - For `TL`: Draw the main line of length `length` cm, then at the end draw a perpendicular hook (bend) of `bend_length` cm. The hook direction it not matter, only the shape type, L or U
     - For `TU`: Draw a straight bar with hooks at **both** ends. The total length is `length` cm. Draw the main segment (length minus 2×bend_length) and add a bend of `bend_length` at each end, both bends in the same perpendicular direction (like a staple).
   - All coordinates are in the current drawing units (assume centimeters). The drawn shapes should be placed on a separate layer (e.g., "ListoferRebarShapes") for clarity.

**Code structure and reuse:**

- Use the same COM connection and helper functions from the attached files (e.g., `_spoint`, `_dist`, `clean_mtext`, and the general approach of iterating model space).
- Create a new class, e.g., `LongitudinalRebarFromDwg`, that inherits or mimics the style of `StirrupFromDwg` and `RebarFromDwg`.
- Include methods:
  - `get_all_blocks_and_leaders()`: collect all block references and leaders.
  - `parse_longitudinal_rebars()`: iterate blocks, find matching leaders and shape texts, parse attributes, and store results in a data class (e.g., `LongitudinalRebarData`).
  - `draw_rebar_shapes()`: for each parsed rebar, draw the corresponding shape in model space.
- Provide a `summary()` and `summary_by_size()` similar to the existing code.

**Constraints and notes:**

- **Ignore stirrups completely**: do not process texts like `T12@15` or `1T12(ADD)`. Those belong to the stirrup extraction script and are not relevant here.
- The `PO` attribute is not essential for the final output; you can ignore it.
- The block may have other text attributes (like `T1.40`) that are not used for longitudinal rebars; skip them.
- The leader may be non‑associative; just find the nearest leader by geometry.
- If a block has no matching leader within a reasonable distance, mark it as incomplete.
- If the shape identifier is missing, default to `TI` (straight) and warn the user.

**Expected output:**

- A list/dictionary of extracted longitudinal rebars with fields: count, diameter, length, shape_type, bend_length, anchor_point, direction, and object IDs of source entities.
- The actual shapes drawn automatically in the AutoCAD drawing.
- A console summary of the parsed rebars (similar to the existing scripts).

Please provide the complete Python code, with clear comments and error handling, that can be run inside AutoCAD (using pywin32). The code should be self‑contained and rely only on standard libraries plus pywin32.

**Attached files for reference** (contain useful helper functions and patterns):
- `extract_stirrups_from_dwg.py`
- `rebar_from_dwg.py`

Thank you.