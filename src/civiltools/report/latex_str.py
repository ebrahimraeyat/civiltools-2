"""
LaTeX formula strings for earthquake coefficient calculation.

Iranian Standard 2800, 4th Edition — complete formula chain with
generic templates and value-substitution functions.
"""

from __future__ import annotations


# ═══════════════════════════════════════════════════════════════════════════
# Generic formula templates (no values — for formulation sections)
# ═══════════════════════════════════════════════════════════════════════════

earthquake_formula = r"C = \frac{A \cdot B \cdot I}{R}"

earthquake_b_formula = r"B = B_1 \times N"

earthquake_b1 = r"""
B_1 = \begin{cases}
  S_0 + (S - S_0 + 1)\left(\frac{T}{T_0}\right) & T < T_0 \\
  S + 1 & T_0 \leq T \leq T_s \\
  (S + 1)\left(\frac{T_s}{T}\right)^{2/3} & T > T_s
\end{cases}
"""

earthquake_n1 = r"""
N = \begin{cases}
  1 & T \leq T_s \\
  \left(\frac{0.7T}{T_s}\right)^{0.4} & T_s < T \leq 4\,\mathrm{s} \\
  1.3 & T > 4\,\mathrm{s}
\end{cases}
\quad\text{(High / Very-High hazard)}
"""

earthquake_n2 = r"""
N = \begin{cases}
  1 & T \leq T_s \\
  \left(\frac{0.7T}{T_s}\right)^{0.5} & T_s < T \leq 4\,\mathrm{s} \\
  1.45 & T > 4\,\mathrm{s}
\end{cases}
\quad\text{(Moderate / Low hazard)}
"""

period_formula = r"T_{emp} = \alpha \cdot H^{\beta}"

period_infill_formula = r"T_{emp} = 0.8 \times \alpha \cdot H^{\beta}"

design_period_formula = (
    r"T = \max\!\left(T_{emp},\;\min(T_{an},\;1.25\,T_{emp})\right)"
)

k_formula = r"""
K = \begin{cases}
  1   & T \leq 0.5\,\mathrm{s} \\
  2   & T \geq 2.5\,\mathrm{s} \\
  0.5T + 0.75 & 0.5 < T < 2.5
\end{cases}
"""

c_min_formula = r"C_{min} = 0.12 \times A \times I"

base_shear_formula = r"V = C \times W"

soil_params_header = (
    r"\begin{array}{|c|c|c|c|c|}"
    r"\hline \text{Soil Type} & T_0 & T_s & S & S_0 \\ \hline"
    r"\end{array}"
)


# ═══════════════════════════════════════════════════════════════════════════
# Value substitution functions
# ═══════════════════════════════════════════════════════════════════════════

def earthquake_c_with_values(
    A: float, B: float, I: float, R: float, C: float,
) -> str:
    """C = ABI/R with substituted values."""
    return (
        rf"C = \frac{{{A} \times {B:.4f} \times {I}}}{{{R}}} = {C:.4f}"
    )


def period_with_values(
    alpha: float, beta: float, H: float, T_emp: float,
    is_infill: bool = False,
) -> str:
    """Empirical period with values."""
    prefix = r"0.8 \times " if is_infill else ""
    return (
        rf"T_{{emp}} = {prefix}{alpha} \times {H:.2f}^{{{beta}}} = {T_emp:.4f}\;\mathrm{{s}}"
    )


def design_period_with_values(
    T_emp: float, T_an: float, T_design: float,
) -> str:
    """Design period with values."""
    return (
        rf"T = \max({T_emp:.4f},\;\min({T_an:.4f},\;"
        rf"1.25 \times {T_emp:.4f})) = {T_design:.4f}\;\mathrm{{s}}"
    )


def b1_with_values(
    T: float, T0: float, Ts: float,
    S_val: float, S0: float, B1: float,
) -> str:
    """B1 reflection coefficient with values."""
    if T < T0:
        return (
            rf"B_1 = {S0} + ({S_val} - {S0} + 1)"
            rf"\left(\frac{{{T:.4f}}}{{{T0}}}\right) = {B1:.4f}"
        )
    if T <= Ts:
        return rf"B_1 = {S_val} + 1 = {B1:.4f}"
    return (
        rf"B_1 = ({S_val} + 1)"
        rf"\left(\frac{{{Ts}}}{{{T:.4f}}}\right)^{{2/3}} = {B1:.4f}"
    )


def n_with_values(
    T: float, Ts: float, N: float,
    is_high_hazard: bool = True,
) -> str:
    """N coefficient with values."""
    if T <= Ts:
        return rf"N = 1"
    exp = "0.4" if is_high_hazard else "0.5"
    if T <= 4.0:
        return (
            rf"N = \left(\frac{{0.7 \times {T:.4f}}}"
            rf"{{{Ts}}}\right)^{{{exp}}} = {N:.4f}"
        )
    limit = "1.3" if is_high_hazard else "1.45"
    return rf"N = {limit}"


def b_with_values(B1: float, N: float, B: float) -> str:
    """B = B1 × N with values."""
    return rf"B = {B1:.4f} \times {N:.4f} = {B:.4f}"


