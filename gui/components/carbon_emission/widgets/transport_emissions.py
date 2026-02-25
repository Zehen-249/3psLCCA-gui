import math
import datetime
import time

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFrame,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QScrollArea,
    QSizePolicy,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from .transport_dialog import TransportDialog
from PySide6.QtGui import QColor

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


def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


def _vline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


def _section_label(text: str) -> QLabel:
    lbl = QLabel(f"<b>{text}</b>")
    lbl.setStyleSheet("font-size: 13px;")
    return lbl


# ---------------------------------------------------------------------------
# Material lookup — scan all structure chunks by UUID
# ---------------------------------------------------------------------------


def _build_material_index(engine) -> dict:
    """
    Returns dict: {uuid: (item, category, chunk_id, comp_name)}
    Scans all structure chunks once per refresh.
    """
    index = {}
    for chunk_id, category in STRUCTURE_CHUNKS:
        data = engine.fetch_chunk(chunk_id) or {}
        for comp_name, items in data.items():
            for item in items:
                mat_id = item.get("id")
                if mat_id:
                    index[mat_id] = (item, category, chunk_id, comp_name)
    return index


# ---------------------------------------------------------------------------
# Emission calculation
# ---------------------------------------------------------------------------


def calc_vehicle_emission(entry: dict, mat_index: dict) -> tuple:
    """
    Returns (total_emission, material_results, warnings)

    material_results: list of dicts with per-material breakdown
    warnings:         list of warning strings
    """
    v = entry.get("vehicle", {})
    r = entry.get("route", {})
    uuids = entry.get("materials", [])

    eff_pay = float(v.get("effective_payload", 0) or 0)
    dist = float(r.get("distance_km", 0) or 0)
    ef = float(v.get("emission_factor", 0) or 0)

    total_emission = 0.0
    material_results = []
    warnings = []

    if eff_pay <= 0:
        warnings.append("Effective payload is zero — check vehicle data.")
        return 0.0, [], warnings

    if dist <= 0:
        warnings.append("Distance is zero — no emission calculated.")

    if ef <= 0:
        warnings.append("Emission factor is zero — no emission calculated.")

    for mat_entry in uuids:
        # materials is now [{uuid, kg_factor}]
        mat_uuid = mat_entry.get("uuid") if isinstance(mat_entry, dict) else mat_entry
        kg_factor = (
            mat_entry.get("kg_factor", 1.0) if isinstance(mat_entry, dict) else 1.0
        )

        if mat_uuid not in mat_index:
            material_results.append(
                {
                    "uuid": mat_uuid,
                    "name": "Unknown",
                    "status": "removed",
                    "emission": 0.0,
                    "warning": "⚠ Material removed from structure",
                }
            )
            warnings.append(f"Material {mat_uuid[:8]}... was removed from structure.")
            continue

        item, category, chunk_id, comp_name = mat_index[mat_uuid]

        if item.get("state", {}).get("in_trash", False):
            material_results.append(
                {
                    "uuid": mat_uuid,
                    "name": item.get("values", {}).get("material_name", ""),
                    "category": category,
                    "status": "trashed",
                    "emission": 0.0,
                }
            )
            continue

        val = item.get("values", {})
        qty = float(val.get("quantity", 0) or 0)
        unit = val.get("unit", "")
        name = val.get("material_name", "")

        # Use kg_factor from transport entry (not structure conv factor)
        qty_kg = qty * kg_factor
        qty_t = qty_kg / 1000.0
        trips = math.ceil(qty_t / eff_pay) if eff_pay > 0 else 0

        # ×2 for return trip (empty return)
        emission = eff_pay * trips * dist * 2 * ef

        warns = []
        if qty <= 0:
            warns.append("⚠ Zero quantity")
        if qty_kg <= 0 and qty > 0:
            warns.append("⚠ Zero kg — check factor")
        if trips > 1000:
            warns.append(f"⚠ {trips} trips — unusually high")
        if abs(kg_factor - 1.0) < 1e-6 and unit.lower() != "kg":
            warns.append(f"⚠ 1:1 factor for {unit} — verify conversion")

        warn = " | ".join(warns)
        if trips > 1000:
            warnings.append(f"'{name}': {trips} trips — unusually high, check data.")

        material_results.append(
            {
                "uuid": mat_uuid,
                "name": name,
                "category": category,
                "unit": unit,
                "qty": qty,
                "kg_factor": kg_factor,
                "qty_kg": qty_kg,
                "trips": trips,
                "emission": emission,
                "status": "ok",
                "warning": warn,  # ← this
            }
        )

        total_emission += emission

    return total_emission, material_results, warnings


