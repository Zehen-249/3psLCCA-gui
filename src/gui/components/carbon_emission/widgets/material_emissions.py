from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QSizePolicy,
    QScrollArea,
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor
import datetime

from ...utils.unit_resolver import analyze_conversion_sympy
from ...utils.definitions import UNIT_DISPLAY


def _fmt_unit(code: str) -> str:
    """Convert raw unit code to display symbol."""
    return UNIT_DISPLAY.get(code.lower(), code) if code else code


def _fmt_carbon_unit(carbon_unit: str) -> str:
    """Normalize stored carbon_unit: fix CO2e subscript and unit symbols."""
    unit = carbon_unit.replace("CO2e", "CO₂e")
    if "/" in unit:
        prefix, denom = unit.rsplit("/", 1)
        return f"{prefix}/{_fmt_unit(denom.strip())}"
    return unit


# Cache for unit analysis — keyed by (unit, carbon_denom, conv_factor)
_analysis_cache: dict = {}


def _cached_analysis(unit: str, carbon_denom: str, conv_factor) -> dict:
    key = (unit, carbon_denom, str(conv_factor))
    if key not in _analysis_cache:
        _analysis_cache[key] = analyze_conversion_sympy(unit, carbon_denom, conv_factor)
    return _analysis_cache[key]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNKS = [
    ("str_foundation", "Foundation"),
    ("str_sub_structure", "Sub Structure"),
    ("str_super_structure", "Super Structure"),
    ("str_misc", "Misc"),
]

# Row background states
BG_INVALID = "#f8d7da"  # red
BG_SUSPICIOUS = "#fff3cd"  # orange/yellow
BG_DISABLED = "#e9ecef"  # gray
TEXT_DARK = "#212529"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_carbon_valid(item) -> bool:
    v = item.get("values", {})
    try:
        emission = float(v.get("carbon_emission", 0) or 0)
        conv = float(v.get("conversion_factor", 0) or 0)
        return emission != 0 and conv > 0
    except (TypeError, ValueError):
        return False


def calc_carbon(item: dict) -> float:
    """Carbon = quantity × conversion_factor × carbon_emission"""
    v = item.get("values", {})
    try:
        return (
            float(v.get("quantity", 0) or 0)
            * float(v.get("conversion_factor", 0) or 0)
            * float(v.get("carbon_emission", 0) or 0)
        )
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Carbon Table Widget
# ---------------------------------------------------------------------------