def k_with_values(T: float, K: float) -> str:
    """K distribution exponent with values."""
    if T <= 0.5:
        return rf"K = 1 \quad (T = {T:.4f} \leq 0.5)"
    if T >= 2.5:
        return rf"K = 2 \quad (T = {T:.4f} \geq 2.5)"
    return rf"K = 0.5 \times {T:.4f} + 0.75 = {K:.4f}"


def c_min_with_values(A: float, I: float, C_min: float) -> str:
    """C_min check with values."""
    return rf"C_{{min}} = 0.12 \times {A} \times {I} = {C_min:.4f}"


def c_check_with_values(C: float, C_min: float, C_final: float) -> str:
    """Final C comparison."""
    if C >= C_min:
        return rf"C = {C:.4f} \geq C_{{min}} = {C_min:.4f} \Rightarrow C = {C_final:.4f}\;\checkmark"
    return rf"C = {C:.4f} < C_{{min}} = {C_min:.4f} \Rightarrow C = {C_final:.4f}"


def soil_params_with_values(
    soil_type: str, T0: float, Ts: float,
    S_val: float, S0: float,
) -> str:
    """Soil parameter table row."""
    return (
        rf"\begin{{array}}{{|c|c|c|c|c|}}"
        rf"\hline \text{{Soil Type}} & T_0 & T_s & S & S_0 \\ \hline"
        rf" \text{{{soil_type}}} & {T0} & {Ts} & {S_val} & {S0} \\ \hline"
        rf"\end{{array}}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Complete calculation chains
# ═══════════════════════════════════════════════════════════════════════════

def full_earthquake_calculation(
    params: dict, direction: str = "x",
) -> list[tuple[str, str]]:
    """Generate full earthquake coefficient calculation as (description, latex) pairs.

    Parameters
    ----------
    params : dict
        Seismic parameters from BuildingModel.seismic_params.
        Expected keys per direction: ``Tx``, ``Tx_an``, ``Tx_design``,
        ``Bx``, ``B1x``, ``Nx``, ``Kx``, ``Cx``, ``Cx_drift``, etc.
        Plus global: ``A``, ``I``, ``Rx``, ``Ry``, ``soil_type``,
        ``T0``, ``Ts``, ``S``, ``S0``, ``alpha``, ``beta``, ``H``,
        ``risk_level``, ``is_infill``.
    direction : str
        ``'x'`` or ``'y'``.
    """
    d = direction.lower()
    D = direction.upper()

    A = params.get("A", 0.3)
    I_ = params.get("I", 1.0)
    R = params.get(f"R{d}", params.get("R", 7.0))
    T_emp = params.get(f"T{d}", 0.5)
    T_an = params.get(f"T{d}_an", 0.6)
    T_design = params.get(f"T{d}_design", T_emp)
    B1 = params.get(f"B1{d}", 2.5)
    N = params.get(f"N{d}", 1.0)
    B = params.get(f"B{d}", 2.5)
    K = params.get(f"K{d}", 1.0)
    C = params.get(f"C{d}", 0.1)
    alpha = params.get("alpha", params.get("Ct", 0.07))
    beta = params.get("beta", 0.75)
    H = params.get("H", params.get("height", 10.0))
    soil_type = params.get("soil_type", "III")
    T0 = params.get("T0", 0.15)
    Ts = params.get("Ts", 0.70)
    S = params.get("S", 1.75)
    S0 = params.get("S0", 1.75)
    is_high = params.get("risk_level", 3) >= 3
    is_infill = params.get("is_infill", False)

    C_min = 0.12 * A * I_
    C_final = max(C, C_min)

    steps = [
        (f"Main formula ({D})", earthquake_formula),
        (f"Empirical period ({D})", period_with_values(alpha, beta, H, T_emp, is_infill)),
        (f"Design period ({D})", design_period_with_values(T_emp, T_an, T_design)),
        (f"Soil parameters", soil_params_with_values(soil_type, T0, Ts, S, S0)),
        (f"Reflection coeff. B₁ ({D})", b1_with_values(T_design, T0, Ts, S, S0, B1)),
        (f"N coefficient ({D})", n_with_values(T_design, Ts, N, is_high)),
        (f"B = B₁ × N ({D})", b_with_values(B1, N, B)),
        (f"Distribution exponent K ({D})", k_with_values(T_design, K)),
        (f"Earthquake coefficient ({D})", earthquake_c_with_values(A, B, I_, R, C)),
        (f"Minimum check ({D})", c_check_with_values(C, C_min, C_final)),
    ]
    return steps


def full_drift_calculation(
    params: dict, direction: str = "x",
) -> list[tuple[str, str]]:
    """Generate drift-specific earthquake coefficient steps."""
    d = direction.lower()
    D = direction.upper()

    A = params.get("A", 0.3)
    I_ = params.get("I", 1.0)
    R = params.get(f"R{d}", 7.0)
    T_design = params.get(f"T{d}_design", 0.5)
    B = params.get(f"B{d}_drift", params.get(f"B{d}", 2.5))
    K = params.get(f"K{d}_drift", params.get(f"K{d}", 1.0))
    C = params.get(f"C{d}_drift", params.get(f"C{d}", 0.1))
    C_min = 0.12 * A * I_
    C_final = max(C, C_min)

    return [
        (f"Drift K ({D})", k_with_values(T_design, K)),
        (f"Drift C ({D})", earthquake_c_with_values(A, B, I_, R, C)),
        (f"Drift min check ({D})", c_check_with_values(C, C_min, C_final)),
    ]
