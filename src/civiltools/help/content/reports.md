---
id: reports
title: Reports
title_fa: گزارش‌ها
context: tools.report
order: 15
---

# Report Generation

civilTools generates comprehensive structural engineering reports in
**PDF** and **DOCX** formats.

## How to Generate

1. Open a model with completed analysis results
2. Go to **Tools → Generate Report** or press `Ctrl+R`
3. Choose the report options in the dialog:
   - **Format**: PDF, DOCX, or Both
   - **Language**: English, فارسی (Persian), or Bilingual
   - **Sections**: Select which report sections to include

## Report Sections

Reports can include any combination of:

| Section                  | Description                              |
|--------------------------|------------------------------------------|
| Building Information     | Stories, grid layout, materials          |
| Seismic Parameters       | Standard 2800 inputs and calculations    |
| Base Shear               | V computation with all sub-formulas      |
| Story Forces             | Vertical distribution table              |
| Drift Check              | Story drift ratios vs. allowable limits  |
| Irregularity Check       | Torsional, mass, stiffness irregularity  |
| Beam Deflection          | Deflection checks per ABA requirements   |
| Column/Wall Design       | Design ratios and reinforcement summary  |

## Persian PDF Features

- **B Nazanin** font for Persian text (auto-detected from system fonts)
- Full **RTL** (right-to-left) layout
- **LaTeX** math equations rendered as images in PDF
- Bilingual mode shows both Persian and English side-by-side

## DOCX Features

- Styled headings with corporate color scheme
- Auto-generated Table of Contents
- Editable — modify in Microsoft Word after export
- Math equations via Office Math Markup (OMML)

## Custom Ordering

Report section order can be controlled in **Settings → Report**
or per-export via the report dialog.
