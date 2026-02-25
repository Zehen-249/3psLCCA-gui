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


# Add to definitions.py after ALL_CONSTRUCTION_UNITS

UNIT_TO_KG = {
    # Mass — base unit: kg
    "kg": 1.0,  # Kilogram
    "kgs": 1.0,  # Kilograms (plural)
    "g": 0.001,  # Gram
    "gm": 0.001,  # Gram (alternate)
    "gram": 0.001,  # Gram (full name)
    "t": 1000.0,  # Metric Tonne
    "tonne": 1000.0,  # Metric Tonne (full name)
    "mt": 1000.0,  # Metric Tonne (abbreviation)
    "ton": 1000.0,  # Tonne (common usage)
    "quintal": 100.0,  # Quintal (100 kg)
    "q": 100.0,  # Quintal (shorthand)
    "bag": 50.0,  # Cement Bag (standard 50 kg)
    "lb": 0.453592,  # Pound (Imperial)
    "lbs": 0.453592,  # Pounds (plural)
    "pound": 0.453592,  # Pound (full name)
}


class ConstructionUnits:
    def __init__(self):
        # Your professional dictionary
        self.units = {
            "Length": {
                "mm": {
                    "name": "mm , Millimeter",
                    "example": "Rebar diameter, plate thickness",
                },
                "m": {"name": "m , Meter", "example": "Wall length, piping, conduit"},
                "rm": {
                    "name": "RM , Running Meter",
                    "example": "Pipes, cables, skirting",
                },
                "ft": {"name": "ft , Foot", "example": "Residential layout dimensions"},
            },
            "Area": {
                "m2": {
                    "name": "m² , Square Meter",
                    "example": "Plastering, flooring, shuttering",
                },
                "sqm": {"name": "sqm , Square Meter", "example": "Tile work, painting"},
                "sqft": {"name": "sq.ft , Square Foot", "example": "Flat sale area"},
                "sqyd": {"name": "sq.yd , Square Yard", "example": "Land purchase"},
            },
            "Volume": {
                "m3": {
                    "name": "m³ , Cubic Meter",
                    "example": "Concrete, excavation, brickwork",
                },
                "cum": {
                    "name": "cum , Cubic Meter",
                    "example": "Concrete supply billing",
                },
                "cft": {
                    "name": "cft , Cubic Foot",
                    "example": "Sand, aggregates supply",
                },
            },
            "Mass": {
                "kg": {"name": "kg , Kilogram", "example": "Reinforcement steel"},
                "tonne": {
                    "name": "Tonne , Metric Tonne",
                    "example": "Bulk steel purchase",
                },
                "mt": {
                    "name": "MT , Metric Tonne",
                    "example": "Structural steel billing",
                },
                "q": {"name": "q , Quintal", "example": "Shorthand for 100kg"},
                "bag": {"name": "Bag , 50kg", "example": "Cement bag count"},
            },
            "Count": {
                "nos": {
                    "name": "Nos. , Numbers",
                    "example": "Doors, windows, fixtures",
                },
                "pcs": {"name": "Pcs. , Pieces", "example": "Sanitary fittings"},
                "set": {
                    "name": "Set , Equipment",
                    "example": "Pump set, equipment set",
                },
                "ls": {"name": "L.S. , Lump Sum", "example": "General work items"},
            },
        }

    def get_dropdown_data(self):
        """Returns a list of tuples: (Code, Name, Example)"""
        data = []
        for cat, units in self.units.items():
            for code, info in units.items():
                data.append((code, info["name"], info["example"]))
        return data


_CONSTRUCTION_UNITS = ConstructionUnits()
# New constant for the UI
UNIT_DROPDOWN_DATA = _CONSTRUCTION_UNITS.get_dropdown_data()


DEFAULT_VEHICLES = {
    "Small Truck (5T)": {
        "name": "Small Truck (5T)",
        "capacity": 5.0,
        "empty_weight": 2.0,
        "payload": 3.0,
        "emission_factor": 0.062,
    },
    "Medium Truck (10T)": {
        "name": "Medium Truck (10T)",
        "capacity": 10.0,
        "empty_weight": 4.0,
        "payload": 6.0,
        "emission_factor": 0.055,
    },
    "Large Truck (20T)": {
        "name": "Large Truck (20T)",
        "capacity": 20.0,
        "empty_weight": 6.5,
        "payload": 13.5,
        "emission_factor": 0.048,
    },
    "Trailer (40T)": {
        "name": "Trailer (40T)",
        "capacity": 40.0,
        "empty_weight": 12.0,
        "payload": 28.0,
        "emission_factor": 0.038,
    },
    "Mini Truck (2T)": {
        "name": "Mini Truck (2T)",
        "capacity": 2.0,
        "empty_weight": 1.0,
        "payload": 1.0,
        "emission_factor": 0.071,
    },
}
