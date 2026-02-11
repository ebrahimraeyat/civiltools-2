---
id: seismic_design
title: Seismic Design (Standard 2800)
title_fa: طراحی لرزه‌ای (آیین‌نامه ۲۸۰۰)
context: design.seismic
order: 10
---

# Seismic Design — Standard 2800

civilTools implements the full **Iranian Standard 2800 (4th Edition)**
seismic design procedure for building structures.

## Design Spectrum

The design base acceleration is computed as:

$$A = A_0 \times I \times B$$

where:
- $A_0$ = base acceleration coefficient (Table 2-3)
- $I$ = importance factor (Table 2-4)
- $B$ = response spectrum coefficient

## Base Shear

The base shear force is:

$$V = C \times W$$

where $C$ is the seismic coefficient:

$$C = \frac{A \cdot B_1}{R}$$

- $R$ = response modification factor (Table 3-4)
- $B_1$ = building response coefficient
- $W$ = effective seismic weight

## Period Calculation

The fundamental period is estimated using the empirical formula:

$$T = C_t \times H^{0.75}$$

| Structure Type     | $C_t$  |
|--------------------|--------|
| Steel MRF          | 0.08   |
| Concrete MRF       | 0.07   |
| Braced / Wall      | 0.05   |

where $H$ is the building height in meters.

## Vertical Distribution

The lateral force at story $i$ is:

$$F_i = \frac{w_i h_i^k}{\sum_{j=1}^{n} w_j h_j^k} \cdot V$$

where:
- $k = 1$ for $T \leq 0.5\,\mathrm{s}$
- $k = 2$ for $T \geq 2.5\,\mathrm{s}$
- Linear interpolation for intermediate periods

## Report Generation

All seismic design parameters and calculations are included in the
**Structural Report**. Go to **Tools → Generate Report** to create
PDF or DOCX output with full formulas and value substitutions.

## Configuration

Set seismic parameters in **Edit → Seismic Parameters**:
- Seismic zone (1–4)
- Soil type (I–IV)
- Importance category
- Structural system type
- Building height and number of stories
