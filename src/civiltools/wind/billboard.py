"""
civiltools.wind.billboard
=========================
Wind load calculation for free-standing billboards (تابلو اعلانات)
according to Iranian National Building Code – Section 6 (مبحث ششم),
Chapter 10 (Wind Load), pages 87-112, 155-156, and flowchart on page 169.

References
----------
- Clause 3-10-6  : Basic wind pressure equation (page 89)
- Clause 6-10-6  : Exposure coefficient Ce (page 91)
- Clause 8-10-6  : Gust effect factor Cg (pages 88-89)
- Clause 9-10-6  : Simplified method for h < 20m (page 97)
- Figure P-6-4-5 : Force coefficient Cf tables (page 156)
- Table 1-10-6   : Basic wind speed by city (pages 116-117)
- Flowchart       : Step-by-step procedure (page 169)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Literal

# ── City wind-speed table (km/h) — Table 1-10-6, pages 116-117 ──────────────
WIND_SPEEDS: dict[str, float] = {
    "Tehran": 110,
    "Esfahan": 110,
    "Shiraz": 100,
    "Tabriz": 110,
    "Mashhad": 110,
    "Ahvaz": 110,
    "Kerman": 130,
    "Rasht": 90,
    "Yazd": 100,
    "Hamedan": 100,
    "Arak": 100,
    "Kermanshah": 100,
    "Urmia": 100,
    "Zahedan": 100,
    "Bandar Abbas": 110,
    "Bushehr": 100,
    "Sari": 90,
    "Gorgan": 90,
    "Qom": 100,
    "Sanandaj": 100,
    "Ilam": 100,
    "Birjand": 100,
    "Bojnord": 100,
    "Zanjan": 100,
    "Ardabil": 100,
    "Khorramabad": 100,
    "Yasuj": 100,
}

_DEFAULT_WIND_SPEED: float = 100.0  # km/h fallback

# ── Cf tables (Figure P-6-4-5, page 156) ─────────────────────────────────────
# Format: list of (l/h, Cf) breakpoints for linear interpolation.
# For l/h > last breakpoint value is used (∞ case).
_CF_ON_GROUND: list[tuple[float, float]] = [
    (0.0,  1.10),
    (1.0,  1.20),
    (10.0, 1.30),
]

_CF_ELEVATED: list[tuple[float, float]] = [
    (0.0,  1.15),
    (1.0,  1.30),
    (10.0, 2.00),
]


# ══════════════════════════════════════════════════════════════════════════════
# Data classes
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BillboardInputs:
    """
    Input parameters for billboard wind load calculation.

    Attributes
    ----------
    height : float
        Height of the billboard sign panel (h), in metres.
    width : float
        Width of the billboard sign panel (w), in metres.
    bottom_elevation : float
        Height of the bottom edge of the billboard from ground level, in metres.
    city : str
        City name used to look up the basic wind speed from Table 1-10-6.
        Falls back to 100 km/h with a warning if the city is not found.
    terrain_type : {'open', 'crowded'}
        Site exposure category per Clause 6-10-7:
        'open'  → باز (open terrain, e.g. flatlands)
        'crowded' → پرتراکم (urban/suburban terrain)
    support_type : {'on_ground', 'elevated'}
        'on_ground' → billboard base sits on/at ground level (l = 0)
        'elevated'  → billboard is elevated on columns/mast
        Note: support length l is taken equal to the billboard width (w).
    importance_factor : float, optional
        Wind importance factor I_w (default 1.0 for ordinary billboards).
    topographic_factor : float, optional
        Topographic factor C_t (default 1.0 for flat sites).
    """

    # Geometry
    height: float
    width: float
    bottom_elevation: float

    # Site
    city: str
    terrain_type: Literal["open", "crowded"]

    # Support
    support_type: Literal["on_ground", "elevated"]
    # Note: support_length (l) is taken equal to billboard width (w)

    # Factors (with defaults)
    importance_factor: float = 1.0
    topographic_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.height <= 0:
            raise ValueError(f"height must be > 0, got {self.height}")
        if self.width <= 0:
            raise ValueError(f"width must be > 0, got {self.width}")
        if self.bottom_elevation < 0:
            raise ValueError(f"bottom_elevation must be >= 0, got {self.bottom_elevation}")
        if self.terrain_type not in ("open", "crowded"):
            raise ValueError(
                f"terrain_type must be 'open' or 'crowded', got '{self.terrain_type}'"
            )
        if self.support_type not in ("on_ground", "elevated"):
            raise ValueError(
                f"support_type must be 'on_ground' or 'elevated', got '{self.support_type}'"
            )


@dataclass
class WindLoadOutput:
    """
    Results of the billboard wind load calculation.

    Attributes
    ----------
    V_kmh : float
        Basic wind speed from city table (km/h).
    V_ms : float
        Basic wind speed converted to m/s.
    q : float
        Basic wind pressure q = 0.001637 × V_ms² (kN/m²).
    Z_ref : float
        Reference height at the centroid of the billboard panel (m).
    Ce : float
        Exposure coefficient per Clause 6-10-6.
    Cg : float
        Gust effect factor per Clause 8/9-10-6.
    Cf : float
        Force coefficient from Figure P-6-4-5 (interpolated).
    A : float
        Area of the billboard panel = width × height (m²).
    F_total_kN : float
        Total wind force on the billboard (kN).
    P_design_kPa : float
        Equivalent uniform design pressure = F_total / A (kN/m²).
    lh_ratio : float
        Computed l/h ratio used for Cf interpolation.
    cg_method : str
        Description of the Cg method applied (static or dynamic note).
    """

    V_kmh: float
    V_ms: float
    q: float
    Z_ref: float
    Ce: float
    Cg: float
    Cf: float
    A: float
    F_total_kN: float
    P_design_kPa: float
    lh_ratio: float
    cg_method: str


# ══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ══════════════════════════════════════════════════════════════════════════════

def get_wind_speed(city: str) -> float:
    """
    Look up basic wind speed (km/h) for a city from Table 1-10-6 (pages 116-117).

    A case-insensitive search is performed first; if the city is not found a
    warning is issued and the default value of 100 km/h is returned.

    Parameters
    ----------
    city : str
        City name (e.g. 'Tehran', 'Mashhad').

    Returns
    -------
    float
        Wind speed in km/h.
    """
    # Exact match first
    if city in WIND_SPEEDS:
        return float(WIND_SPEEDS[city])
    # Case-insensitive fallback
    city_lower = city.strip().lower()
    for key, value in WIND_SPEEDS.items():
        if key.lower() == city_lower:
            return float(value)
    warnings.warn(
        f"City '{city}' not found in wind speed table. "
        f"Using default fallback value of {_DEFAULT_WIND_SPEED} km/h.",
        UserWarning,
        stacklevel=3,
    )
    return _DEFAULT_WIND_SPEED


def _interpolate(x: float, table: list[tuple[float, float]]) -> float:
    """
    Linear interpolation/extrapolation over a sorted (x, y) breakpoint table.

    For x beyond the last breakpoint the last value is returned (∞ case per
    Figure P-6-4-5: for l/h > 10 the value at ∞ = value at 10 applies).

    Parameters
    ----------
    x : float
        Query point.
    table : list[tuple[float, float]]
        Sorted list of (x_i, y_i) breakpoints.

    Returns
    -------
    float
        Interpolated (or clamped) y value.
    """
    if x <= table[0][0]:
        return table[0][1]
    if x >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        x0, y0 = table[i]
        x1, y1 = table[i + 1]
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return table[-1][1]  # should never reach here


def interpolate_cf(lh_ratio: float, support_type: str) -> float:
    """
    Determine force coefficient Cf from Figure P-6-4-5 (page 156).

    Parameters
    ----------
    lh_ratio : float
        Ratio l/h where l = support_length, h = billboard height.
    support_type : {'on_ground', 'elevated'}
        Type of support condition.

    Returns
    -------
    float
        Interpolated Cf value.
    """
    if support_type == "on_ground":
        return _interpolate(lh_ratio, _CF_ON_GROUND)
    else:  # elevated
        return _interpolate(lh_ratio, _CF_ELEVATED)


def calculate_ce(z: float, terrain_type: str) -> float:
    """
    Calculate the exposure coefficient Ce per Clause 6-10-6 (page 91).

    Parameters
    ----------
    z : float
        Reference height in metres (centroid of billboard).
    terrain_type : {'open', 'crowded'}
        Site exposure category.

    Returns
    -------
    float
        Exposure coefficient Ce (clamped to [0.50, 2.50]).
    """
    z = max(z, 0.1)  # avoid division by zero or log of zero
    if terrain_type == "open":
        ce = (z / 10.0) ** 0.28
    else:  # crowded
        ce = 0.5 * (z / 12.7) ** 0.28
    return max(0.50, min(2.50, ce))


# ══════════════════════════════════════════════════════════════════════════════
# Main calculation function
# ══════════════════════════════════════════════════════════════════════════════

def calculate_wind_load(
    inputs: BillboardInputs,
    verbose: bool = True,
) -> WindLoadOutput:
    """
    Calculate wind load on a free-standing billboard per مبحث ششم Chapter 10.

    Follows the step-by-step flowchart on page 169 of the Iranian National
    Building Code Section 6 (Loads on Buildings).

    Parameters
    ----------
    inputs : BillboardInputs
        All required input parameters.
    verbose : bool, optional
        If True (default), prints a detailed step-by-step report to stdout.

    Returns
    -------
    WindLoadOutput
        Dataclass containing all intermediate and final results.

    Raises
    ------
    ValueError
        If inputs contain invalid values (caught by BillboardInputs.__post_init__).
    """

    h = inputs.height
    w = inputs.width
    b = inputs.bottom_elevation
    l = w          # support_length equals billboard width per user convention
    I_w = inputs.importance_factor

    # ── Step 1: Basic wind speed ──────────────────────────────────────────────
    V_kmh = get_wind_speed(inputs.city)
    V_ms = V_kmh / 3.6
    q = 0.001637 * V_ms ** 2  # kN/m²

    # ── Step 2: Reference height ──────────────────────────────────────────────
    Z_ref = b + h / 2.0

    # ── Step 3: Exposure coefficient Ce ──────────────────────────────────────
    Ce = calculate_ce(Z_ref, inputs.terrain_type)

    # ── Step 4: Gust effect factor Cg ────────────────────────────────────────
    aspect_ratio = h / w
    if h < 20.0 and aspect_ratio < 1.0:
        Cg = 1.0
        cg_method = f"Static simplified method (h={h}m < 20m, aspect={aspect_ratio:.2f} < 1)"
    else:
        Cg = 1.0  # conservative — dynamic method not implemented for billboards
        cg_method = (
            "Conservative static (Cg=1.0); "
            "dynamic method (Appendix 6-4) recommended for h>=20m or aspect>=1"
        )

    # ── Step 5: Force coefficient Cf ─────────────────────────────────────────
    lh_ratio = l / h
    Cf = interpolate_cf(lh_ratio, inputs.support_type)

    # Find the two surrounding breakpoints for the verbose report
    _table = _CF_ON_GROUND if inputs.support_type == "on_ground" else _CF_ELEVATED
    cf_low_x = cf_low_y = cf_high_x = cf_high_y = None
    for i in range(len(_table) - 1):
        if _table[i][0] <= lh_ratio <= _table[i + 1][0]:
            cf_low_x, cf_low_y = _table[i]
            cf_high_x, cf_high_y = _table[i + 1]
            break
    if cf_low_x is None:  # beyond last breakpoint
        cf_low_x, cf_low_y = _table[-1]
        cf_high_x, cf_high_y = _table[-1]

    # ── Step 6: Area ──────────────────────────────────────────────────────────
    A = w * h  # m²

    # ── Step 7: Total wind force ──────────────────────────────────────────────
    F_total = I_w * Cf * q * Cg * Ce * A  # kN

    # ── Step 8: Equivalent design pressure ───────────────────────────────────
    P_design = F_total / A  # kN/m²

    # ── Verbose output ────────────────────────────────────────────────────────
    if verbose:
        print("=" * 55)
        print("=== Wind Load Calculation for Billboard ===")
        print("=" * 55)
        print("Input Summary:")
        print(f"  Dimensions        : {h:.2f}m (H) x {w:.2f}m (W)")
        print(f"  Area              : {A:.2f} m2")
        print(f"  Bottom elevation  : {b:.2f} m")
        print(f"  City              : {inputs.city}")
        print(f"  Terrain           : {inputs.terrain_type}")
        print(f"  Support           : {inputs.support_type}, l = w = {l:.2f} m")
        print(f"  Importance factor : {I_w:.2f}")
        print()
        print("Step 1: Basic Wind Speed")
        print(f"  V (km/h) = {V_kmh:.2f}")
        print(f"  V (m/s)  = {V_ms:.4f}")
        print(f"  q = 0.001637 * ({V_ms:.4f})^2 = {q:.4f} kN/m2")
        print()
        print("Step 2: Reference Height")
        print(f"  Z = {b:.2f} + {h:.2f}/2 = {Z_ref:.4f} m")
        print()
        print("Step 3: Exposure Coefficient Ce")
        print(f"  Terrain = {inputs.terrain_type}")
        if inputs.terrain_type == "open":
            print(f"  Ce = ({Z_ref:.2f}/10)^0.28 = {Ce:.4f}")
        else:
            print(f"  Ce = 0.5 * ({Z_ref:.2f}/12.7)^0.28 = {Ce:.4f}")
        print(f"  (clamped to [0.50, 2.50]) => Ce = {Ce:.4f}")
        print()
        print("Step 4: Gust Factor Cg")
        print(f"  {cg_method}")
        print(f"  Cg = {Cg:.2f}")
        print()
        print("Step 5: Force Coefficient Cf")
        print(f"  l/h = {l:.2f} / {h:.2f} = {lh_ratio:.4f}")
        print(f"  Support type : {inputs.support_type}")
        if cf_low_x != cf_high_x:
            print(f"  Cf at l/h={cf_low_x}: {cf_low_y:.2f}, at l/h={cf_high_x}: {cf_high_y:.2f}")
        print(f"  Interpolated Cf = {Cf:.4f}")
        print()
        print("Step 6: Total Wind Force")
        print(f"  A = {w:.2f} * {h:.2f} = {A:.4f} m2")
        print(
            f"  F = {I_w:.2f} * {Cf:.4f} * {q:.4f} * {Cg:.2f} * {Ce:.4f} * {A:.4f}"
        )
        print(f"    = {F_total:.4f} kN")
        print()
        print("Step 7: Design Pressure")
        print(f"  P_design = {F_total:.4f} / {A:.4f} = {P_design:.4f} kN/m2")
        print()
        print("=" * 55)
        print("=== Output Summary ===")
        print("=" * 55)
        print(f"  Wind Speed      : {V_ms:.2f} m/s  ({V_kmh:.2f} km/h)")
        print(f"  Basic Pressure  : {q:.4f} kN/m2")
        print(f"  Reference Height: {Z_ref:.2f} m")
        print(f"  Ce              : {Ce:.4f}")
        print(f"  Cg              : {Cg:.2f}")
        print(f"  Cf              : {Cf:.4f}")
        print(f"  Total Force     : {F_total:.4f} kN")
        print(f"  Design Pressure : {P_design:.4f} kN/m2")
        print("=" * 55)

    return WindLoadOutput(
        V_kmh=V_kmh,
        V_ms=V_ms,
        q=q,
        Z_ref=Z_ref,
        Ce=Ce,
        Cg=Cg,
        Cf=Cf,
        A=A,
        F_total_kN=F_total,
        P_design_kPa=P_design,
        lh_ratio=lh_ratio,
        cg_method=cg_method,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Example usage
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    sample = BillboardInputs(
        height=2.0,
        width=4.0,
        bottom_elevation=1.0,
        city="Tehran",
        terrain_type="open",
        support_type="elevated",
        importance_factor=1.0,
        topographic_factor=1.0,
    )
    result = calculate_wind_load(sample)
