import re
from sympy import symbols
from sympy.physics.units import kg, m, mm, liter, metric_ton
from sympy.physics.units.systems.si import dimsys_SI as SI
from sympy.physics.units import convert_to

# -------------------------
# Define powers explicitly
# -------------------------
m2 = m**2
m3 = m**3

# -------------------------
# Unit Mapping & Aliases
# -------------------------
SYM_MAP = {
    "kg": kg,
    "kgs": kg,
    "kilogram": kg,
    "t": metric_ton,
    "tonne": metric_ton,
    "mt": metric_ton,
    "g": kg / 1000,
    "m": m,
    "mm": mm,
    "cm": 0.01 * m,
    "km": 1000 * m,
    "m2": m2,
    "sqm": m2,
    "m3": m3,
    "cum": m3,
    "l": liter,
    "ltr": liter,
    "ml": 0.001 * liter,
    "m2-mm": m2 * mm,
    "nos": symbols("nos"),
    "pcs": symbols("nos"),
    "unit": symbols("nos"),
}


# -------------------------
# Parse unit string
# -------------------------
def parse_to_sympy(unit_str):
    if not unit_str:
        return None
    clean = unit_str.lower().replace("co2e", "").replace("gwp", "").strip()
    processed_str = re.sub(r"(?<=[a-z0-9])-(?=[a-z])", "*", clean)
    for key in sorted(SYM_MAP.keys(), key=len, reverse=True):
        processed_str = re.sub(rf"\b{key}\b", f"SYM_MAP['{key}']", processed_str)
    try:
        return eval(processed_str, {"SYM_MAP": SYM_MAP})
    except:
        return None


# -------------------------
# Get dimension dictionary
# -------------------------
def get_dimension(expr):
    if expr is None:
        return None
    try:
        if hasattr(expr, "dimension"):
            return SI.get_dimensional_dependencies(expr.dimension)
        else:
            return SI.get_dimensional_dependencies(expr)
    except:
        return None


# -------------------------
# Compute mass in kg for mass units
# -------------------------
def mass_in_kg(expr):
    try:
        factor_expr = convert_to(expr, kg)
        if hasattr(factor_expr, "coeff"):
            return float(factor_expr.coeff(kg))
        return None
    except:
        return None


# -------------------------
# kg_factor calculation
# -------------------------
def analyze_conversion_sympy(mat_unit, carbon_unit_denom, conv_factor):
    res = {
        "kg_factor": None,
        "is_suspicious": False,
        "comment": "",
        "debug_dim_match": False,
    }

    m_expr = parse_to_sympy(mat_unit)
    c_expr = parse_to_sympy(carbon_unit_denom)

    # Validate CF
    try:
        cf = float(conv_factor)
    except:
        cf = 0.0

    if cf <= 0:
        res.update(
            {
                "kg_factor": None,
                "is_suspicious": True,
                "comment": "CF must be positive.",
            }
        )
        return res

    # If units not parsable, fallback to string logic
    if m_expr is None or c_expr is None:
        if mat_unit == carbon_unit_denom:
            res["kg_factor"] = None
            res["comment"] = "Unknown unit, but units match by string."
        else:
            res["kg_factor"] = None
            res["comment"] = "Unknown unit, cannot compute kg_factor but not flagged."
        return res

    # Dimensions
    m_dim = get_dimension(m_expr)
    c_dim = get_dimension(c_expr)
    mass_dim = get_dimension(kg)
    res["debug_dim_match"] = m_dim == c_dim

    # ------------------------- Logic -------------------------
    # Case 1: Material is mass (kg, tonne)
    if m_dim == mass_dim:
        kg_factor = mass_in_kg(m_expr)
        if kg_factor is not None:
            res["kg_factor"] = kg_factor
            res["comment"] = f"Material already in mass, kg_factor = {kg_factor}."
        else:
            res["kg_factor"] = None
            res["is_suspicious"] = True
            res["comment"] = "Cannot determine mass in kg for material unit."

    # Case 2: CF converts material to mass
    elif c_dim == mass_dim:
        res["kg_factor"] = cf
        res["comment"] = f"CF converts material to mass: kg_factor = CF = {cf}."
        if abs(cf - 1.0) < 1e-6:
            res["is_suspicious"] = True
            res["comment"] += " Flagged: CF=1.0 may be placeholder."

    # Case 3: Cannot determine kg_factor
    else:
        res["kg_factor"] = None
        res["is_suspicious"] = True
        res["comment"] = (
            "Cannot determine kg_factor: non-mass material and CF does not convert to mass."
        )

    return res


# -------------------------
# CF validation
# -------------------------
def validate_cf_simple(mat_unit, carbon_unit_denom, cf):
    """
    Returns dictionary:
    - sus: True if suspicious
    - suggest: "1" or "!1" or "pos" only if suspicious
    """
    result = {"sus": False, "suggest": None}

    # CF must be positive
    if cf <= 0:
        result["sus"] = True
        result["suggest"] = "pos"
        return result

    # Compare units
    if mat_unit == carbon_unit_denom:
        result["sus"] = abs(cf - 1.0) > 1e-6
        if result["sus"]:
            result["suggest"] = "1"
    else:
        result["sus"] = abs(cf - 1.0) < 1e-6
        if result["sus"]:
            result["suggest"] = "!1"

    return result


# # -------------------------
# # Test Cases
# # -------------------------
# if __name__ == "__main__":
#     test_cases = [
#         # Label, Material Unit, Carbon Denom, CF
#         ("Concrete Density", "m3", "kg", 2400),
#         ("Tonne Scaling", "tonne", "kg", 1000),
#         ("Incorrect Tonne Scaling", "tonne", "kg", 1),
#         ("Paint Yield", "kg", "m2-mm", 0.5),
#         ("Placeholder Linear Weight", "m", "kg", 1.0),
#         ("Complex Algebraic Cancellation", "kg", "m3-m2", 0.5),
#         ("Piece to Mass", "pcs", "kg", 0.3),
#         ("Vol to Vol", "m3", "l", 1000),
#         ("Area to Func", "m2", "m2-mm", 0.001),
#         ("Energy Match", "MJ", "MJ", 1.0),
#     ]

#     # Print table header
#     headers = [
#         "Label",
#         "Material Unit",
#         "Carbon Denom",
#         "CF",
#         "kg_factor",
#         "CF Sus",
#         "CF Suggest",
#         "Status",
#     ]
#     print(" | ".join(f"{h:<25}" for h in headers))
#     print("-" * (25 * len(headers)))

#     for label, m_u, c_u, cf in test_cases:
#         out_kg = analyze_conversion_sympy(m_u, c_u, cf)
#         out_cf = validate_cf_simple(m_u, c_u, cf)

#         kg_f = (
#             f"{out_kg['kg_factor']:.3f}" if out_kg["kg_factor"] is not None else "None"
#         )
#         cf_sus = "Yes" if out_cf["sus"] else "No"
#         cf_suggest = (
#             str(out_cf["suggest"])
#             if out_cf["sus"] and out_cf["suggest"] is not None
#             else ""
#         )
#         status = (
#             "✅ Valid"
#             if not out_kg["is_suspicious"] and not out_cf["sus"]
#             else "🚩 Suspicious"
#         )

#         print(
#             f"{label:<25} | {m_u:<25} | {c_u:<25} | {cf:<25} | "
#             f"{kg_f:<25} | {cf_sus:<25} | {cf_suggest:<25} | {status}"
#         )
