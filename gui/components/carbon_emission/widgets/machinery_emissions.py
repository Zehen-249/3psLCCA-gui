"""
gui/components/carbon_emission/widgets/machinery_emissions.py

Chunk: machinery_emissions_data

Two modes toggled by radio buttons:
  - Detailed Equipment List  (table with per-row calculation)
  - Lump Sum                 (electricity + fuel — built via build_form)

Grand total shown at top and bottom.
Currency label pulled from general_info chunk.
"""

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from gui.components.base_widget import ScrollableForm
from gui.components.utils.form_builder.form_definitions import FieldDef, Section
from gui.components.utils.form_builder.form_builder import build_form
from gui.components.utils.remarks_editor import RemarksEditor

CHUNK = "machinery_emissions_data"
BASE_DOCS_URL = "https://yourdocs.com/carbon/machinery/"

ENERGY_SOURCES = [
    "Diesel",
    "Electricity (Grid)",
    "Electricity (Solar/Renewable)",
    "Other",
]

EF_DEFAULTS = {
    "Diesel": 2.69,
    "Electricity (Grid)": 0.71,
    "Electricity (Solar/Renewable)": 0.0,
    "Other": 0.0,
}

RATE_SUFFIX = {
    "Diesel": " l/hr",
    "Electricity (Grid)": " kW",
    "Electricity (Solar/Renewable)": " kW",
    "Other": " units/hr",
}

CONSUMPTION_UNIT = {
    "Diesel": "litres",
    "Electricity (Grid)": "kWh",
    "Electricity (Solar/Renewable)": "kWh",
    "Other": "units",
}

DEFAULT_MACHINERY_DATA = [
    {"name": "Backhoe loader (JCB)", "source": "Diesel", "rate": 5.0, "ef": 2.69},
    {
        "name": "Bar bending machine",
        "source": "Electricity (Grid)",
        "rate": 3.0,
        "ef": 0.71,
    },
    {
        "name": "Bar cutting machine",
        "source": "Electricity (Grid)",
        "rate": 4.0,
        "ef": 0.71,
    },
    {"name": "Bitumen boiler", "source": "Diesel", "rate": 1.0, "ef": 2.69},
    {"name": "Bitumen sprayer", "source": "Diesel", "rate": 5.0, "ef": 2.69},
    {"name": "Concrete pump", "source": "Diesel", "rate": 12.0, "ef": 2.69},
    {"name": "Crane (crawler)", "source": "Diesel", "rate": 12.0, "ef": 2.69},
    {"name": "Crane (mobile)", "source": "Diesel", "rate": 8.0, "ef": 2.69},
    {"name": "Dewatering pump", "source": "Diesel", "rate": 2.0, "ef": 2.69},
    {"name": "DG set", "source": "Diesel", "rate": 4.0, "ef": 2.69},
    {"name": "Grouting mixer", "source": "Electricity (Grid)", "rate": 1.0, "ef": 0.71},
    {"name": "Grouting pump", "source": "Electricity (Grid)", "rate": 5.0, "ef": 0.71},
    {"name": "Hydraulic excavator", "source": "Diesel", "rate": 14.0, "ef": 2.69},
    {
        "name": "Hydraulic stressing jack",
        "source": "Electricity (Grid)",
        "rate": 3.0,
        "ef": 0.71,
    },
    {
        "name": "Needle Vibrator",
        "source": "Electricity (Grid)",
        "rate": 1.0,
        "ef": 0.71,
    },
    {"name": "Paver finisher", "source": "Diesel", "rate": 7.0, "ef": 2.69},
    {"name": "Road roller", "source": "Diesel", "rate": 4.0, "ef": 2.69},
    {
        "name": "Rotary piling rig/Hydraulic piling rig",
        "source": "Diesel",
        "rate": 15.0,
        "ef": 2.69,
    },
    {
        "name": "Site office (If Grid electricity is used)",
        "source": "Electricity (Grid)",
        "rate": 4.0,
        "ef": 0.71,
    },
    {
        "name": "Welding machine",
        "source": "Electricity (Grid)",
        "rate": 4.0,
        "ef": 0.71,
    },
]

# ── Field definitions — passed to build_form ──────────────────────────────────

