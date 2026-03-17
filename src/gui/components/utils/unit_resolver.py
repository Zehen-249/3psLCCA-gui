"""
gui/components/utils/unit_resolver.py
======================================
Pure-dict unit analysis — mirrors the logic in material_dialog.py.

No SymPy dependency. All lookups use the same UNIT_TO_SI / UNIT_DIMENSION
tables from definitions.py that drive the MaterialDialog UI, so the two
subsystems can never diverge.

Public API (backward-compatible):
    get_unit_info(code, custom_units=None)         -> (to_si, dimension)
    suggest_cf(mat_code, denom_code, ...)          -> float | None
    analyze_conversion_sympy(mat, denom, cf, ...)  -> dict  (main entry point)
    validate_cf_simple(mat, denom, cf)             -> dict
"""

from .definitions import UNIT_TO_SI, UNIT_DIMENSION, SI_BASE_UNITS

# ---------------------------------------------------------------------------
# Global custom-units cache
# Loaded once from custom_materials.db at startup (or on demand).
# All functions in this module consult this cache automatically so callers
# don't have to thread a custom_units list through every call.
# ---------------------------------------------------------------------------

_custom_units_cache: list[dict] = []


def load_custom_units() -> None:
    """(Re-)load all user-defined custom units from the DB into the cache.

    Call this once at app startup and again whenever the user adds/deletes
    a custom unit via the UI.
    """
    global _custom_units_cache
    try:
        from ..structure.registry.custom_material_db import CustomMaterialDB
        _custom_units_cache = CustomMaterialDB().list_custom_units()
    except Exception as exc:
        print(f"[unit_resolver] Could not load custom units: {exc}")
        _custom_units_cache = []


def get_custom_units() -> list[dict]:
    """Return the current in-process custom-units list."""
    return _custom_units_cache


def get_known_units() -> set[str]:
    """Return the full set of recognised unit codes (canonical + aliases).

    Derived from UNIT_TO_SI and _UNIT_ALIASES so there is a single source
    of truth — no hardcoded lists elsewhere in the codebase.
    """
    return set(UNIT_TO_SI.keys()) | set(_UNIT_ALIASES.keys())


# ---------------------------------------------------------------------------
# Aliases — normalise SOR / registry strings to canonical unit codes
# Mirrors _SOR_UNIT_ALIASES in material_dialog.py plus extra common variants
# ---------------------------------------------------------------------------

_UNIT_ALIASES: dict[str, str] = {
    "rmt":      "rm",
    "lmt":      "rm",
    "sqmt":     "sqm",
    "t":        "tonne",
    "kgs":      "kg",
    "ton":      "tonne",
    "metric_ton": "tonne",
    "kilogram": "kg",
    "meter":    "m",
    "metre":    "m",
    "sqft":     "sqft",
    "sqyd":     "sqyd",
    "cft":      "cft",
}


# ---------------------------------------------------------------------------
# Core helper — mirrors MaterialDialog._get_unit_info
# ---------------------------------------------------------------------------

def get_unit_info(
    code: str,
    custom_units: list | None = None,
) -> tuple[float | None, str | None]:
    """Return (to_si, dimension) for *code*.

    Resolution order:
      1. Canonical UNIT_TO_SI / UNIT_DIMENSION registry.
      2. Global custom-units cache (loaded from DB), then the explicit
         *custom_units* list if provided (kept for backward compatibility).
      3. _UNIT_ALIASES fallback (then re-tries 1 & 2).

    Returns (None, None) when the unit is completely unknown.
    """
    if not code:
        return None, None

    code = code.strip()

    # 1. Direct hit in canonical registry
    si_val = UNIT_TO_SI.get(code)
    dim = UNIT_DIMENSION.get(code)
    if si_val is not None:
        return si_val, dim

    # 2. Global cache first, then any explicit list passed by caller
    for source in (_custom_units_cache, custom_units or []):
        cu = next((c for c in source if c.get("symbol") == code), None)
        if cu:
            return float(cu.get("to_si", 1.0)), cu.get("dimension")

    # 3. Alias lookup — lowercase for robustness
    alias = _UNIT_ALIASES.get(code.lower())
    if alias and alias != code:
        return get_unit_info(alias, custom_units)

    return None, None


# ---------------------------------------------------------------------------
# CF suggestion — mirrors MaterialDialog._update_cf
# ---------------------------------------------------------------------------

def suggest_cf(
    mat_code: str,
    denom_code: str,
    custom_units: list | None = None,
) -> float | None:
    """Return the auto-suggested conversion factor, or None if not determinable.

    Logic identical to MaterialDialog._update_cf:
      • mat == denom      → 1.0  (hidden field in the UI)
      • same dimension    → mat_si / denom_si  (unit conversion)
      • different dims    → None  (user must supply a physical value, e.g. density)
    """
    if mat_code == denom_code:
        return 1.0

    mat_si, mat_dim = get_unit_info(mat_code, custom_units)
    denom_si, denom_dim = get_unit_info(denom_code, custom_units)

    if (mat_si is not None and denom_si is not None
            and mat_dim is not None and mat_dim == denom_dim):
        return mat_si / denom_si

    return None


# ---------------------------------------------------------------------------
# Main analysis — replaces the old SymPy-based analyze_conversion_sympy
# ---------------------------------------------------------------------------

