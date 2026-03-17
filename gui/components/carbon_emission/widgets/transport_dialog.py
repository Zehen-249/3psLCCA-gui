import math
import uuid
import datetime

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QMessageBox, QCheckBox,
    QScrollArea, QSizePolicy, QAbstractItemView, QSplitter,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDoubleValidator, QFont

from ...utils.definitions import STRUCTURE_CHUNKS, UNIT_DIMENSION

# ---------------------------------------------------------------------------
# Vehicle class data
# (full_name, cap_range_label, typical_tare_t, suggested_ef, default_capacity_t)
# ---------------------------------------------------------------------------

_CLASSES = [
    ("Light Duty Vehicle (<4.5T)", "< 4.5 t",  1.5,  1.2,  2.5),
    ("HDV Small (4.5–9T)",         "4.5–9 t",  2.5,  0.7,  7.0),
    ("HDV Medium (9–12T)",         "9–12 t",   4.0,  0.55, 10.5),
    ("HDV Large (>12T)",           "> 12 t",   10.5, 0.19, 24.5),
]

# Short display labels for the class buttons
_BTN_LABELS = [
    ("Light Duty", "< 4.5 t", "EF 1.2"),
    ("HDV Small",  "4.5–9 t", "EF 0.7"),
    ("HDV Medium", "9–12 t",  "EF 0.55"),
    ("HDV Large",  "> 12 t",  "EF 0.19"),
]


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


# ---------------------------------------------------------------------------
# Single-page Transport Dialog
# ---------------------------------------------------------------------------