LUMPSUM_ELEC_FIELDS = [
    Section("Electricity Consumption"),
    FieldDef(
        "elec_consumption_per_day",
        "Electricity Consumption per Day",
        "Total electricity consumed per working day across all equipment.",
        "float",
        options=(0.0, 1e12, 2),
        unit="kWh/day",
    ),
    FieldDef(
        "elec_days",
        "Number of Days",
        "Total number of working days for electricity consumption.",
        "int",
        options=(0, 9999),
        unit="days",
    ),
    FieldDef(
        "elec_ef",
        "Emission Factor",
        "Grid electricity emission factor (kg CO2e per kWh).",
        "float",
        options=(0.0, 999.0, 4),
        unit="kg CO2e/kWh",
    ),
]

LUMPSUM_FUEL_FIELDS = [
    Section("Fuel (Diesel) Consumption"),
    FieldDef(
        "fuel_consumption_per_day",
        "Fuel Consumption per Day",
        "Total diesel/fuel consumed per working day across all equipment.",
        "float",
        options=(0.0, 1e12, 2),
        unit="litres/day",
    ),
    FieldDef(
        "fuel_days",
        "Number of Days",
        "Total number of working days for fuel consumption.",
        "int",
        options=(0, 9999),
        unit="days",
    ),
    FieldDef(
        "fuel_ef",
        "Emission Factor",
        "Diesel emission factor (kg CO2e per litre).",
        "float",
        options=(0.0, 999.0, 4),
        unit="kg CO2e/litre",
    ),
]

_LUMPSUM_KEYS = [
    ("elec_consumption_per_day", 0.0),
    ("elec_days", 0),
    ("elec_ef", 0.71),
    ("fuel_consumption_per_day", 0.0),
    ("fuel_days", 0),
    ("fuel_ef", 2.69),
]


# ── Equipment row ─────────────────────────────────────────────────────────────


class _EquipmentRow:
    """All cell widgets for one equipment table row."""

    def __init__(self, on_change, on_delete):
        self.name = QLineEdit()
        self.name.setPlaceholderText("Equipment name")
        self.name.textChanged.connect(on_change)

        self.source = QComboBox()
        self.source.addItems(ENERGY_SOURCES)
        self.source.currentIndexChanged.connect(self._on_source_changed)
        self.source.currentIndexChanged.connect(on_change)

        self.rate = QDoubleSpinBox()
        self.rate.setRange(0.0, 99999.0)
        self.rate.setDecimals(2)
        self.rate.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.rate.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.rate.valueChanged.connect(on_change)

        self.hrs = QDoubleSpinBox()
        self.hrs.setRange(0.0, 24.0)
        self.hrs.setDecimals(1)
        self.hrs.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.hrs.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.hrs.valueChanged.connect(on_change)

        self.days = QSpinBox()
        self.days.setRange(0, 9999)
        self.days.setButtonSymbols(QSpinBox.NoButtons)
        self.days.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.days.valueChanged.connect(on_change)

        self.ef = QDoubleSpinBox()
        self.ef.setRange(0.0, 999.0)
        self.ef.setDecimals(4)
        self.ef.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.ef.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.ef.valueChanged.connect(on_change)

        self.consumption_item = QTableWidgetItem("0.00")
        self.consumption_item.setFlags(Qt.ItemIsEnabled)
        self.consumption_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.emissions_item = QTableWidgetItem("0.00")
        self.emissions_item.setFlags(Qt.ItemIsEnabled)
        self.emissions_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.btn_delete = QPushButton("✕")
        self.btn_delete.setFixedWidth(32)
        self.btn_delete.setFixedHeight(28)
        self.btn_delete.setToolTip("Remove this row")
        self.btn_delete.clicked.connect(on_delete)

        # Blank row: suffix only, EF stays 0 until user picks source
        self._is_new = True
        self._loading = False
        self.rate.setSuffix(RATE_SUFFIX.get(ENERGY_SOURCES[0], ""))

    def _on_source_changed(self):
        src = self.source.currentText()
        self.rate.setSuffix(RATE_SUFFIX.get(src, ""))
        if not self._loading:
            self._is_new = False
            self.ef.blockSignals(True)
            self.ef.setValue(EF_DEFAULTS.get(src, 0.0))
            self.ef.blockSignals(False)

    def recalculate(self) -> float:
        consumption = self.rate.value() * self.hrs.value() * self.days.value()
        emissions = consumption * self.ef.value()
        src = self.source.currentText()
        unit = CONSUMPTION_UNIT.get(src, "units")
        self.consumption_item.setText(f"{consumption:,.2f} {unit}")
        self.emissions_item.setText(f"{emissions:,.2f}")
        return emissions

    def to_dict(self) -> dict:
        return {
            "name": self.name.text(),
            "source": self.source.currentText(),
            "rate": float(self.rate.value()),
            "hrs": float(self.hrs.value()),
            "days": int(self.days.value()),
            "ef": float(self.ef.value()),
        }

    def load_dict(self, d: dict):
        self._loading = True
        self._is_new = False
        try:
            src = d.get("source", "Diesel")

            self.name.blockSignals(True)
            self.name.setText(str(d.get("name", "")))
            self.name.blockSignals(False)

            idx = self.source.findText(src)
            self.source.blockSignals(True)
            self.source.setCurrentIndex(max(0, idx))
            self.source.blockSignals(False)

            self.rate.setSuffix(RATE_SUFFIX.get(src, ""))
            self.rate.blockSignals(True)
            self.rate.setValue(float(d.get("rate", 0.0)))
            self.rate.blockSignals(False)

            self.hrs.blockSignals(True)
            self.hrs.setValue(float(d.get("hrs", 0.0)))
            self.hrs.blockSignals(False)

            self.days.blockSignals(True)
            self.days.setValue(int(d.get("days", 0)))
            self.days.blockSignals(False)

            self.ef.blockSignals(True)
            self.ef.setValue(float(d.get("ef", 0.0)))
            self.ef.blockSignals(False)
        finally:
            self._loading = False