class CarbonTable(QTableWidget):
    INCLUDED_HEADERS = [
        "Category",
        "Material",
        "Qty (unit)",
        "Conv. Factor",
        "Emission",
        "Total kgCO₂e",
        "Warning",
        "Action",
    ]
    EXCLUDED_HEADERS = [
        "Category",
        "Material",
        "Qty (unit)",
        "Conv. Factor",
        "Emission",
        "Reason",
        "Warning",
        "Action",
    ]

    def __init__(self, is_included: bool, parent=None):
        super().__init__(parent)
        self.is_included = is_included
        headers = self.INCLUDED_HEADERS if is_included else self.EXCLUDED_HEADERS
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionMode(QTableWidget.NoSelection)
        self.verticalHeader().setDefaultSectionSize(35)
        self.verticalHeader().setVisible(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._set_column_widths()

    def _set_column_widths(self):
        widths = (
            [110, 180, 80, 90, 110, 100, 70, 160]
            if self.is_included
            else [110, 160, 80, 90, 110, 100, 90, 160]
        )
        for i, w in enumerate(widths):
            self.setColumnWidth(i, w)

    def sizeHint(self):
        header_h = self.horizontalHeader().height() or 35
        rows_h = self.rowCount() * self.verticalHeader().defaultSectionSize()
        return QSize(super().sizeHint().width(), max(60, header_h + rows_h + 10))

    def minimumSizeHint(self):
        return self.sizeHint()

    def update_height(self):
        self.updateGeometry()

    def set_row_style(self, row: int, color_hex: str):
        bg = QColor(color_hex)
        is_highlighted = color_hex in [BG_INVALID, BG_SUSPICIOUS, BG_DISABLED]
        fg = QColor(TEXT_DARK if is_highlighted else "black")

        for col in range(self.columnCount()):
            it = self.item(row, col)
            if it:
                it.setBackground(bg)
                it.setForeground(fg)
            w = self.cellWidget(row, col)
            if w:
                w.setStyleSheet(
                    f"background-color: {color_hex}; color: {TEXT_DARK if is_highlighted else 'black'};"
                )

    def clear_rows(self):
        self.setRowCount(0)
        self.update_height()


# ---------------------------------------------------------------------------
# MaterialEmissions
# ---------------------------------------------------------------------------


class MaterialEmissions(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self._details_visible = False
        self._frozen = False

        # Outer layout holds only the scroll area, so growing tables never
        # overlap sibling widgets — the scroll area absorbs all extra height.
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(8)

        # Summary Bar
        self.summary_bar = QWidget()
        summary_layout = QHBoxLayout(self.summary_bar)
        self.total_lbl = QLabel("Total: - kgCO₂e")
        self.count_lbl = QLabel("Included: — of — items")
        self.details_btn = QPushButton("Show Details ▼")
        self.details_btn.setFlat(True)
        self.details_btn.clicked.connect(self._toggle_details)
        summary_layout.addWidget(self.total_lbl)
        summary_layout.addWidget(self._vline())
        summary_layout.addWidget(self.count_lbl)
        summary_layout.addStretch()
        summary_layout.addWidget(self.details_btn)
        main_layout.addWidget(self.summary_bar)

        # Details Row
        self.details_widget = QWidget()
        details_layout = QHBoxLayout(self.details_widget)
        self.foundation_lbl = QLabel("Foundation: —")
        self.sub_lbl = QLabel("Sub Structure: —")
        self.super_lbl = QLabel("Super Structure: —")
        self.misc_lbl = QLabel("Misc: —")
        for lbl in [self.foundation_lbl, self.sub_lbl, self.super_lbl, self.misc_lbl]:
            details_layout.addWidget(lbl)
            details_layout.addWidget(self._vline())
        details_layout.addStretch()
        self.details_widget.setVisible(False)
        main_layout.addWidget(self.details_widget)
        main_layout.addWidget(self._hline())

        main_layout.addWidget(self._section_label("Included in Carbon Calculation"))
        self.included_table = CarbonTable(is_included=True)
        main_layout.addWidget(self.included_table)
        main_layout.addWidget(self._hline())

        main_layout.addWidget(self._section_label("Excluded from Carbon Calculation"))
        self.excluded_table = CarbonTable(is_included=False)
        main_layout.addWidget(self.excluded_table)
        main_layout.addStretch()

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(f"<b>{text}</b>")
        lbl.setStyleSheet("font-size: 13px;")
        return lbl

    def _hline(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setFrameShadow(QFrame.Sunken)
        return f

    def _vline(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.VLine)
        f.setFrameShadow(QFrame.Sunken)
        return f

    def _toggle_details(self):
        self._details_visible = not self._details_visible
        self.details_widget.setVisible(self._details_visible)
        self.details_btn.setText(
            "Hide Details ▲" if self._details_visible else "Show Details ▼"
        )

    def on_refresh(self):
        if not self.controller or not getattr(self.controller, "engine", None):
            return

        included_items = []
        excluded_items = []
        cat_totals = {label: 0.0 for _, label in CHUNKS}
        total_carbon = 0.0
        total_count = 0
        included_count = 0

        for chunk_id, category in CHUNKS:
            data = self.controller.engine.fetch_chunk(chunk_id) or {}
            for comp_name, items in data.items():
                for idx, item in enumerate(items):
                    if item.get("state", {}).get("in_trash", False):
                        continue

                    total_count += 1
                    v = item.get("values", {})
                    state = item.get("state", {})

                    # Target denominator for carbon is usually the unit after the slash
                    carbon_unit = v.get("carbon_unit", "")
                    carbon_denom = (
                        carbon_unit.split("/")[-1] if "/" in carbon_unit else ""
                    )

                    # Unit resolver analysis (cached — same inputs always yield same result)
                    analysis = _cached_analysis(
                        v.get("unit", ""), carbon_denom, v.get("conversion_factor", 1)
                    )

                    valid = is_carbon_valid(item)
                    is_included_flag = state.get("included_in_carbon_emission", True)
                    is_confirmed = state.get("carbon_conversion_confirmed", False)
                    suspicious = analysis["is_suspicious"] and not is_confirmed

                    if valid and is_included_flag and not suspicious:
                        included_count += 1
                        carbon = calc_carbon(item)
                        total_carbon += carbon
                        cat_totals[category] += carbon
                        included_items.append(
                            (category, chunk_id, comp_name, idx, item, carbon, analysis)
                        )
                    else:
                        reason = (
                            "Missing Data"
                            if not valid
                            else ("Suspicious Data" if suspicious else "User Excluded")
                        )
                        excluded_items.append(
                            (category, chunk_id, comp_name, idx, item, reason, analysis)
                        )

        self._populate_included(included_items)
        self._populate_excluded(excluded_items)
        self._update_summary(total_carbon, included_count, total_count, cat_totals)

    def _populate_included(self, items):
        t = self.included_table
        t.setUpdatesEnabled(False)
        t.clear_rows()
        for category, chunk_id, comp_name, idx, item, carbon, analysis in items:
            v = item.get("values", {})
            row = t.rowCount()
            t.insertRow(row)

            t.setItem(row, 0, QTableWidgetItem(category))
            t.setItem(row, 1, QTableWidgetItem(v.get("material_name", "")))
            t.setItem(
                row, 2, QTableWidgetItem(f"{v.get('quantity', 0)} {_fmt_unit(v.get('unit', ''))}")
            )
            t.setItem(row, 3, QTableWidgetItem(str(v.get("conversion_factor", 1))))
            t.setItem(
                row,
                4,
                QTableWidgetItem(
                    f"{v.get('carbon_emission', 0)} {_fmt_carbon_unit(v.get('carbon_unit', ''))}"
                ),
            )

            carbon_item = QTableWidgetItem(f"{carbon:.2f}")
            carbon_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(row, 5, carbon_item)

            # Persistent Warnings: Check for zero qty or if the confirmed factor is still suspicious
            warnings = []
            if float(v.get("quantity", 0) or 0) == 0:
                warnings.append("Zero Qty")
            if analysis["is_suspicious"]:
                warnings.append("⚠️ Conversion Factor seems incorrect.")

            t.setItem(row, 6, QTableWidgetItem(", ".join(warnings)))

            edit_btn = QPushButton("Edit EF")
            edit_btn.clicked.connect(
                lambda _, ci=chunk_id, cn=comp_name, i=idx, it=item: self._open_emission_edit(ci, cn, i, it)
            )
            excl_btn = QPushButton("Exclude")
            excl_btn.clicked.connect(
                lambda _, ci=chunk_id, cn=comp_name, i=idx: self._toggle_inclusion(ci, cn, i, False)
            )
            excl_btn.setEnabled(not self._frozen)
            t.setCellWidget(row, 7, self._btn_container(edit_btn, excl_btn))

        t.update_height()
        t.setUpdatesEnabled(True)

    def _populate_excluded(self, items):
        t = self.excluded_table
        t.setUpdatesEnabled(False)
        t.clear_rows()
        for category, chunk_id, comp_name, idx, item, reason, analysis in items:
            v = item.get("values", {})
            row = t.rowCount()
            t.insertRow(row)

            t.setItem(row, 0, QTableWidgetItem(category))
            t.setItem(row, 1, QTableWidgetItem(v.get("material_name", "")))
            t.setItem(
                row, 2, QTableWidgetItem(f"{v.get('quantity', 0)} {_fmt_unit(v.get('unit', ''))}")
            )
            t.setItem(row, 3, QTableWidgetItem(str(v.get("conversion_factor", 1))))
            t.setItem(
                row,
                4,
                QTableWidgetItem(
                    f"{v.get('carbon_emission', 0)} {_fmt_carbon_unit(v.get('carbon_unit', ''))}"
                ),
            )
            t.setItem(row, 5, QTableWidgetItem(reason))

            warn_text = "! Factor" if reason == "Suspicious Data" else ""
            t.setItem(row, 6, QTableWidgetItem(warn_text))

            edit_btn = QPushButton("Edit EF")
            edit_btn.clicked.connect(
                lambda _, ci=chunk_id, cn=comp_name, i=idx, it=item: self._open_emission_edit(ci, cn, i, it)
            )

            if reason in ["Missing Data", "Suspicious Data"]:
                t.set_row_style(
                    row, BG_INVALID if reason == "Missing Data" else BG_SUSPICIOUS
                )
                t.setCellWidget(row, 7, self._btn_container(edit_btn))
            else:
                incl_btn = QPushButton("Include")
                incl_btn.clicked.connect(
                    lambda _, ci=chunk_id, cn=comp_name, i=idx: self._toggle_inclusion(ci, cn, i, True)
                )
                incl_btn.setEnabled(not self._frozen)
                t.setCellWidget(row, 7, self._btn_container(edit_btn, incl_btn))
        t.update_height()
        t.setUpdatesEnabled(True)

    def _update_summary(
        self, total: float, included: int, total_count: int, cat_totals: dict
    ):
        self.total_lbl.setText(f"Total: {total:,.2f} kgCO₂e")
        self.count_lbl.setText(f"Included: {included} of {total_count} items")
        self.foundation_lbl.setText(
            f"Foundation: {cat_totals.get('Foundation', 0):,.2f}"
        )
        self.sub_lbl.setText(
            f"Sub Structure: {cat_totals.get('Sub Structure', 0):,.2f}"
        )
        self.super_lbl.setText(
            f"Super Structure: {cat_totals.get('Super Structure', 0):,.2f}"
        )
        self.misc_lbl.setText(f"Misc: {cat_totals.get('Misc', 0):,.2f}")

    def _toggle_inclusion(
        self, chunk_id: str, comp_name: str, data_index: int, include: bool
    ):
        data = self.controller.engine.fetch_chunk(chunk_id) or {}
        if comp_name in data and data_index < len(data[comp_name]):
            data[comp_name][data_index]["state"][
                "included_in_carbon_emission"
            ] = include
            self.controller.engine.stage_update(chunk_name=chunk_id, data=data)
            self._mark_dirty()
            QTimer.singleShot(0, self.on_refresh)

    def _btn_container(self, *buttons) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(4)
        for btn in buttons:
            h.addWidget(btn)
        return w

    def _open_emission_edit(
        self, chunk_id: str, comp_name: str, data_index: int, item: dict
    ):
        from ...structure.widgets.material_dialog import MaterialDialog
        dialog = MaterialDialog(comp_name, parent=self, data=item, emissions_only=True)
        if dialog.exec():
            vals = dialog.get_values()
            data = self.controller.engine.fetch_chunk(chunk_id) or {}
            if comp_name in data and data_index < len(data[comp_name]):
                target = data[comp_name][data_index]
                target["values"]["carbon_emission"] = vals.get("carbon_emission", 0.0)
                target["values"]["carbon_unit"] = vals.get("carbon_unit", "")
                target["values"]["conversion_factor"] = vals.get("conversion_factor", 1.0)
                target["state"]["included_in_carbon_emission"] = vals.get(
                    "included_in_carbon_emission", True
                )
                target["state"]["carbon_conversion_confirmed"] = True
                target["meta"]["modified_on"] = datetime.datetime.now().isoformat()
                self.controller.engine.stage_update(chunk_name=chunk_id, data=data)
                self._mark_dirty()
                QTimer.singleShot(0, self.on_refresh)

    def _mark_dirty(self):
        if self.controller and self.controller.engine:
            import time

            eng = self.controller.engine
            eng._last_keystroke_time = time.time()
            eng._has_unsaved_changes = True
            try:
                eng.on_dirty(True)
            except:
                pass

    def _compute(self) -> dict:
        """
        Core calculation logic shared by on_refresh(), validate(), and get_data().
        Returns raw computed data without touching any UI.
        """
        cat_totals = {label: 0.0 for _, label in CHUNKS}
        included_items = []
        excluded_items = []
        total_carbon = 0.0
        total_count = 0
        included_count = 0

        if not self.controller or not getattr(self.controller, "engine", None):
            return {
                "total_carbon": 0.0,
                "cat_totals": cat_totals,
                "included_count": 0,
                "total_count": 0,
                "included_items": [],
                "excluded_items": [],
            }

        for chunk_id, category in CHUNKS:
            data = self.controller.engine.fetch_chunk(chunk_id) or {}
            for comp_name, items in data.items():
                for idx, item in enumerate(items):
                    if item.get("state", {}).get("in_trash", False):
                        continue
                    total_count += 1
                    v = item.get("values", {})
                    state = item.get("state", {})
                    carbon_unit = v.get("carbon_unit", "")
                    carbon_denom = carbon_unit.split("/")[-1] if "/" in carbon_unit else ""
                    analysis = _cached_analysis(
                        v.get("unit", ""), carbon_denom, v.get("conversion_factor", 1)
                    )
                    valid = is_carbon_valid(item)
                    is_included_flag = state.get("included_in_carbon_emission", True)
                    is_confirmed = state.get("carbon_conversion_confirmed", False)
                    suspicious = analysis["is_suspicious"] and not is_confirmed

                    if valid and is_included_flag and not suspicious:
                        included_count += 1
                        carbon = calc_carbon(item)
                        total_carbon += carbon
                        cat_totals[category] += carbon
                        included_items.append(
                            (category, chunk_id, comp_name, idx, item, carbon, analysis)
                        )
                    else:
                        reason = (
                            "Missing Data"
                            if not valid
                            else ("Suspicious Data" if suspicious else "User Excluded")
                        )
                        excluded_items.append(
                            (category, chunk_id, comp_name, idx, item, reason, analysis)
                        )

        return {
            "total_carbon": total_carbon,
            "cat_totals": cat_totals,
            "included_count": included_count,
            "total_count": total_count,
            "included_items": included_items,
            "excluded_items": excluded_items,
        }

    def validate(self) -> dict:
        result = self._compute()
        warnings = []

        if result["total_count"] == 0:
            warnings.append(
                "No materials found — add items in the Construction Work Data section."
            )
        elif result["total_carbon"] == 0.0:
            warnings.append(
                f"Total material carbon is 0 kgCO₂e — "
                f"{result['included_count']} of {result['total_count']} items are included."
            )

        missing = sum(
            1 for *_, reason, _ in result["excluded_items"] if reason == "Missing Data"
        )
        suspicious = sum(
            1 for *_, reason, _ in result["excluded_items"] if reason == "Suspicious Data"
        )
        if missing:
            warnings.append(
                f"{missing} item{'s' if missing != 1 else ''} excluded — missing emission factor data."
            )
        if suspicious:
            warnings.append(
                f"{suspicious} item{'s' if suspicious != 1 else ''} excluded — "
                f"suspicious conversion factor (not confirmed)."
            )

        return {"errors": [], "warnings": warnings}

    def get_data(self) -> dict:
        result = self._compute()
        included = [
            {
                "category": cat,
                "component": comp,
                "material": item.get("values", {}).get("material_name", ""),
                "quantity": float(item.get("values", {}).get("quantity", 0) or 0),
                "unit": item.get("values", {}).get("unit", ""),
                "conversion_factor": float(
                    item.get("values", {}).get("conversion_factor", 1) or 1
                ),
                "carbon_emission": float(
                    item.get("values", {}).get("carbon_emission", 0) or 0
                ),
                "carbon_unit": item.get("values", {}).get("carbon_unit", ""),
                "total_kgCO2e": carbon,
            }
            for cat, chunk_id, comp, idx, item, carbon, analysis in result["included_items"]
        ]
        return {
            "chunk": "material_emissions_data",
            "data": {
                "included_items": included,
                "cat_totals": result["cat_totals"],
                "total_kgCO2e": result["total_carbon"],
                "included_count": result["included_count"],
                "total_count": result["total_count"],
            },
        }

    def freeze(self, frozen: bool = True):
        self._frozen = frozen
        self.on_refresh()  # repopulate so button states reflect new frozen state

    def showEvent(self, event):
        super().showEvent(event)
        self.on_refresh()