# ---------------------------------------------------------------------------
# Vehicle Card Widget
# ---------------------------------------------------------------------------


class VehicleCard(QGroupBox):
    """
    Displays one vehicle entry with:
    - Header: name, route, total emission
    - Material breakdown table
    - Warnings
    - Edit / Trash buttons
    """

    def __init__(
        self,
        entry: dict,
        mat_results: list,
        warnings: list,
        total_emission: float,
        on_edit,
        on_trash,
        parent=None,
    ):
        v = entry.get("vehicle", {})
        r = entry.get("route", {})
        title = (
            f"{v.get('name', 'Vehicle')}  —  "
            f"{r.get('origin', '?')} → {r.get('destination', '?')}  |  "
            f"{r.get('distance_km', 0)} km  |  "
            f"{total_emission:,.2f} kgCO2e"
        )
        super().__init__(title, parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Vehicle specs row
        specs_row = QHBoxLayout()
        specs = [
            f"Capacity: {v.get('capacity', 0)}t",
            f"Empty Wt: {v.get('empty_weight', 0)}t",
            f"Payload: {v.get('payload', 0)}t",
            f"Loading: {v.get('loading_pct', 100)}%",
            f"Eff. Payload: {v.get('effective_payload', 0):.2f}t",
            f"EF: {v.get('emission_factor', 0)} kgCO2e/t-km",
        ]
        for spec in specs:
            lbl = QLabel(spec)
            lbl.setStyleSheet("font-size: 11px;")
            specs_row.addWidget(lbl)
            specs_row.addWidget(_vline())
        specs_row.addStretch()
        layout.addLayout(specs_row)

        # Warnings
        for warn in warnings:
            warn_lbl = QLabel(f"! {warn}")
            warn_lbl.setWordWrap(True)
            warn_lbl.setStyleSheet("font-size: 11px;")
            layout.addWidget(warn_lbl)

        # Materials table
        if mat_results:
            table = self._build_table(mat_results)
            layout.addWidget(table)

        # Buttons
        btn_row = QHBoxLayout()
        edit_btn = QPushButton("Edit")
        trash_btn = QPushButton("Remove")
        edit_btn.clicked.connect(on_edit)
        trash_btn.clicked.connect(on_trash)
        btn_row.addStretch()
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(trash_btn)
        layout.addLayout(btn_row)

    def _build_table(self, mat_results: list) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(
            [
                "Material",
                "Category",
                "kg Factor",
                "Qty (kg)",
                "Trips",
                "Emission (kgCO2e)",
                "Warnings",
            ]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        for mat in mat_results:
            print(f"[DEBUG] mat: {mat}")  # ← add this
            row = table.rowCount()
            table.insertRow(row)
            status = mat.get("status", "ok")

            if status == "ok":
                table.setItem(row, 0, self._item(mat.get("name", "")))
                table.setItem(row, 1, self._item(mat.get("category", "")))
                table.setItem(row, 2, self._item(str(mat.get("kg_factor", 1))))
                table.setItem(
                    row,
                    3,
                    self._item(
                        f"{mat.get('qty_kg', 0):,.0f}", Qt.AlignRight | Qt.AlignVCenter
                    ),
                )
                table.setItem(
                    row,
                    4,
                    self._item(
                        str(mat.get("trips", 0)), Qt.AlignRight | Qt.AlignVCenter
                    ),
                )
                table.setItem(
                    row,
                    5,
                    self._item(
                        f"{mat.get('emission', 0):,.2f}",
                        Qt.AlignRight | Qt.AlignVCenter,
                    ),
                )

                warn = mat.get("warning", "")
                warn_item = self._item(warn if warn else "", Qt.AlignCenter)
                if warn:
                    # Truncate display text, full detail in tooltip
                    parts = warn.split(" | ")
                    display = parts[0] + (" ..." if len(parts) > 1 else "")
                    warn_item = self._item(display, Qt.AlignCenter)
                    # warn_item.setForeground(QColor("#874d00"))
                    # warn_item.setBackground(QColor("#fffbe6"))
                    # Bullet list in tooltip
                    tooltip = "\n".join(f"• {p}" for p in parts)
                    warn_item.setToolTip(tooltip)
                table.setItem(row, 6, warn_item)

            else:
                table.setItem(row, 0, self._item(mat.get("name", "")))
                table.setItem(row, 1, self._item(mat.get("category", "")))
                for c in range(2, 6):
                    table.setItem(row, c, self._item("—", Qt.AlignCenter))
                label = "In Trash" if status == "trashed" else "Removed"
                warn_item = self._item(f"✕ {label}", Qt.AlignCenter)
                warn_item.setForeground(QColor("#cf1322"))
                warn_item.setBackground(QColor("#fff1f0"))
                table.setItem(row, 6, warn_item)

        header_h = table.horizontalHeader().height() or 32
        table.setFixedHeight(header_h + table.rowCount() * 32 + 10)
        return table

    def _item(self, text="", align=None) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(Qt.ItemIsEnabled)
        if align:
            it.setTextAlignment(align)
        return it


# ---------------------------------------------------------------------------
# TransportEmissions — main widget
# ---------------------------------------------------------------------------


class TransportEmissions(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setObjectName("TransportEmissions")

        self._details_visible = False

        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        # ── Summary Bar ──────────────────────────────────────────────────
        summary_bar = QWidget()
        summary_layout = QHBoxLayout(summary_bar)
        summary_layout.setContentsMargins(8, 8, 8, 8)

        self.total_lbl = QLabel("Total Transport Emissions: — kgCO2e")
        self.vehicle_lbl = QLabel("Vehicles: —")
        self.details_btn = QPushButton("Show Details ▼")
        self.details_btn.setFlat(True)
        self.details_btn.setCursor(Qt.PointingHandCursor)
        self.details_btn.clicked.connect(self._toggle_details)

        summary_layout.addWidget(self.total_lbl)
        summary_layout.addWidget(_vline())
        summary_layout.addWidget(self.vehicle_lbl)
        summary_layout.addStretch()
        summary_layout.addWidget(self.details_btn)
        outer.addWidget(summary_bar)

        # ── Details (hidden by default) ───────────────────────────────────
        self.details_widget = QWidget()
        details_layout = QHBoxLayout(self.details_widget)
        details_layout.setContentsMargins(8, 0, 8, 8)

        self.foundation_lbl = QLabel("Foundation: —")
        self.sub_lbl = QLabel("Sub Structure: —")
        self.super_lbl = QLabel("Super Structure: —")
        self.misc_lbl = QLabel("Misc: —")

        for lbl in [self.foundation_lbl, self.sub_lbl, self.super_lbl, self.misc_lbl]:
            details_layout.addWidget(lbl)
            details_layout.addWidget(_vline())

        details_layout.addStretch()
        self.details_widget.setVisible(False)
        outer.addWidget(self.details_widget)

        outer.addWidget(_hline())

        # ── Add Vehicle Button ────────────────────────────────────────────
        add_row = QHBoxLayout()
        self.add_btn = QPushButton("+ Add Vehicle")
        self.add_btn.setMinimumHeight(32)
        self.add_btn.clicked.connect(self._open_add_dialog)
        add_row.addWidget(self.add_btn)
        add_row.addStretch()
        outer.addLayout(add_row)

        # ── Scroll area for vehicle cards ─────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setSpacing(8)
        scroll.setWidget(self.container)
        outer.addWidget(scroll)

    # ── UI Helpers ───────────────────────────────────────────────────────

    def _toggle_details(self):
        self._details_visible = not self._details_visible
        self.details_widget.setVisible(self._details_visible)
        self.details_btn.setText(
            "Hide Details ▲" if self._details_visible else "Show Details ▼"
        )

    # ── Refresh ──────────────────────────────────────────────────────────

    def on_refresh(self):
        if not self.controller or not getattr(self.controller, "engine", None):
            return

        # Clear cards
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        data = self.controller.engine.fetch_chunk("transport_data") or {}
        vehicles = data.get("vehicles", [])

        mat_index = _build_material_index(self.controller.engine)

        total_emission = 0.0
        cat_totals = {label: 0.0 for _, label in STRUCTURE_CHUNKS}
        active_count = 0

        for entry in vehicles:
            if entry.get("state", {}).get("in_trash", False):
                continue

            active_count += 1
            emission, mat_results, warnings = calc_vehicle_emission(entry, mat_index)
            total_emission += emission

            # Category breakdown
            for mat in mat_results:
                if mat.get("status") == "ok":
                    cat = mat.get("category", "")
                    if cat in cat_totals:
                        cat_totals[cat] += mat.get("emission", 0)

            entry_id = entry.get("id")
            card = VehicleCard(
                entry=entry,
                mat_results=mat_results,
                warnings=warnings,
                total_emission=emission,
                on_edit=lambda _, eid=entry_id: self._open_edit_dialog(eid),
                on_trash=lambda _, eid=entry_id: self._trash_vehicle(eid),
            )
            self.container_layout.addWidget(card)

        self.container_layout.addStretch()

        # Update summary
        self.total_lbl.setText(
            f"Total Transport Emissions: {total_emission:,.2f} kgCO2e"
        )
        self.vehicle_lbl.setText(f"Vehicles: {active_count}")
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

    # ── Actions ──────────────────────────────────────────────────────────

    def _get_assigned_uuids(self, exclude_entry_id: str = None) -> set:
        data = self.controller.engine.fetch_chunk("transport_data") or {}
        vehicles = data.get("vehicles", [])
        assigned = set()
        for entry in vehicles:
            if entry.get("state", {}).get("in_trash", False):
                continue
            if entry.get("id") == exclude_entry_id:
                continue
            for m in entry.get("materials", []):
                if isinstance(m, dict):
                    assigned.add(m.get("uuid"))
                else:
                    assigned.add(m)  # fallback for plain uuid strings
        return assigned

    def _open_add_dialog(self):
        assigned = self._get_assigned_uuids()
        dialog = TransportDialog(self.controller, assigned, parent=self)
        if dialog.exec():
            entry = dialog.get_vehicle_entry()
            data = self.controller.engine.fetch_chunk("transport_data") or {}
            data.setdefault("vehicles", []).append(entry)
            self.controller.engine.stage_update(chunk_name="transport_data", data=data)
            self._mark_dirty()
            QTimer.singleShot(0, self.on_refresh)

    def _open_edit_dialog(self, entry_id: str):
        data = self.controller.engine.fetch_chunk("transport_data") or {}
        vehicles = data.get("vehicles", [])
        entry = next((v for v in vehicles if v.get("id") == entry_id), None)
        if not entry:
            return

        assigned = self._get_assigned_uuids(exclude_entry_id=entry_id)
        dialog = TransportDialog(self.controller, assigned, data=entry, parent=self)
        if dialog.exec():
            updated = dialog.get_vehicle_entry()
            vehicles = [updated if v.get("id") == entry_id else v for v in vehicles]
            data["vehicles"] = vehicles
            self.controller.engine.stage_update(chunk_name="transport_data", data=data)
            self._mark_dirty()
            QTimer.singleShot(0, self.on_refresh)

    def _trash_vehicle(self, entry_id: str):
        confirm = QMessageBox.question(
            self,
            "Remove Vehicle",
            "Remove this vehicle entry? Materials will be available for reassignment.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        data = self.controller.engine.fetch_chunk("transport_data") or {}
        vehicles = data.get("vehicles", [])
        for v in vehicles:
            if v.get("id") == entry_id:
                v.setdefault("state", {})["in_trash"] = True
                v["meta"]["modified_on"] = datetime.datetime.now().isoformat()
                break

        data["vehicles"] = vehicles
        self.controller.engine.stage_update(chunk_name="transport_data", data=data)
        self._mark_dirty()
        QTimer.singleShot(0, self.on_refresh)

    def _mark_dirty(self):
        if self.controller and self.controller.engine:
            eng = self.controller.engine
            eng._last_keystroke_time = time.time()
            eng._has_unsaved_changes = True
            try:
                eng.on_dirty(True)
            except Exception as e:
                print(f"[TransportEmissions] _mark_dirty: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        self.on_refresh()
