import math
import uuid
import datetime

from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QMessageBox,
    QCheckBox,
    QScrollArea,
    QGroupBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator

from ...utils.definitions import DEFAULT_VEHICLES, FIELD_DEFINITIONS, BASE_DOCS_URL


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRUCTURE_CHUNKS = [
    ("str_foundation", "Foundation"),
    ("str_sub_structure", "Sub Structure"),
    ("str_super_structure", "Super Structure"),
    ("str_misc", "Misc"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _section_label(text: str) -> QLabel:
    lbl = QLabel(f"<b>{text}</b>")
    lbl.setStyleSheet("font-size: 13px;")
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


def _readonly_field(label: str, value: str = "—") -> tuple:
    """Returns (QLabel title, QLabel value) pair for read-only display."""
    title = QLabel(label)
    title.setStyleSheet("font-weight: 600; font-size: 12px;")
    val_lbl = QLabel(value)
    return title, val_lbl


# ---------------------------------------------------------------------------
# TransportDialog
# ---------------------------------------------------------------------------


class TransportDialog(QDialog):
    """
    Add / Edit vehicle dialog.

    Section 1 — Vehicle Selection
        Dropdown: Default + Custom vehicles
        Fields: Name, Capacity, Empty Weight, Payload (readonly),
                Loading %, Effective Payload (readonly), Emission Factor

    Section 2 — Route
        Origin, Destination, Distance

    Section 3 — Assign Materials
        Checkbox table of all structure materials
        Already assigned UUIDs are disabled (grayed out)
    """

    def __init__(
        self,
        controller,
        assigned_uuids: set,
        data: dict = None,
        parent=None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.assigned_uuids = assigned_uuids
        self.is_edit = data is not None
        self.existing_data = data or {}

        self.setWindowTitle("Edit Vehicle" if self.is_edit else "Add Vehicle")
        self.setMinimumWidth(620)
        self.setMinimumHeight(600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # ── Outer layout ─────────────────────────────────────────────────
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 8)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        self.root = QVBoxLayout(inner)
        self.root.setContentsMargins(16, 12, 16, 4)
        self.root.setSpacing(6)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # ── Build sections ───────────────────────────────────────────────
        self._build_vehicle_section()
        self.root.addWidget(_divider())
        self._build_route_section()
        self.root.addWidget(_divider())
        self._build_materials_section()
        self.root.addStretch()

        # ── Button bar ───────────────────────────────────────────────────
        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(16, 8, 16, 4)

        self.save_btn = QPushButton("Update Vehicle" if self.is_edit else "Add Vehicle")
        self.save_btn.setMinimumHeight(32)
        self.save_btn.clicked.connect(self.validate_and_accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(32)
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        outer.addWidget(btn_bar)

        # ── Load existing data if editing ────────────────────────────────
        if self.is_edit:
            self._load_existing()

    # ── Section 1: Vehicle ───────────────────────────────────────────────

    def _build_vehicle_section(self):
        self.root.addWidget(_section_label("Vehicle Details"))

        # Dropdown — default + custom vehicles
        dropdown_row = QHBoxLayout()
        dropdown_lbl = QLabel("Select Vehicle Template:")
        dropdown_lbl.setStyleSheet("font-weight: 600;")
        self.vehicle_dropdown = QComboBox()
        self.vehicle_dropdown.addItem("-- Select --", userData=None)

        # Default vehicles
        for name, specs in DEFAULT_VEHICLES.items():
            self.vehicle_dropdown.addItem(f"{name}", userData=specs)

        # Custom vehicles from project
        custom = self._fetch_custom_vehicles()
        if custom:
            self.vehicle_dropdown.addItem("── Custom ──", userData=None)
            for v in custom:
                self.vehicle_dropdown.addItem(v["name"], userData=v)

        self.vehicle_dropdown.currentIndexChanged.connect(self._on_vehicle_selected)
        dropdown_row.addWidget(dropdown_lbl)
        dropdown_row.addWidget(self.vehicle_dropdown)
        dropdown_row.addStretch()
        self.root.addLayout(dropdown_row)

        # Fields grid
        fields_widget = QWidget()
        fields_layout = QHBoxLayout(fields_widget)
        fields_layout.setContentsMargins(0, 4, 0, 4)
        fields_layout.setSpacing(16)

        # Left column
        left = QVBoxLayout()
        self.name_in = self._input_field(left, "Vehicle Name", is_text=True)
        self.capacity_in = self._spinbox_field(left, "Capacity (t)", 0, 200, 2)
        self.empty_wt_in = self._spinbox_field(left, "Empty Weight (t)", 0, 200, 2)

        # Right column
        right = QVBoxLayout()
        self.payload_lbl = self._readonly_display(right, "Payload (t)")
        self.loading_in = self._spinbox_field(
            right, "Loading (%)", 1, 100, 1, default=100
        )
        self.eff_pay_lbl = self._readonly_display(right, "Effective Payload (t)")
        self.emission_in = self._spinbox_field(
            right, "Emission Factor (kgCO2e/t-km)", 0, 10, 6, default=0.055
        )

        fields_layout.addLayout(left)
        fields_layout.addLayout(right)
        self.root.addWidget(fields_widget)

        # Save as custom vehicle
        save_row = QHBoxLayout()
        self.save_custom_chk = QCheckBox("Save as custom vehicle for this project")
        save_row.addWidget(self.save_custom_chk)
        save_row.addStretch()
        self.root.addLayout(save_row)

        # Wire calculations
        self.capacity_in.valueChanged.connect(self._recalculate)
        self.empty_wt_in.valueChanged.connect(self._recalculate)
        self.loading_in.valueChanged.connect(self._recalculate)

    def _build_route_section(self):
        self.root.addWidget(_section_label("Route"))

        route_widget = QWidget()
        route_layout = QHBoxLayout(route_widget)
        route_layout.setContentsMargins(0, 4, 0, 4)
        route_layout.setSpacing(16)

        left = QVBoxLayout()
        right = QVBoxLayout()

        self.origin_in = self._input_field(left, "Origin", is_text=True)
        self.dest_in = self._input_field(right, "Destination", is_text=True)
        self.dist_in = self._spinbox_field(left, "Distance (km)", 0, 10000, 1)

        route_layout.addLayout(left)
        route_layout.addLayout(right)
        self.root.addWidget(route_widget)

    def _build_materials_section(self):
        self.root.addWidget(_section_label("Assign Materials"))

        info = QLabel(
            "Select materials to be transported by this vehicle. "
            "Materials already assigned to another vehicle are disabled."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 11px;")
        self.root.addWidget(info)

        # Materials table
        self.mat_table = QTableWidget()
        self.mat_table.setColumnCount(7)
        self.mat_table.setHorizontalHeaderLabels(
            ["", "Material", "Category", "Qty", "Unit", "Conv. Factor", "Qty (kg)"]
        )
        self.mat_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.mat_table.horizontalHeader().setStretchLastSection(True)
        self.mat_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.mat_table.setSelectionMode(QTableWidget.NoSelection)
        self.mat_table.verticalHeader().setVisible(False)
        self.mat_table.verticalHeader().setDefaultSectionSize(35)
        self.mat_table.setColumnWidth(0, 30)  # checkbox
        self.mat_table.setColumnWidth(1, 150)  # material
        self.mat_table.setColumnWidth(2, 100)  # category
        self.mat_table.setColumnWidth(3, 60)  # qty
        self.mat_table.setColumnWidth(4, 50)  # unit
        self.mat_table.setColumnWidth(5, 90)  # conv factor
        self.mat_table.setColumnWidth(6, 80)  # qty kg

        self._populate_materials_table()
        self.root.addWidget(self.mat_table)

    # ── Field builders ───────────────────────────────────────────────────

    def _input_field(self, layout: QVBoxLayout, label: str, is_text=False) -> QWidget:
        lbl = QLabel(label)
        lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        layout.addWidget(lbl)

        if is_text:
            widget = QLineEdit()
        else:
            widget = QLineEdit()

        widget.setMinimumHeight(30)
        layout.addWidget(widget)
        return widget

    def _spinbox_field(
        self,
        layout: QVBoxLayout,
        label: str,
        min_val: float,
        max_val: float,
        decimals: int,
        default: float = 0.0,
    ) -> QDoubleSpinBox:
        lbl = QLabel(label)
        lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        layout.addWidget(lbl)

        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setDecimals(decimals)
        spin.setValue(default)
        spin.setMinimumHeight(30)
        layout.addWidget(spin)
        return spin

    def _readonly_display(self, layout: QVBoxLayout, label: str) -> QLabel:
        lbl = QLabel(label)
        lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        layout.addWidget(lbl)

        val_lbl = QLabel("—")
        val_lbl.setMinimumHeight(30)
        layout.addWidget(val_lbl)
        return val_lbl

    # ── Vehicle dropdown handler ─────────────────────────────────────────

    def _on_vehicle_selected(self, index: int):
        specs = self.vehicle_dropdown.itemData(index)
        if not specs:
            return

        self.name_in.setText(specs.get("name", ""))
        self.capacity_in.setValue(specs.get("capacity", 0))
        self.empty_wt_in.setValue(specs.get("empty_weight", 0))
        self.emission_in.setValue(specs.get("emission_factor", 0))
        self._recalculate()

    def _recalculate(self):
        capacity = self.capacity_in.value()
        empty_wt = self.empty_wt_in.value()
        loading = self.loading_in.value()

        payload = max(0.0, capacity - empty_wt)
        eff_payload = payload * (loading / 100)

        self.payload_lbl.setText(f"{payload:.2f} t")
        self.eff_pay_lbl.setText(f"{eff_payload:.2f} t")

        # Validate gross weight
        if empty_wt >= capacity and capacity > 0:
            self.payload_lbl.setText("! Empty wt >= Capacity")

    # ── Materials table ──────────────────────────────────────────────────

    def _populate_materials_table(self):
        """Scan all structure chunks and populate checkbox table."""
        self.mat_table.setRowCount(0)
        self._material_rows = []  # list of (uuid, chunk_id, comp_name, item)

        # UUIDs already assigned to THIS vehicle (allowed to re-check in edit mode)
        own_uuids = set()
        if self.is_edit:
            own_uuids = set(self.existing_data.get("materials", []))

        for chunk_id, category in STRUCTURE_CHUNKS:
            data = self.controller.engine.fetch_chunk(chunk_id) or {}
            for comp_name, items in data.items():
                for item in items:
                    if item.get("state", {}).get("in_trash", False):
                        continue

                    mat_uuid = item.get("id", "")
                    v = item.get("values", {})

                    row = self.mat_table.rowCount()
                    self.mat_table.insertRow(row)

                    # Checkbox
                    chk = QCheckBox()
                    chk_widget = QWidget()
                    chk_layout = QHBoxLayout(chk_widget)
                    chk_layout.addWidget(chk)
                    chk_layout.setAlignment(Qt.AlignCenter)
                    chk_layout.setContentsMargins(0, 0, 0, 0)

                    # Disable if assigned to another vehicle
                    is_assigned_elsewhere = (
                        mat_uuid in self.assigned_uuids and mat_uuid not in own_uuids
                    )
                    if is_assigned_elsewhere:
                        chk.setEnabled(False)

                    # Pre-check if editing and material was assigned
                    if mat_uuid in own_uuids:
                        chk.setChecked(True)

                    self.mat_table.setCellWidget(row, 0, chk_widget)

                    qty = v.get("quantity", 0)
                    unit = v.get("unit", "")
                    conv = v.get("conversion_factor", 1)
                    qty_kg = float(qty or 0) * float(conv or 1)

                    self.mat_table.setItem(
                        row, 1, QTableWidgetItem(v.get("material_name", ""))
                    )
                    self.mat_table.setItem(row, 2, QTableWidgetItem(category))
                    self.mat_table.setItem(row, 3, QTableWidgetItem(str(qty)))
                    self.mat_table.setItem(row, 4, QTableWidgetItem(unit))
                    self.mat_table.setItem(row, 5, QTableWidgetItem(str(conv)))
                    self.mat_table.setItem(row, 6, QTableWidgetItem(f"{qty_kg:,.0f}"))

                    self._material_rows.append((mat_uuid, chunk_id, comp_name, item))

        # Resize table height
        header_h = self.mat_table.horizontalHeader().height() or 35
        rows_h = self.mat_table.rowCount() * 35
        self.mat_table.setFixedHeight(min(300, max(80, header_h + rows_h + 10)))

    def _get_checked_uuids(self) -> list:
        checked = []
        for row, (mat_uuid, chunk_id, comp_name, item) in enumerate(
            self._material_rows
        ):
            chk_widget = self.mat_table.cellWidget(row, 0)
            if chk_widget:
                chk = chk_widget.findChild(QCheckBox)
                if chk and chk.isChecked():
                    checked.append(mat_uuid)
        return checked

    # ── Load existing data ───────────────────────────────────────────────

    def _load_existing(self):
        d = self.existing_data
        v = d.get("vehicle", {})
        r = d.get("route", {})

        self.name_in.setText(v.get("name", ""))
        self.capacity_in.setValue(v.get("capacity", 0))
        self.empty_wt_in.setValue(v.get("empty_weight", 0))
        self.loading_in.setValue(v.get("loading_pct", 100))
        self.emission_in.setValue(v.get("emission_factor", 0))

        self.origin_in.setText(r.get("origin", ""))
        self.dest_in.setText(r.get("destination", ""))
        self.dist_in.setValue(r.get("distance_km", 0))

        self._recalculate()

    # ── Custom vehicle fetch ─────────────────────────────────────────────

    def _fetch_custom_vehicles(self) -> list:
        try:
            data = self.controller.engine.fetch_chunk("project_vehicles") or {}
            return data.get("custom", [])
        except Exception:
            return []

    # ── Validation ───────────────────────────────────────────────────────

    def validate_and_accept(self):
        name = self.name_in.text().strip()
        capacity = self.capacity_in.value()
        empty_wt = self.empty_wt_in.value()
        dist = self.dist_in.value()
        ef = self.emission_in.value()

        if not name:
            QMessageBox.critical(self, "Validation Error", "Vehicle name is required.")
            return

        if capacity <= 0:
            QMessageBox.critical(
                self, "Validation Error", "Capacity must be greater than zero."
            )
            return

        if empty_wt >= capacity:
            QMessageBox.critical(
                self,
                "Validation Error",
                "Empty weight must be less than capacity.\n"
                f"Payload = Capacity ({capacity}t) - Empty Weight ({empty_wt}t) must be > 0.",
            )
            return

        if dist <= 0:
            QMessageBox.warning(
                self, "Warning", "Distance is zero — no emission will be calculated."
            )

        if ef <= 0:
            QMessageBox.critical(
                self, "Validation Error", "Emission factor must be greater than zero."
            )
            return

        checked = self._get_checked_uuids()
        if not checked:
            QMessageBox.warning(
                self,
                "No Materials",
                "Please assign at least one material to this vehicle.",
            )
            return

        # Save custom vehicle if checked
        if self.save_custom_chk.isChecked():
            self._save_custom_vehicle(name, capacity, empty_wt, ef)

        self.accept()

    def _save_custom_vehicle(self, name, capacity, empty_wt, ef):
        try:
            data = self.controller.engine.fetch_chunk("project_vehicles") or {}
            custom = data.get("custom", [])

            # Check duplicate name
            if any(v["name"].lower() == name.lower() for v in custom):
                QMessageBox.warning(
                    self,
                    "Duplicate",
                    f"Vehicle '{name}' already exists in custom vehicles.",
                )
                return

            custom.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "capacity": capacity,
                    "empty_weight": empty_wt,
                    "payload": capacity - empty_wt,
                    "emission_factor": ef,
                    "meta": {
                        "created_on": datetime.datetime.now().isoformat(),
                        "modified_on": datetime.datetime.now().isoformat(),
                    },
                }
            )
            data["custom"] = custom
            self.controller.engine.stage_update(
                chunk_name="project_vehicles", data=data
            )
        except Exception as e:
            print(f"[ERROR] _save_custom_vehicle: {e}")

    # ── Output ───────────────────────────────────────────────────────────

    def get_vehicle_entry(self) -> dict:
        capacity = self.capacity_in.value()
        empty_wt = self.empty_wt_in.value()
        loading = self.loading_in.value()
        payload = capacity - empty_wt
        eff_pay = payload * (loading / 100)
        now = datetime.datetime.now().isoformat()

        entry_id = self.existing_data.get("id", str(uuid.uuid4()))

        return {
            "id": entry_id,
            "vehicle": {
                "name": self.name_in.text().strip(),
                "capacity": capacity,
                "empty_weight": empty_wt,
                "payload": payload,
                "loading_pct": loading,
                "effective_payload": eff_pay,
                "emission_factor": self.emission_in.value(),
                "is_custom": self.save_custom_chk.isChecked(),
            },
            "route": {
                "origin": self.origin_in.text().strip(),
                "destination": self.dest_in.text().strip(),
                "distance_km": self.dist_in.value(),
            },
            "materials": self._get_checked_uuids(),
            "meta": {
                "created_on": self.existing_data.get("meta", {}).get("created_on", now),
                "modified_on": now,
            },
            "state": {
                "in_trash": False,
            },
        }