def analyze_conversion_sympy(
    mat_unit: str,
    carbon_unit_denom: str,
    conv_factor,
    custom_units: list | None = None,
) -> dict:
    """Analyse whether *conv_factor* is plausible for the given unit pair.

    Returns a dict matching the original shape so all existing callers work:
        {
            "kg_factor":      float | None,
            "is_suspicious":  bool,
            "comment":        str,
            "debug_dim_match": bool,
        }

    Suspicion rules mirror MaterialDialog._update_cf / validate_and_accept:
      0. CF ≤ 0                  → always suspicious.
      1. Same unit code          → CF should be 1; flag if not.
      2. Same dimension, diff unit → expected CF = mat_si/denom_si; flag if >1% off.
      3. Material is Mass        → kg_factor = mat_si; not suspicious on its own.
      4. Denominator is Mass     → CF converts qty → mass; flag if CF = 1 (placeholder).
      5. Different non-mass dims → flag only if CF = 1 (likely placeholder).
      6. Unknown units           → string-equality fallback.
    """
    res = {
        "kg_factor": None,
        "is_suspicious": False,
        "comment": "",
        "debug_dim_match": False,
    }

    try:
        cf = float(conv_factor)
    except (TypeError, ValueError):
        cf = 0.0

    # ── Case 0: invalid CF ────────────────────────────────────────────────────
    if cf <= 0:
        res.update(is_suspicious=True, comment="CF must be positive.")
        return res

    mat_si, mat_dim = get_unit_info(mat_unit, custom_units)
    denom_si, denom_dim = get_unit_info(carbon_unit_denom, custom_units)

    res["debug_dim_match"] = (mat_dim is not None) and (mat_dim == denom_dim)

    # ── Case 6: unknown unit(s) — string-equality fallback ───────────────────
    if mat_si is None or denom_si is None:
        if mat_unit == carbon_unit_denom:
            res["comment"] = "Unknown unit, but units match by string."
        else:
            suspicious = abs(cf - 1.0) < 1e-6
            res.update(
                is_suspicious=suspicious,
                comment=(
                    "Unknown units; CF=1 may be a placeholder."
                    if suspicious
                    else "Unknown units; cannot verify CF."
                ),
            )
        return res

    # ── Case 1: identical unit codes ──────────────────────────────────────────
    if mat_unit == carbon_unit_denom:
        suspicious = abs(cf - 1.0) > 1e-6
        res.update(
            kg_factor=(mat_si if mat_dim == "Mass" else None),
            is_suspicious=suspicious,
            comment=(
                "Same unit — CF should be 1."
                if suspicious
                else "Same unit, CF=1 correct."
            ),
        )
        return res

    # ── Case 2: same dimension, different unit (e.g. tonne/kg, ft/m, m3/cft) ─
    if mat_dim == denom_dim:
        expected = mat_si / denom_si
        suspicious = abs(cf - expected) / max(abs(expected), 1e-12) > 0.01
        res.update(
            kg_factor=(mat_si if mat_dim == "Mass" else None),
            is_suspicious=suspicious,
            comment=(
                f"Same dimension ({mat_dim}); expected CF≈{expected:g}, got {cf:g}."
                if suspicious
                else f"Same dimension ({mat_dim}), CF={cf:g} matches expected {expected:g}."
            ),
        )
        return res

    # ── Case 3: material is mass (kg, tonne, …) ───────────────────────────────
    if mat_dim == "Mass":
        res.update(
            kg_factor=mat_si,
            comment=f"Material already in mass; kg_factor={mat_si:g}.",
        )
        return res

    # ── Case 4: denominator is mass — CF converts material quantity → mass ────
    if denom_dim == "Mass":
        # 1 mat_unit = cf denom_units; 1 denom_unit = denom_si kg
        kg_factor = cf * denom_si
        suspicious = abs(cf - 1.0) < 1e-6
        res.update(
            kg_factor=kg_factor,
            is_suspicious=suspicious,
            comment=(
                f"CF converts {mat_dim} → mass; kg_factor={kg_factor:g}."
                + (" CF=1 may be a placeholder." if suspicious else "")
            ),
        )
        return res

    # ── Case 5: different non-mass dimensions (e.g. Volume → Length) ─────────
    suspicious = abs(cf - 1.0) < 1e-6
    res.update(
        is_suspicious=suspicious,
        comment=(
            f"Different dimensions ({mat_dim} → {denom_dim}); CF=1 likely a placeholder."
            if suspicious
            else f"Cross-dimension CF ({mat_dim} → {denom_dim}) = {cf:g}."
        ),
    )
    return res


# ---------------------------------------------------------------------------
# Simple CF validation (validate_cf_simple) — improved to use registry
# ---------------------------------------------------------------------------

def validate_cf_simple(mat_unit: str, carbon_unit_denom: str, cf: float) -> dict:
    """Quick plausibility check.

    Returns {"sus": bool, "suggest": str | None}.

    Mirrors MaterialDialog validate_and_accept logic:
      • CF ≤ 0        → sus, suggest="pos"
      • same unit     → sus if CF ≠ 1,   suggest="1"
      • same dim      → sus if CF deviates from mat_si/denom_si, suggest=expected
      • diff dims     → sus if CF = 1,   suggest="!1"
    """
    if cf <= 0:
        return {"sus": True, "suggest": "pos"}

    mat_si, mat_dim = get_unit_info(mat_unit)
    denom_si, denom_dim = get_unit_info(carbon_unit_denom)

    if mat_unit == carbon_unit_denom:
        sus = abs(cf - 1.0) > 1e-6
        return {"sus": sus, "suggest": "1" if sus else None}

    if mat_si is not None and denom_si is not None and mat_dim == denom_dim:
        expected = mat_si / denom_si
        sus = abs(cf - expected) / max(abs(expected), 1e-12) > 0.01
        return {"sus": sus, "suggest": f"{expected:g}" if sus else None}

    # Different or unknown dimensions — CF=1 is suspicious
    sus = abs(cf - 1.0) < 1e-6
    return {"sus": sus, "suggest": "!1" if sus else None}