# ── Detailed equipment table ──────────────────────────────────────────────────


class _DetailedTable(QWidget):
    HEADERS = [
        "Equipment Name",
        "Energy Source",
        "Fuel / Power Rating",
        "Avg Hrs/Day",
        "No. of Days",
        "EF (kg CO2e/unit)",
        "Consumption",
        "Emissions (kg CO2e)",
        "",
    ]

    def __init__(self, on_change, parent=None):
        super().__init__(parent)
        self._on_change = on_change
        self._rows: list[_EquipmentRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Default days — QFormLayout style matching build_form output
        days_container = QWidget()
        days_form = QFormLayout(days_container)
        days_form.setContentsMargins(0, 0, 0, 4)
        days_form.setSpacing(8)
        days_form.setLabelAlignment(Qt.AlignLeft)
        days_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        self._default_days = QSpinBox()
        self._default_days.setRange(0, 9999)
        self._default_days.setButtonSymbols(QSpinBox.NoButtons)
        self._default_days.setSuffix("  days")
        self._default_days.setMinimumWidth(120)
        self._default_days.setMaximumWidth(160)
        self._default_days.setToolTip("Set then click Apply to All Rows")

        days_field_row = QWidget()
        days_field_layout = QHBoxLayout(days_field_row)
        days_field_layout.setContentsMargins(0, 0, 0, 0)
        days_field_layout.setSpacing(8)
        days_field_layout.addWidget(self._default_days)
        btn_apply = QPushButton("Apply to All Rows")
        btn_apply.setFixedHeight(28)
        btn_apply.clicked.connect(self._apply_default_days)
        days_field_layout.addWidget(btn_apply)
        days_field_layout.addStretch()
        days_form.addRow("Default No. of Days:", days_field_row)
        layout.addWidget(days_container)

        # Table
        self._table = QTableWidget(0, len(self.HEADERS))
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(self.HEADERS) - 1):
            hh.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(len(self.HEADERS) - 1, QHeaderView.Fixed)
        hh.resizeSection(len(self.HEADERS) - 1, 40)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(self._table)

        # Subtotals
        sub_layout = QHBoxLayout()
        self._lbl_diesel_sub = QLabel("Diesel: 0.00 kg CO2e")
        self._lbl_elec_sub = QLabel("Electricity: 0.00 kg CO2e")
        self._lbl_detail_total = QLabel("Subtotal: 0.00 kg CO2e")
        bold = QFont()
        bold.setBold(True)
        self._lbl_detail_total.setFont(bold)
        sub_layout.addWidget(self._lbl_diesel_sub)
        sub_layout.addSpacing(20)
        sub_layout.addWidget(self._lbl_elec_sub)
        sub_layout.addStretch()
        sub_layout.addWidget(self._lbl_detail_total)
        layout.addLayout(sub_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("＋ Add Equipment")
        btn_add.setMinimumHeight(35)
        btn_add.clicked.connect(self._add_blank_row)
        btn_defaults = QPushButton("Load Defaults")
        btn_defaults.setMinimumHeight(35)
        btn_defaults.clicked.connect(self._load_defaults)
        btn_clear = QPushButton("Clear All")
        btn_clear.setMinimumHeight(35)
        btn_clear.clicked.connect(self._clear_all)
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_defaults)
        btn_layout.addWidget(btn_clear)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _apply_default_days(self):
        for row in self._rows:
            row.days.setValue(self._default_days.value())
        self._recalculate()

    def _add_blank_row(self, d: dict | None = None):
        row_idx = len(self._rows)

        def on_change():
            self._recalculate()

        def on_delete(r=row_idx):
            self._delete_row(r)

        eq = _EquipmentRow(on_change=on_change, on_delete=on_delete)
        if d:
            eq.load_dict(d)
        self._rows.append(eq)
        self._table.insertRow(row_idx)
        self._table.setRowHeight(row_idx, 36)
        self._table.setCellWidget(row_idx, 0, eq.name)
        self._table.setCellWidget(row_idx, 1, eq.source)
        self._table.setCellWidget(row_idx, 2, eq.rate)
        self._table.setCellWidget(row_idx, 3, eq.hrs)
        self._table.setCellWidget(row_idx, 4, eq.days)
        self._table.setCellWidget(row_idx, 5, eq.ef)
        self._table.setItem(row_idx, 6, eq.consumption_item)
        self._table.setItem(row_idx, 7, eq.emissions_item)
        self._table.setCellWidget(row_idx, 8, eq.btn_delete)
        self._update_height()
        self._recalculate()

    def _delete_row(self, row_idx: int):
        eq = self._rows[row_idx]
        actual = self._rows.index(eq)
        self._table.removeRow(actual)
        self._rows.pop(actual)
        for i, r in enumerate(self._rows):
            r.btn_delete.clicked.disconnect()
            r.btn_delete.clicked.connect(
                lambda checked=False, idx=i: self._delete_row(idx)
            )
        self._recalculate()

    def _load_defaults(self):
        if self._rows:
            reply = QMessageBox.question(
                self,
                "Load Defaults",
                "This will replace all current rows with the default equipment list.\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._clear_all(confirm=False)
        for d in DEFAULT_MACHINERY_DATA:
            self._add_blank_row(d)

    def _clear_all(self, confirm=True):
        if confirm and self._rows:
            reply = QMessageBox.question(
                self,
                "Clear All",
                "Remove all equipment rows?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._table.setRowCount(0)
        self._rows.clear()
        self._recalculate()

    def _update_height(self):
        h = self._table.horizontalHeader().height() or 35
        h += self._table.rowCount() * 36
        self._table.setFixedHeight(h + 10)

    def _recalculate(self):
        diesel_total = elec_total = 0.0
        for eq in self._rows:
            em = eq.recalculate()
            if eq.source.currentText() == "Diesel":
                diesel_total += em
            else:
                elec_total += em
        total = diesel_total + elec_total
        self._lbl_diesel_sub.setText(f"Diesel: {diesel_total:,.2f} kg CO2e")
        self._lbl_elec_sub.setText(f"Electricity: {elec_total:,.2f} kg CO2e")
        self._lbl_detail_total.setText(f"Subtotal: {total:,.2f} kg CO2e")
        self._on_change()

    def get_total(self) -> float:
        return sum(eq.recalculate() for eq in self._rows)

    def collect(self) -> dict:
        return {
            "default_days": int(self._default_days.value()),
            "rows": [eq.to_dict() for eq in self._rows],
        }

    def load(self, data: dict):
        self._default_days.setValue(int(data.get("default_days", 0)))
        self._clear_all(confirm=False)
        for d in data.get("rows", []):
            self._add_blank_row(d)


# ── Main page ─────────────────────────────────────────────────────────────────


class MachineryEmissions(ScrollableForm):
    def __init__(self, controller=None):
        super().__init__(controller=controller, chunk_name=CHUNK)
        self._loading = False
        self._build_ui()
        if self.controller and hasattr(self.controller, "chunk_updated"):
            self.controller.chunk_updated.connect(self._on_chunk_updated)

    def _get_currency(self) -> str:
        if self.controller and self.controller.engine:
            info = self.controller.engine.fetch_chunk("general_info") or {}
            return str(info.get("currency", ""))
        return ""

    def _build_ui(self):
        f = self.form
        bold = QFont()
        bold.setBold(True)
        bold.setPointSize(11)

        # ── Grand total banner (top) ───────────────────────────────────────
        banner = QGroupBox()
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        self._lbl_grand_total = QLabel("Total Machinery Emissions: — kg CO2e")
        self._lbl_grand_total.setFont(bold)
        note = QLabel(
            "  ⓘ  Fill either Detailed Equipment List or Lump Sum — not both."
        )
        note.setStyleSheet("color: gray; font-style: italic;")
        banner_layout.addWidget(self._lbl_grand_total)
        banner_layout.addWidget(note)
        banner_layout.addStretch()
        f.addRow(banner)

        # ── Toggle ────────────────────────────────────────────────────────
        toggle_widget = QWidget()
        toggle_layout = QHBoxLayout(toggle_widget)
        toggle_layout.setContentsMargins(0, 4, 0, 4)
        self._radio_detailed = QRadioButton("Detailed Equipment List")
        self._radio_lumpsum = QRadioButton("Lump Sum")
        self._radio_detailed.setChecked(True)
        self._toggle_group = QButtonGroup(self)
        self._toggle_group.addButton(self._radio_detailed, 0)
        self._toggle_group.addButton(self._radio_lumpsum, 1)
        self._toggle_group.idToggled.connect(self._on_mode_toggled)
        toggle_layout.addWidget(QLabel("Input Method:"))
        toggle_layout.addSpacing(8)
        toggle_layout.addWidget(self._radio_detailed)
        toggle_layout.addSpacing(16)
        toggle_layout.addWidget(self._radio_lumpsum)
        toggle_layout.addStretch()
        f.addRow(toggle_widget)

        # ── Stack ─────────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # Index 0 — Detailed table
        self._detailed_table = _DetailedTable(on_change=self._on_totals_changed)
        self._stack.addWidget(self._detailed_table)

        # Index 1 — Lump Sum via build_form temp-swap
        lumpsum_widget = QWidget()
        lumpsum_layout = QFormLayout(lumpsum_widget)
        lumpsum_layout.setContentsMargins(0, 0, 0, 0)

        _saved = self.form
        self.form = lumpsum_layout
        build_form(self, LUMPSUM_ELEC_FIELDS, BASE_DOCS_URL)
        build_form(self, LUMPSUM_FUEL_FIELDS, BASE_DOCS_URL)
        self.form = _saved

        # Pop from _field_map — we save manually via collect_data
        # Wire valueChanged -> _on_totals_changed for live total update
        for key, default in _LUMPSUM_KEYS:
            self._field_map.pop(key, None)
            w = getattr(self, key, None)
            if w is not None:
                w.valueChanged.connect(self._on_totals_changed)

        # Set default EF values
        if hasattr(self, "elec_ef"):
            self.elec_ef.setValue(0.71)
        if hasattr(self, "fuel_ef"):
            self.fuel_ef.setValue(2.69)

        # Lump sum subtotal
        ls_total_row = QWidget()
        ls_total_layout = QHBoxLayout(ls_total_row)
        ls_total_layout.setContentsMargins(0, 8, 0, 4)
        self._lbl_lumpsum_total = QLabel("Lump Sum Subtotal: 0.00 kg CO2e")
        bold2 = QFont()
        bold2.setBold(True)
        self._lbl_lumpsum_total.setFont(bold2)
        ls_total_layout.addStretch()
        ls_total_layout.addWidget(self._lbl_lumpsum_total)
        lumpsum_layout.addRow(ls_total_row)

        self._stack.addWidget(lumpsum_widget)
        f.addRow(self._stack)

        # ── Grand total (bottom) ───────────────────────────────────────────
        bottom_banner = QGroupBox()
        bottom_layout = QHBoxLayout(bottom_banner)
        bottom_layout.setContentsMargins(12, 8, 12, 8)
        self._lbl_grand_total_bottom = QLabel("Total Machinery Emissions: — kg CO2e")
        self._lbl_grand_total_bottom.setFont(bold)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self._lbl_grand_total_bottom)
        f.addRow(bottom_banner)

        # ── Remarks ───────────────────────────────────────────────────────
        self._remarks = RemarksEditor(
            title="Remarks / Notes",
            on_change=self._on_field_changed,
        )
        f.addRow(self._remarks)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _lumpsum_elec_total(self) -> float:
        c = getattr(self, "elec_consumption_per_day", None)
        d = getattr(self, "elec_days", None)
        e = getattr(self, "elec_ef", None)
        return c.value() * d.value() * e.value() if c and d and e else 0.0

    def _lumpsum_fuel_total(self) -> float:
        c = getattr(self, "fuel_consumption_per_day", None)
        d = getattr(self, "fuel_days", None)
        e = getattr(self, "fuel_ef", None)
        return c.value() * d.value() * e.value() if c and d and e else 0.0

    def _current_mode(self) -> str:
        return "detailed" if self._radio_detailed.isChecked() else "lumpsum"

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_mode_toggled(self, btn_id: int, checked: bool):
        if checked:
            self._stack.setCurrentIndex(btn_id)
            self._on_totals_changed()

    def _on_totals_changed(self):
        if self._loading:
            return
        # Guard: may fire during build_form before all labels are created
        if not hasattr(self, "_lbl_grand_total_bottom"):
            return
        mode = self._current_mode()
        if mode == "detailed":
            total = self._detailed_table.get_total()
        else:
            total = self._lumpsum_elec_total() + self._lumpsum_fuel_total()
            self._lbl_lumpsum_total.setText(f"Lump Sum Subtotal: {total:,.2f} kg CO2e")

        text = f"Total Machinery Emissions: {total:,.2f} kg CO2e"
        self._lbl_grand_total.setText(text)
        self._lbl_grand_total_bottom.setText(text)
        self._on_field_changed()

    # ── Currency ──────────────────────────────────────────────────────────

    def _apply_currency(self):
        currency = self._get_currency()
        note = f" (Currency: {currency})" if currency else ""
        self._lbl_grand_total.setToolTip(f"Total CO2e emissions from machinery{note}")
        self._lbl_grand_total_bottom.setToolTip(
            f"Total CO2e emissions from machinery{note}"
        )

    def _on_chunk_updated(self, chunk_name: str):
        if chunk_name == "general_info":
            self._apply_currency()

    # ── Data I/O ──────────────────────────────────────────────────────────

    def collect_data(self) -> dict:
        lumpsum = {}
        for key, default in _LUMPSUM_KEYS:
            w = getattr(self, key, None)
            if w is not None:
                lumpsum[key] = (
                    int(w.value()) if isinstance(w, QSpinBox) else float(w.value())
                )
            else:
                lumpsum[key] = default

        return {
            "mode": self._current_mode(),
            "detailed": self._detailed_table.collect(),
            "lumpsum": lumpsum,
            "remarks": self._remarks.to_html(),
            "total_kgCO2e": round(
                (
                    self._detailed_table.get_total()
                    if self._current_mode() == "detailed"
                    else self._lumpsum_elec_total() + self._lumpsum_fuel_total()
                ),
                4,
            ),
        }

    def load_data(self, data: dict):
        if not data:
            return
        self._loading = True
        try:
            mode = data.get("mode", "detailed")
            self._radio_lumpsum.setChecked(mode == "lumpsum")
            self._radio_detailed.setChecked(mode != "lumpsum")
            self._stack.setCurrentIndex(1 if mode == "lumpsum" else 0)

            self._detailed_table.load(data.get("detailed", {}))

            ls = data.get("lumpsum", {})
            for key, default in _LUMPSUM_KEYS:
                w = getattr(self, key, None)
                if w is not None:
                    w.blockSignals(True)
                    val = ls.get(key, default)
                    w.setValue(int(val) if isinstance(w, QSpinBox) else float(val))
                    w.blockSignals(False)

            self._remarks.from_html(data.get("remarks", ""))
        finally:
            self._loading = False
        self._on_totals_changed()

    # ── Base overrides ────────────────────────────────────────────────────

    def _on_field_changed(self):
        if self._loading:
            return
        if self.controller and self.controller.engine and self.chunk_name:
            self.controller.engine.stage_update(
                chunk_name=self.chunk_name, data=self.collect_data()
            )
        self.data_changed.emit()

    def get_data_dict(self) -> dict:
        return self.collect_data()

    def load_data_dict(self, data: dict):
        self.load_data(data)

    def refresh_from_engine(self):
        if not self.controller or not self.controller.engine:
            return
        if not self.controller.engine.is_active() or not self.chunk_name:
            return
        data = self.controller.engine.fetch_chunk(self.chunk_name)
        if data:
            self.load_data(data)
        self._apply_currency()

    def on_refresh(self):
        if not self.controller or not getattr(self.controller, "engine", None):
            return
        data = self.controller.engine.fetch_chunk(CHUNK) or {}
        self.load_data(data)
        self._apply_currency()

    def validate(self):
        return True, []
