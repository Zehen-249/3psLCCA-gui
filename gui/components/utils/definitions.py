# ---------------------------------------------------------------------------
# utils/definitions.py
# ---------------------------------------------------------------------------

BASE_DOCS_URL = "https://yourdocs.com/structure/"

FIELD_DEFINITIONS = {
    # ── Basic Info ──────────────────────────────────────────────────────────
    "material_name": {
        "label": "Material Name",
        "explanation": "Name of the material or work item as it appears in your project schedule.",
        "doc_slug": "material-name",
        "required": True,
    },
    "quantity": {
        "label": "Quantity",
        "explanation": "Total quantity of this material required on site, expressed in your project unit (Unit A).",
        "doc_slug": "quantity",
        "required": True,
    },
    "unit": {
        "label": "Unit",
        "explanation": "The site/project unit for quantity. Example: m3, kg, m, nos.",
        "doc_slug": "unit",
        "required": True,
    },
    "rate": {
        "label": "Rate (Cost)",
        "explanation": "Unit cost of this material in your project currency.",
        "doc_slug": "rate",
        "required": False,
    },
    "rate_source": {
        "label": "Rate Source",
        "explanation": "Reference for the rate used. Example: DSR 2023, Market Rate, Quoted Rate.",
        "doc_slug": "rate-source",
        "required": False,
    },
    # ── Carbon Emission ─────────────────────────────────────────────────────
    "carbon_emission": {
        "label": "Emission Factor",
        "explanation": (
            "Carbon emission factor from a standard reference (e.g. IFC, IPCC, ICE Database), "
            "expressed in kgCO2e per Unit B. Example: 0.159 kgCO2e/kg for ready-mix concrete."
        ),
        "doc_slug": "emission-factor",
        "required": False,
    },
    "carbon_unit": {
        "label": "Carbon Unit",
        "explanation": (
            "Unit in which the emission factor is expressed, taken from the standard reference. "
            "Format: kgCO2e/<unit> — e.g. kgCO2e/kg, kgCO2e/m3."
        ),
        "doc_slug": "carbon-unit",
        "required": False,
    },
    "conversion_factor": {
        "label": "Conversion Factor",
        "explanation": (
            "Converts your site unit (Unit A) to the standard reference unit (Unit B). "
            "Example: quantity in m³ but emission factor is per kg — enter density, e.g. 2400 for concrete. "
            "Formula: Carbon = Quantity × Conversion Factor × Emission Factor."
        ),
        "doc_slug": "conversion-factor",
        "required": False,
    },
    # ── Recyclability ───────────────────────────────────────────────────────
    "scrap_rate": {
        "label": "Scrap Rate (%)",
        "explanation": (
            "Estimated material wastage on site as a percentage of ordered quantity. "
            "Example: 5 means 5% of ordered material is wasted during construction."
        ),
        "doc_slug": "scrap-rate",
        "required": False,
    },
    "recyclability_percentage": {
        "label": "Recyclability (%)",
        "explanation": (
            "Percentage of this material recoverable at end of life. "
            "Example: 90 for structural steel, 20 for concrete, 0 for landfill materials."
        ),
        "doc_slug": "recyclability",
        "required": False,
    },
    # ── Categorization ──────────────────────────────────────────────────────
    "grade": {
        "label": "Grade",
        "explanation": "Material grade or specification. Example: M25 for concrete, Fe500 for rebar.",
        "doc_slug": "grade",
        "required": False,
    },
    "type": {
        "label": "Type",
        "explanation": "Material category. Example: Concrete, Steel, Masonry, Timber.",
        "doc_slug": "material-type",
        "required": False,
    },
}


UNIT_ALIASES = {
    # mass
    "kg": {"kg", "kgs", "kilogram", "kilograms"},
    "t": {"t", "ton", "tonne", "tonnes", "mt", "metric ton", "metric tonne"},
    "g": {"g", "gram", "grams"},
    "lb": {"lb", "lbs", "pound", "pounds"},
    # volume
    "m3": {"m3", "m³", "cum", "cubic meter", "cubic metre", "cubic meters"},
    "l": {"l", "ltr", "litre", "liter", "liters", "litres"},
    "ml": {"ml", "millilitre", "milliliter"},
    # length
    "m": {"m", "meter", "metre", "meters", "metres"},
    "km": {"km", "kilometer", "kilometre", "kilometers"},
    "mm": {"mm", "millimeter", "millimetre"},
    "cm": {"cm", "centimeter", "centimetre"},
    # area
    "m2": {"m2", "m²", "sqm", "square meter", "square metre"},
    "km2": {"km2", "km²", "square kilometer", "square kilometre"},
    # misc
    "nos": {"nos", "no", "no.", "number", "numbers", "unit", "units", "pcs", "pieces"},
}
