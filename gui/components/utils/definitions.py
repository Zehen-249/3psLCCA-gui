# ---------------------------------------------------------------------------
# utils/definitions.py
# ---------------------------------------------------------------------------


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
                # "mm": {
                #     "name": "mm , Millimeter",
                #     "example": "Rebar diameter, plate thickness",
                # },
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


# ---------------------------------------------------------------------------
# SI unit system for the Add Material dialog
# ---------------------------------------------------------------------------

# Maps unit code → how many SI base units it equals
# (e.g. tonne → 1000.0 means 1 tonne = 1000 kg)
UNIT_TO_SI = {
    # Mass (SI base: kg)
    "kg":    1.0,
    "tonne": 1000.0,
    "mt":    1000.0,
    "q":     100.0,
    # Length (SI base: m)
    "m":     1.0,
    "rm":    1.0,
    "ft":    0.3048,
    # Area (SI base: m²)
    "m2":    1.0,
    "sqm":   1.0,
    "sqft":  0.09290304,
    "sqyd":  0.83612736,
    # Volume (SI base: m³)
    "m3":    1.0,
    "cum":   1.0,
    "cft":   0.028316846,
    # Count (dimensionless, base: nos)
    "nos":   1.0,
    "pcs":   1.0,
    "set":   1.0,
    "ls":    1.0,
}

# Maps unit code → its physical dimension
UNIT_DIMENSION = {
    "kg":    "Mass",   "tonne": "Mass",   "mt":    "Mass",   "q":     "Mass",
    "m":     "Length", "rm":    "Length", "ft":    "Length",
    "m2":    "Area",   "sqm":   "Area",   "sqft":  "Area",   "sqyd":  "Area",
    "m3":    "Volume", "cum":   "Volume", "cft":   "Volume",
    "nos":   "Count",  "pcs":   "Count",  "set":   "Count",  "ls":    "Count",
}

# Maps dimension name → its SI base unit code
SI_BASE_UNITS = {
    "Mass":   "kg",
    "Length": "m",
    "Area":   "m2",
    "Volume": "m3",
    "Count":  "nos",
}


# Maps raw unit codes to their pretty display symbols used across the UI.
# Add or change a symbol here and every widget picks it up automatically.
UNIT_DISPLAY: dict[str, str] = {
    # Area
    "m2":    "m²",
    "sqm":   "m²",
    "sqft":  "sq.ft",
    "sqyd":  "sq.yd",
    # Volume
    "m3":    "m³",
    "cum":   "m³",
    "cft":   "ft³",
    # Mass
    "t":     "t",
    "tonne": "t",
    "mt":    "MT",
    "q":     "q",
    # Length
    "rm":    "RM",
    # Count
    "nos":   "Nos.",
    "pcs":   "Pcs.",
    "ls":    "L.S.",
}


STRUCTURE_CHUNKS = [
    ("str_foundation", "Foundation"),
    ("str_sub_structure", "Sub Structure"),
    ("str_super_structure", "Super Structure"),
    ("str_misc", "Misc"),
]


# Vehicle presets — EF values from IPCC AR5 (WGIII, 2014) / matching CSV source.
# gross_weight = fully loaded vehicle weight (vehicle tare + full payload).
# capacity     = net payload capacity (cargo only).
# empty_weight is derived at runtime: gross_weight - capacity.
DEFAULT_VEHICLES = {
    "Light Duty Vehicle (<4.5T)": {
        "name": "Light Duty Vehicle (<4.5T)",
        "capacity": 2.5,
        "gross_weight": 3.5,
        "emission_factor": 1.2,
    },
    "HDV Small (4.5–9T)": {
        "name": "HDV Small (4.5–9T)",
        "capacity": 7.0,
        "gross_weight": 9.5,
        "emission_factor": 0.7,
    },
    "HDV Medium (9–12T)": {
        "name": "HDV Medium (9–12T)",
        "capacity": 10.5,
        "gross_weight": 14.0,
        "emission_factor": 0.55,
    },
    "HDV Large (>12T)": {
        "name": "HDV Large (>12T)",
        "capacity": 24.5,
        "gross_weight": 35.0,
        "emission_factor": 0.19,
    },
}