class TransportDialog(QDialog):
    """
    Single-page dialog for adding / editing a transport delivery entry.

    Layout
    ──────
    Top bar   : Source/Supplier  +  Distance
    Class row : 4 clickable vehicle class cards
    Advanced  : collapsible capacity / gross weight / EF overrides
    ── divider ──
    Main area : left = material picker  |  right = live delivery summary
    Footer    : Save / Cancel
    """

    def __init__(self, controller, assigned_uuids: set,
                 data: dict = None, parent=None):
        super().__init__(parent)
        self.controller      = controller
        self.assigned_uuids  = assigned_uuids
        self.is_edit         = data is not None
        self.existing_data   = data or {}

        self._selected_cls   = 0        # default Light Duty Vehicle
        self._rows_metadata  = []
        self._hide_assigned  = False
        self._ef_override    = False    # True when user manually edits EF

        self.setWindowTitle("Edit Delivery" if self.is_edit else "Add Delivery")
        self.setMinimumSize(1020, 700)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 12)
        outer.setSpacing(10)

        self._build_top_bar(outer)
        self._build_class_cards(outer)
        self._build_advanced(outer)
        outer.addWidget(_divider())
        self._build_main_area(outer)   # splitter: materials | summary
        self._build_footer(outer)

        # Populate material table BEFORE loading existing data
        self._populate_materials()

        if self.is_edit:
            self._load_existing()
        else:
            self._select_class(0)      # Light Duty Vehicle default

    # ── Top bar ───────────────────────────────────────────────────────

    def _build_top_bar(self, layout):
        row = QHBoxLayout()
        row.setSpacing(16)

        source_w = QWidget()
        sl = QVBoxLayout(source_w)
        sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(3)
        sl.addWidget(QLabel("Source / Supplier"))
        self.source_in = QLineEdit()
        self.source_in.setPlaceholderText("e.g. Mumbai Batching Plant")
        self.source_in.setMinimumHeight(34)
        sl.addWidget(self.source_in)
        row.addWidget(source_w, 3)

        dist_w = QWidget()
        dl = QVBoxLayout(dist_w)
        dl.setContentsMargins(0, 0, 0, 0); dl.setSpacing(3)
        dl.addWidget(QLabel("One-Way Distance (km) *"))
        self.dist_in = QDoubleSpinBox()
        self.dist_in.setRange(0, 100_000)
        self.dist_in.setDecimals(1)
        self.dist_in.setMinimumHeight(34)
        self.dist_in.valueChanged.connect(self._update_summary)
        dl.addWidget(self.dist_in)
        row.addWidget(dist_w, 1)

        layout.addLayout(row)

    # ── Vehicle class cards ───────────────────────────────────────────

    def _build_class_cards(self, layout):
        hdr = QLabel("Vehicle Type")
        hdr.setStyleSheet("font-weight: bold;")
        layout.addWidget(hdr)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        self._class_btns = []

        for i, (line1, line2, line3) in enumerate(_BTN_LABELS):
            btn = QPushButton(f"{line1}\n{line2}\n{line3}")
            btn.setCheckable(True)
            btn.setMinimumHeight(64)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _checked, idx=i: self._select_class(idx))
            cards_row.addWidget(btn)
            self._class_btns.append(btn)

        layout.addLayout(cards_row)

    # ── Advanced overrides (collapsible) ──────────────────────────────

    def _build_advanced(self, layout):
        self._adv_toggle = QPushButton("▸  Override capacity / gross weight / EF")
        self._adv_toggle.setFlat(True)
        self._adv_toggle.setCursor(Qt.PointingHandCursor)
        self._adv_toggle.setStyleSheet("text-align: left; padding: 2px 0;")
        self._adv_toggle.clicked.connect(self._toggle_advanced)
        layout.addWidget(self._adv_toggle)

        self._adv_widget = QWidget()
        self._adv_widget.setVisible(False)
        ag = QGridLayout(self._adv_widget)
        ag.setContentsMargins(0, 4, 0, 0)
        ag.setSpacing(12)
        ag.setColumnStretch(0, 1)
        ag.setColumnStretch(1, 1)
        ag.setColumnStretch(2, 1)

        def _spin_field(label, mn, mx, dec):
            w = QWidget(); l = QVBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0); l.setSpacing(3)
            l.addWidget(QLabel(label))
            sb = QDoubleSpinBox()
            sb.setRange(mn, mx); sb.setDecimals(dec); sb.setMinimumHeight(32)
            l.addWidget(sb)
            return w, sb

        w, self.capacity_in = _spin_field("Payload Capacity (t)", 0.01, 1000, 2)
        ag.addWidget(w, 0, 0)
        self.capacity_in.valueChanged.connect(self._on_capacity_changed)

        w, self.gross_in = _spin_field("Gross Weight — Loaded (t)", 0.01, 2000, 2)
        ag.addWidget(w, 0, 1)
        self.gross_in.valueChanged.connect(self._update_summary)

        w, self.ef_in = _spin_field("Emission Factor (kgCO₂e/t-km)", 0, 10, 4)
        ag.addWidget(w, 0, 2)
        self.ef_in.valueChanged.connect(self._on_ef_user_changed)

        self.empty_derived_lbl = QLabel("Empty vehicle weight: — t")
        self.empty_derived_lbl.setStyleSheet("color: gray; font-size: 11px;")
        ag.addWidget(self.empty_derived_lbl, 1, 0, 1, 3)

        layout.addWidget(self._adv_widget)

    def _toggle_advanced(self):
        vis = not self._adv_widget.isVisible()
        self._adv_widget.setVisible(vis)
        self._adv_toggle.setText(
            "▾  Override capacity / gross weight / EF" if vis
            else "▸  Override capacity / gross weight / EF"
        )

    # ── Main area: materials (left) + summary (right) ─────────────────

    def _build_main_area(self, layout):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Left: material picker ─────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        ll.setSpacing(6)

        mat_hdr = QHBoxLayout()
        mat_title = QLabel("Materials")
        mat_title.setStyleSheet("font-weight: bold;")
        mat_hdr.addWidget(mat_title)
        mat_hdr.addStretch()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setFlat(True)
        self.select_all_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_btn.setStyleSheet(
            "QPushButton { color: #0066cc; font-size: 11px; border: none; padding: 0 4px; }"
            "QPushButton:hover { color: #004499; text-decoration: underline; }"
        )
        self.select_all_btn.clicked.connect(self._select_all_valid)
        mat_hdr.addWidget(self.select_all_btn)
        self.hide_assigned_chk = QCheckBox("Hide assigned")
        self.hide_assigned_chk.toggled.connect(self._on_hide_assigned)
        mat_hdr.addWidget(self.hide_assigned_chk)
        ll.addLayout(mat_hdr)

        self.search_in = QLineEdit()
        self.search_in.setPlaceholderText("🔍  Search materials...")
        self.search_in.setMinimumHeight(32)
        self.search_in.textChanged.connect(self._on_search)
        ll.addWidget(self.search_in)

        self.mat_table = QTableWidget()
        self.mat_table.setColumnCount(6)
        self.mat_table.setHorizontalHeaderLabels(
            ["", "Material", "Category", "Unit", "Qty (kg)", "kg / unit"]
        )
        self.mat_table.verticalHeader().setVisible(False)
        self.mat_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.mat_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.mat_table.setAlternatingRowColors(True)
        self.mat_table.setShowGrid(False)
        self.mat_table.verticalHeader().setDefaultSectionSize(34)

        h = self.mat_table.horizontalHeader()
        self.mat_table.setColumnWidth(0, 36)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.mat_table.setColumnWidth(5, 120)
        ll.addWidget(self.mat_table)

        self.mat_count_lbl = QLabel("")
        self.mat_count_lbl.setStyleSheet("color: gray; font-size: 11px;")
        ll.addWidget(self.mat_count_lbl)

        splitter.addWidget(left)

        # ── Right: live summary ───────────────────────────────────────
        right = QWidget()
        right.setMinimumWidth(230)
        right.setMaximumWidth(290)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 0, 0, 0)
        rl.setSpacing(6)

        sum_title = QLabel("Delivery Summary")
        sum_title.setStyleSheet("font-weight: bold;")
        rl.addWidget(sum_title)
        rl.addWidget(_divider())

        def _row(label):
            rw = QHBoxLayout(); rw.setSpacing(4)
            lbl = QLabel(label)
            lbl.setStyleSheet("color: gray; font-size: 11px;")
            val = QLabel("—")
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rw.addWidget(lbl); rw.addStretch(); rw.addWidget(val)
            return rw, val

        r, self._s_class  = _row("Vehicle class");   rl.addLayout(r)
        r, self._s_dist   = _row("Distance");         rl.addLayout(r)
        r, self._s_cap    = _row("Capacity");         rl.addLayout(r)
        rl.addWidget(_divider())
        r, self._s_mats   = _row("Materials");        rl.addLayout(r)
        r, self._s_load   = _row("Total load");       rl.addLayout(r)
        r, self._s_trips  = _row("Trips");            rl.addLayout(r)
        rl.addWidget(_divider())

        rl.addWidget(QLabel("Est. Emission"))

        self._s_emission = QLabel("—")
        font = QFont(); font.setPointSize(18); font.setBold(True)
        self._s_emission.setFont(font)
        self._s_emission.setAlignment(Qt.AlignRight)
        self._s_emission.setWordWrap(True)
        rl.addWidget(self._s_emission)

        self._s_breakdown = QLabel("")
        self._s_breakdown.setStyleSheet("color: gray; font-size: 10px;")
        self._s_breakdown.setAlignment(Qt.AlignRight)
        self._s_breakdown.setWordWrap(True)
        rl.addWidget(self._s_breakdown)

        rl.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([700, 260])
        layout.addWidget(splitter, 1)

    # ── Footer ────────────────────────────────────────────────────────

    def _build_footer(self, layout):
        layout.addWidget(_divider())
        row = QHBoxLayout()

        row.addStretch()

        cancel = QPushButton("Cancel")
        cancel.setMinimumHeight(36); cancel.setFixedWidth(100)
        cancel.clicked.connect(self.reject)

        self.save_btn = QPushButton("Save Delivery")
        self.save_btn.setMinimumHeight(36); self.save_btn.setFixedWidth(140)
        self.save_btn.clicked.connect(self._on_save)

        row.addWidget(cancel)
        row.addWidget(self.save_btn)
        layout.addLayout(row)

    # ── Class selection ───────────────────────────────────────────────

    def _select_class(self, idx: int):
        self._selected_cls = idx
        _, _, tare, ef, cap = _CLASSES[idx]

        for i, btn in enumerate(self._class_btns):
            btn.setChecked(i == idx)

        self._ef_override = False
        for w in (self.capacity_in, self.gross_in, self.ef_in):
            w.blockSignals(True)
        self.capacity_in.setValue(cap)
        self.gross_in.setMinimum(cap)
        self.gross_in.setValue(round(cap + tare, 2))
        self.ef_in.setValue(ef)
        for w in (self.capacity_in, self.gross_in, self.ef_in):
            w.blockSignals(False)

        self._refresh_empty_label()
        self._update_summary()

    def _on_capacity_changed(self):
        cap = self.capacity_in.value()
        self.gross_in.setMinimum(cap)
        self._refresh_empty_label()
        self._update_summary()

    def _on_ef_user_changed(self):
        self._ef_override = True
        self._update_summary()

    def _refresh_empty_label(self):
        gross = self.gross_in.value()
        cap   = self.capacity_in.value()
        empty = max(0.0, gross - cap)
        self.empty_derived_lbl.setText(
            f"Empty vehicle weight (derived): {empty:.2f} t   "
            f"(Gross {gross:.2f} t − Capacity {cap:.2f} t)"
        )

    # ── Material table ────────────────────────────────────────────────

    def _populate_materials(self):
        self.mat_table.setRowCount(0)
        self._rows_metadata = []

        saved_kg = (
            {m["uuid"]: m["kg_factor"]
             for m in self.existing_data.get("materials", [])}
            if self.is_edit else {}
        )

        for chunk_id, category in STRUCTURE_CHUNKS:
            chunk_data = self.controller.engine.fetch_chunk(chunk_id) or {}
            for _comp, items in chunk_data.items():
                for item in items:
                    if item.get("state", {}).get("in_trash", False):
                        continue

                    mat_uuid   = item.get("id", "")
                    v          = item.get("values", {})
                    unit       = v.get("unit", "")
                    qty        = float(v.get("quantity", 0) or 0)
                    stored_usi = v.get("unit_to_si")
                    is_mass    = UNIT_DIMENSION.get(unit.lower()) == "Mass"
                    is_assigned = mat_uuid in self.assigned_uuids

                    kg_from_carbon = False
                    if mat_uuid in saved_kg:
                        kg_factor = saved_kg[mat_uuid]
                    elif is_mass and stored_usi is not None:
                        kg_factor = float(stored_usi)
                    elif v.get("transport_kg_factor"):
                        kg_factor = float(v["transport_kg_factor"])
                    elif (
                        v.get("conversion_factor")
                        and len(_cu := v.get("carbon_unit", "").split("/", 1)) == 2
                        and _cu[0].lower().replace("₂", "2") in ("kgco2e", "kgco2")
                        and _cu[1].lower() == "kg"
                    ):
                        kg_factor = float(v["conversion_factor"])
                        kg_from_carbon = True
                    else:
                        kg_factor = 0.0

                    qty_kg = qty * kg_factor

                    row = self.mat_table.rowCount()
                    self.mat_table.insertRow(row)

                    # Col 0 — checkbox (assigned materials get no checkbox)
                    if is_assigned:
                        self.mat_table.setItem(row, 0, QTableWidgetItem())
                    else:
                        chk_w = QWidget()
                        cl = QHBoxLayout(chk_w)
                        cl.setContentsMargins(0, 0, 0, 0)
                        cl.setAlignment(Qt.AlignCenter)
                        chk = QCheckBox()
                        chk.setChecked(mat_uuid in saved_kg)
                        chk.stateChanged.connect(self._update_summary)
                        cl.addWidget(chk)
                        self.mat_table.setItem(row, 0, QTableWidgetItem())
                        self.mat_table.setCellWidget(row, 0, chk_w)

                    _no_interact = Qt.ItemIsEnabled  # read-only flag shorthand

                    # Col 1 — material name
                    name_val = v.get("material_name", "")
                    ni = QTableWidgetItem(name_val)
                    if is_assigned:
                        ni.setForeground(QColor("#aaaaaa"))
                        ni.setFlags(_no_interact)
                        ni.setToolTip("Already assigned to another vehicle")
                    else:
                        f = ni.font(); f.setBold(True); ni.setFont(f)
                    self.mat_table.setItem(row, 1, ni)

                    # Col 2 — category
                    ci = QTableWidgetItem(category)
                    if is_assigned:
                        ci.setForeground(QColor("#aaaaaa"))
                        ci.setFlags(_no_interact)
                    self.mat_table.setItem(row, 2, ci)

                    # Col 3 — unit
                    ui = QTableWidgetItem(unit if unit else "—")
                    ui.setTextAlignment(Qt.AlignCenter)
                    ui.setFlags(_no_interact)
                    if is_assigned:
                        ui.setForeground(QColor("#aaaaaa"))
                    self.mat_table.setItem(row, 3, ui)

                    # Col 4 — qty in kg
                    qi = QTableWidgetItem(f"{qty_kg:,.0f}" if qty_kg > 0 else "—")
                    qi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    qi.setData(Qt.UserRole, qty_kg)
                    qi.setFlags(_no_interact)
                    if is_assigned:
                        qi.setForeground(QColor("#aaaaaa"))
                    self.mat_table.setItem(row, 4, qi)

                    # Col 5 — kg / unit
                    if is_assigned:
                        ai = QTableWidgetItem("—")
                        ai.setTextAlignment(Qt.AlignCenter)
                        ai.setForeground(QColor("#aaaaaa"))
                        ai.setFlags(_no_interact)
                        self.mat_table.setItem(row, 5, ai)
                    elif is_mass:
                        fi = QTableWidgetItem(f"{kg_factor:g}" if kg_factor > 0 else "")
                        fi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        fi.setData(Qt.UserRole, kg_factor)
                        fi.setFlags(_no_interact)
                        fi.setToolTip("Auto-calculated from unit definition")
                        self.mat_table.setItem(row, 5, fi)
                    else:
                        prefill = saved_kg.get(mat_uuid, kg_factor)
                        edit = QLineEdit("" if prefill <= 0 else f"{prefill:g}")
                        edit.setPlaceholderText("kg per unit")
                        edit.setValidator(QDoubleValidator(0, 1e9, 4))
                        if kg_from_carbon:
                            edit.setToolTip(
                                "Pre-filled from carbon emission data "
                                "(carbon denominator is kg — same conversion applies)"
                            )
                        edit.textChanged.connect(
                            lambda t, r=row, q=qty: self._on_factor_changed(t, r, q)
                        )
                        sort_item = QTableWidgetItem()
                        sort_item.setData(Qt.UserRole, prefill)
                        self.mat_table.setItem(row, 5, sort_item)
                        self.mat_table.setCellWidget(row, 5, edit)

                    self._rows_metadata.append({
                        "uuid":          mat_uuid,
                        "material_name": name_val,
                        "category":      category,
                        "unit":          unit,
                        "qty":           qty,
                        "kg_factor":     kg_factor,
                        "qty_kg":        qty_kg,
                        "is_assigned":   is_assigned,
                    })

        # Sorting is intentionally disabled: cell widgets (QLineEdit) capture
        # the row index at insertion time, so physical row reordering would
        # cause _on_factor_changed to update the wrong row.  Search filtering
        # (which only hides rows without reordering) is sufficient for navigation.
        self.mat_table.setSortingEnabled(False)
        self._refresh_mat_count()

    def _on_factor_changed(self, text: str, row: int, qty: float):
        try:
            val    = float(text or 0)
            qty_kg = qty * val
            self._rows_metadata[row]["kg_factor"] = val
            self._rows_metadata[row]["qty_kg"]    = qty_kg
            item = self.mat_table.item(row, 4)
            if item:
                item.setText(f"{qty_kg:,.0f}" if qty_kg > 0 else "—")
                item.setData(Qt.UserRole, qty_kg)
            sort = self.mat_table.item(row, 5)
            if sort:
                sort.setData(Qt.UserRole, val)
            self._update_summary()
        except Exception:
            pass

    def _on_search(self, text: str):
        text = text.lower().strip()
        for row in range(self.mat_table.rowCount()):
            meta = self._rows_metadata[row]
            match = (
                text in meta["material_name"].lower()
                or text in meta["category"].lower()
            )
            hidden = not match
            if not hidden and self._hide_assigned and meta["is_assigned"]:
                hidden = True
            self.mat_table.setRowHidden(row, hidden)
        self._refresh_mat_count()

    def _on_hide_assigned(self, checked: bool):
        self._hide_assigned = checked
        self._on_search(self.search_in.text())

    def _select_all_valid(self):
        """Check all unassigned materials that are not already checked."""
        for row in range(self.mat_table.rowCount()):
            if row >= len(self._rows_metadata):
                continue
            if self._rows_metadata[row].get("is_assigned"):
                continue
            chk_w = self.mat_table.cellWidget(row, 0)
            if chk_w is None:
                continue
            chk = chk_w.layout().itemAt(0).widget()
            if isinstance(chk, QCheckBox) and not chk.isChecked():
                chk.setChecked(True)

    def _refresh_mat_count(self):
        visible = sum(
            1 for r in range(self.mat_table.rowCount())
            if not self.mat_table.isRowHidden(r)
        )
        total = self.mat_table.rowCount()
        self.mat_count_lbl.setText(f"Showing {visible} of {total} materials")

    # ── Live summary ──────────────────────────────────────────────────

    def _update_summary(self):
        cap   = self.capacity_in.value()
        gross = self.gross_in.value()
        empty = max(0.0, gross - cap)
        dist  = self.dist_in.value()
        ef    = self.ef_in.value()

        total_kg      = 0.0
        selected_count = 0

        for row in range(self.mat_table.rowCount()):
            chk_w = self.mat_table.cellWidget(row, 0)
            if not chk_w:
                continue
            chk = chk_w.findChild(QCheckBox)
            if chk and chk.isChecked():
                qty_kg = (self.mat_table.item(row, 4).data(Qt.UserRole) or 0.0)
                total_kg += qty_kg
                selected_count += 1

        total_t  = total_kg / 1000.0
        trips    = math.ceil(total_t / cap) if cap > 0 and total_t > 0 else 0
        loaded   = gross * trips * dist * ef
        ret      = empty * trips * dist * ef
        emission = loaded + ret

        cls_name = _CLASSES[self._selected_cls][0]

        self._s_class.setText(cls_name)
        self._s_dist.setText(f"{dist:.1f} km" if dist > 0 else "—")
        self._s_cap.setText(f"{cap:.2f} t")
        self._s_mats.setText(str(selected_count) if selected_count else "—")
        self._s_load.setText(f"{total_kg:,.0f} kg" if total_kg > 0 else "—")

        if trips > 0:
            overload = total_t > cap
            self._s_trips.setText(str(trips))
            self._s_trips.setStyleSheet(
                "color: #cf1322; font-weight: bold;" if overload else ""
            )
        else:
            self._s_trips.setText("—")
            self._s_trips.setStyleSheet("")

        if emission > 0:
            self._s_emission.setText(f"{emission:,.1f} kgCO₂e")
            self._s_breakdown.setText(
                f"Loaded {loaded:,.1f}  +  Return {ret:,.1f}"
            )
        else:
            self._s_emission.setText("—")
            self._s_breakdown.setText(
                "Select materials and enter distance" if dist == 0 or selected_count == 0
                else ""
            )

        self._refresh_empty_label()

    # ── Validation & save ─────────────────────────────────────────────

    def _on_save(self):
        if self.dist_in.value() <= 0:
            QMessageBox.critical(self, "Error",
                "Distance must be greater than 0 km.")
            return

        selected = self._get_selected()
        if not selected:
            QMessageBox.critical(self, "Error",
                "Select at least one material.")
            return

        missing = [m["name"] for m in selected if m["kg_factor"] <= 0]
        if missing:
            QMessageBox.critical(self, "Missing kg/unit Factor",
                "These materials need a kg/unit factor:\n• "
                + "\n• ".join(missing))
            return

        self.accept()

    def _get_selected(self) -> list:
        result = []
        for row in range(self.mat_table.rowCount()):
            chk_w = self.mat_table.cellWidget(row, 0)
            if not chk_w:
                continue
            chk = chk_w.findChild(QCheckBox)
            if not (chk and chk.isChecked()):
                continue

            meta  = self._rows_metadata[row]
            edit  = self.mat_table.cellWidget(row, 5)
            if isinstance(edit, QLineEdit):
                try:
                    kg_factor = float(edit.text() or 0)
                except ValueError:
                    kg_factor = 0.0
            else:
                kg_factor = (self.mat_table.item(row, 5).data(Qt.UserRole) or 0.0)

            result.append({
                "uuid":      meta["uuid"],
                "kg_factor": kg_factor,
                "name":      meta["material_name"],
            })
        return result

    # ── Load existing entry ───────────────────────────────────────────

    def _load_existing(self):
        d  = self.existing_data
        v  = d.get("vehicle", {})
        r  = d.get("route", {})

        self.source_in.setText(r.get("origin", ""))
        self.dist_in.setValue(r.get("distance_km", 0))

        # Resolve class index from saved vehicle_class name
        saved_cls = v.get("vehicle_class", "")
        idx = next(
            (i for i, c in enumerate(_CLASSES) if c[0] == saved_cls),
            3   # fallback HDV Large
        )
        self._selected_cls = idx
        for i, btn in enumerate(self._class_btns):
            btn.setChecked(i == idx)

        # Load override values (block signals → single update at end)
        for w in (self.capacity_in, self.gross_in, self.ef_in):
            w.blockSignals(True)
        cap = v.get("capacity", _CLASSES[idx][4])
        self.capacity_in.setValue(cap)
        self.gross_in.setMinimum(cap)
        self.gross_in.setValue(v.get("gross_weight", cap + _CLASSES[idx][2]))
        self.ef_in.setValue(v.get("emission_factor", _CLASSES[idx][3]))
        for w in (self.capacity_in, self.gross_in, self.ef_in):
            w.blockSignals(False)

        # If advanced values differ from class defaults, open the section
        cap_def = _CLASSES[idx][4]
        ef_def  = _CLASSES[idx][3]
        if (abs(cap - cap_def) > 0.01
                or abs(v.get("emission_factor", ef_def) - ef_def) > 1e-4):
            self._toggle_advanced()

        self._refresh_empty_label()
        self._update_summary()

    # ── Build entry dict ──────────────────────────────────────────────

    def get_vehicle_entry(self) -> dict:
        materials = self._get_selected()
        cap   = self.capacity_in.value()
        gross = self.gross_in.value()
        empty = max(0.0, gross - cap)
        dist  = self.dist_in.value()
        ef    = self.ef_in.value()
        cls   = _CLASSES[self._selected_cls][0]

        total_kg = sum(
            m["kg_factor"] * next(
                (r["qty"] for r in self._rows_metadata if r["uuid"] == m["uuid"]),
                0.0,
            )
            for m in materials
        )
        total_t  = total_kg / 1000.0
        trips    = math.ceil(total_t / cap) if cap > 0 and total_t > 0 else 0
        emission = (gross + empty) * trips * dist * ef

        return {
            "id": self.existing_data.get("id", str(uuid.uuid4())),
            "vehicle": {
                "name":            cls,
                "capacity":        cap,
                "gross_weight":    gross,
                "empty_weight":    empty,
                "emission_factor": ef,
                "vehicle_class":   cls,
            },
            "route": {
                "origin":      self.source_in.text().strip(),
                "destination": "Site",
                "distance_km": dist,
            },
            "materials": [
                {"uuid": m["uuid"], "kg_factor": m["kg_factor"]}
                for m in materials
            ],
            "summary": {
                "total_cargo_kg":         total_kg,
                "total_cargo_t":          total_t,
                "trips":                  trips,
                "distance_km":            dist,
                "emission_factor":        ef,
                "total_emissions_kgco2e": emission,
            },
            "meta": {
                "created_at": self.existing_data.get("meta", {}).get(
                    "created_at", datetime.datetime.now().isoformat()
                ),
                "updated_at": datetime.datetime.now().isoformat(),
            },
            "state": self.existing_data.get("state", {}),
        }
