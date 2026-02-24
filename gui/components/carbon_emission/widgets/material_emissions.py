from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QLineEdit,
    QMessageBox,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDoubleValidator, QDesktopServices
import datetime
from ...utils.definitions import FIELD_DEFINITIONS, BASE_DOCS_URL, UNIT_ALIASES


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNKS = [
    ("str_foundation", "Foundation"),
    ("str_sub_structure", "Sub Structure"),
    ("str_super_structure", "Super Structure"),
    ("str_misc", "Misc"),
]


# ---------------------------------------------------------------------------
# Validity check
# ---------------------------------------------------------------------------


def is_carbon_valid(item) -> bool:
    v = item.get("values", {})
    try:
        emission = float(v.get("carbon_emission", 0) or 0)
        conv = float(v.get("conversion_factor", 0) or 0)
        return emission != 0 and conv > 0
    except (TypeError, ValueError):
        return False


def _normalize_unit(unit: str) -> str:
    """Returns canonical unit key or original if not found."""
    u = unit.strip().lower()
    for canonical, aliases in UNIT_ALIASES.items():
        if u in aliases:
            return canonical
    return u


def is_carbon_suspicious(item: dict) -> bool:
    v = item.get("values", {})
    try:
        unit = _normalize_unit(v.get("unit", ""))
        carbon_unit = v.get("carbon_unit", "")
        conv_factor = float(v.get("conversion_factor", 1) or 1)

        # Extract Unit B from carbon_unit e.g. "kgCO2e/kg" → "kg"
        unit_b = (
            _normalize_unit(carbon_unit.split("/")[-1]) if "/" in carbon_unit else ""
        )

        return bool(unit_b and unit != unit_b and conv_factor == 1.0)
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
# Mini Fix Dialog — only carbon fields, shown for missing-data items
# ---------------------------------------------------------------------------


class CarbonFixDialog(QDialog):
    """
    Minimal dialog to fill missing carbon fields.
    Only exposes: Emission Factor, Carbon Unit, Conversion Factor.
    """

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fix Carbon Data")
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        v = item.get("values", {})

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        name = v.get("material_name", "Material")
        header = QLabel(f"<b>{name}</b>")
        layout.addWidget(header)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        dbl = QDoubleValidator()
        dbl.setNotation(QDoubleValidator.StandardNotation)

        # Emission Factor
        layout.addWidget(self._field_label("carbon_emission"))
        self.emission_in = QLineEdit(str(v.get("carbon_emission", "0.0")))
        self.emission_in.setValidator(dbl)
        self.emission_in.setMinimumHeight(30)
        layout.addWidget(self._field_row(self.emission_in, "carbon_emission"))

        # Carbon Unit
        layout.addWidget(self._field_label("carbon_unit"))
        self.unit_in = QLineEdit(v.get("carbon_unit", "kgCO2e/kg"))
        self.unit_in.setMinimumHeight(30)
        layout.addWidget(self._field_row(self.unit_in, "carbon_unit"))

        # Conversion Factor
        layout.addWidget(self._field_label("conversion_factor"))
        self.conv_in = QLineEdit(str(v.get("conversion_factor", "1.0")))
        self.conv_in.setValidator(dbl)
        self.conv_in.setMinimumHeight(30)
        layout.addWidget(self._field_row(self.conv_in, "conversion_factor"))

        # Buttons
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line2)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save & Include")
        save_btn.setMinimumHeight(32)
        save_btn.clicked.connect(self.validate_and_accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(32)
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _field_label(self, key: str) -> QLabel:
        defn = FIELD_DEFINITIONS.get(key, {})
        lbl = QLabel(defn.get("label", key))
        lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        return lbl

    def _field_row(self, input_widget: QWidget, key: str) -> QWidget:
        """Input + ⓘ button on same row."""
        defn = FIELD_DEFINITIONS.get(key, {})
        expl = defn.get("explanation", "")
        slug = defn.get("doc_slug", "")

        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(input_widget)

        info_btn = QPushButton("ⓘ")
        info_btn.setFixedSize(22, 22)
        info_btn.setFlat(True)
        info_btn.setFocusPolicy(Qt.NoFocus)
        info_btn.setCursor(Qt.PointingHandCursor)
        info_btn.clicked.connect(lambda: self._show_info(key))
        row.addWidget(info_btn)

        return container

    def _show_info(self, key: str):
        defn = FIELD_DEFINITIONS.get(key, {})
        msg = QMessageBox(self)
        msg.setWindowTitle(defn.get("label", key))
        msg.setText(defn.get("explanation", "No description available."))

        slug = defn.get("doc_slug", "")
        if slug:
            read_more = msg.addButton("Read More →", QMessageBox.HelpRole)
            read_more.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl(f"{BASE_DOCS_URL}{slug}"))
            )

        msg.addButton(QMessageBox.Close)
        msg.exec()

    def validate_and_accept(self):
        try:
            e = float(self.emission_in.text() or 0)
            c = float(self.conv_in.text() or 0)
            if e == 0 or c == 0:
                QMessageBox.warning(
                    self,
                    "Incomplete",
                    "Emission Factor and Conversion Factor cannot be zero.",
                )
                return
            self.accept()
        except ValueError:
            QMessageBox.critical(
                self, "Validation Error", "Please enter valid numbers."
            )

    def get_values(self) -> dict:
        return {
            "carbon_emission": float(self.emission_in.text() or 0),
            "carbon_unit": self.unit_in.text().strip(),
            "conversion_factor": float(self.conv_in.text() or 1),
        }


# ---------------------------------------------------------------------------
# Carbon Table Widget
# ---------------------------------------------------------------------------


class CarbonTable(QTableWidget):
    """
    Base table for included / excluded sections.
    is_included determines columns and action button label.
    """

    INCLUDED_HEADERS = [
        "Category",
        "Material",
        "Qty (unit)",
        "Conv. Factor",
        "Emission",
        "Total kgCO2e",
        "Warning",
        "Action",
    ]
    EXCLUDED_HEADERS = ["Category", "Material", "Qty (unit)", "Conv. Factor", "Emission", "Reason", "Warning", "Action"]

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
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self._set_column_widths()
        self.update_height()

    def _set_column_widths(self):
        if self.is_included:
            widths = [110, 180, 80, 90, 110, 100, 60, 80]
        else:
            widths = [110, 160, 80, 90, 110, 100, 90, 90]
        for i, w in enumerate(widths):
            self.setColumnWidth(i, w)

    def update_height(self):
        header_h = self.horizontalHeader().height() or 35
        rows_h = self.rowCount() * self.verticalHeader().defaultSectionSize()
        self.setFixedHeight(max(60, header_h + rows_h + 10))

    def clear_rows(self):
        self.setRowCount(0)
        self.update_height()


# ---------------------------------------------------------------------------
# CarbonEmissionWidget — main tab
# ---------------------------------------------------------------------------


class MaterialEmissions(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setObjectName("CarbonEmissionWidget")

        self._details_visible = False

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # ── Summary Bar ──────────────────────────────────────────────────
        self.summary_bar = QWidget()
        summary_layout = QHBoxLayout(self.summary_bar)
        summary_layout.setContentsMargins(8, 8, 8, 8)

        self.total_lbl = QLabel("Total: — kgCO2e")
        self.count_lbl = QLabel("Included: — of — items")
        self.details_btn = QPushButton("Show Details ▼")
        self.details_btn.setFlat(True)
        self.details_btn.setCursor(Qt.PointingHandCursor)
        self.details_btn.clicked.connect(self._toggle_details)

        summary_layout.addWidget(self.total_lbl)
        summary_layout.addWidget(self._vline())
        summary_layout.addWidget(self.count_lbl)
        summary_layout.addStretch()
        summary_layout.addWidget(self.details_btn)

        main_layout.addWidget(self.summary_bar)

        # ── Details Row (hidden by default) ──────────────────────────────
        self.details_widget = QWidget()
        details_layout = QHBoxLayout(self.details_widget)
        details_layout.setContentsMargins(8, 0, 8, 8)

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

        # ── Included Section ─────────────────────────────────────────────
        main_layout.addWidget(self._section_label("Included in Carbon Calculation"))

        self.included_table = CarbonTable(is_included=True)
        main_layout.addWidget(self.included_table)

        main_layout.addWidget(self._hline())

        # ── Excluded Section ─────────────────────────────────────────────
        main_layout.addWidget(self._section_label("Excluded from Carbon Calculation"))

        self.excluded_table = CarbonTable(is_included=False)
        main_layout.addWidget(self.excluded_table)

        main_layout.addStretch()

    # ── UI Helpers ───────────────────────────────────────────────────────

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

    # ── Data Loading ─────────────────────────────────────────────────────

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
                    valid = is_carbon_valid(item)
                    included = item.get("state", {}).get(
                        "included_in_carbon_emission", True
                    )
                    confirmed = item.get("state", {}).get(
                        "carbon_conversion_confirmed", False
                    )
                    suspicious = is_carbon_suspicious(item) and not confirmed

                    if valid and included and not suspicious:
                        included_count += 1
                        carbon = calc_carbon(item)
                        total_carbon += carbon
                        cat_totals[category] += carbon
                        qty = float(item.get("values", {}).get("quantity", 0) or 0)
                        warn = "Zero Qty" if qty == 0 else ""
                        included_items.append(
                            (category, chunk_id, comp_name, idx, item, carbon, warn)
                        )

                    else:
                        if not valid:
                            reason = "Missing Data"
                        elif suspicious:
                            reason = "Suspicious Data"
                        else:
                            reason = "User Excluded"
                        excluded_items.append(
                            (category, chunk_id, comp_name, idx, item, reason)
                        )

        self._populate_included(included_items)
        self._populate_excluded(excluded_items)
        self._update_summary(total_carbon, included_count, total_count, cat_totals)

    def _populate_included(self, items):
        t = self.included_table
        t.clear_rows()

        for category, chunk_id, comp_name, idx, item, carbon, warn in items:
            v = item.get("values", {})
            row = t.rowCount()
            t.insertRow(row)

            qty_unit = f"{v.get('quantity', 0)} {v.get('unit', '')}".strip()
            emission = (
                f"{v.get('carbon_emission', 0)} {v.get('carbon_unit', '')}".strip()
            )

            t.setItem(row, 0, QTableWidgetItem(category))
            t.setItem(row, 1, QTableWidgetItem(v.get("material_name", "")))
            t.setItem(row, 2, QTableWidgetItem(qty_unit))
            t.setItem(row, 3, QTableWidgetItem(str(v.get("conversion_factor", 1))))
            t.setItem(row, 4, QTableWidgetItem(emission))

            carbon_item = QTableWidgetItem(f"{carbon:.2f}")
            carbon_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(row, 5, carbon_item)

            warn_item = QTableWidgetItem(warn)
            warn_item.setTextAlignment(Qt.AlignCenter)
            t.setItem(row, 6, warn_item)

            btn = QPushButton("Exclude")
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(
                lambda _, ci=chunk_id, cn=comp_name, i=idx: self._toggle_inclusion(
                    ci, cn, i, False
                )
            )
            t.setCellWidget(row, 7, btn)

        t.update_height()

    def _populate_excluded(self, items):
        t = self.excluded_table
        t.clear_rows()

        for category, chunk_id, comp_name, idx, item, reason in items:
            v   = item.get("values", {})
            row = t.rowCount()
            t.insertRow(row)

            t.setItem(row, 0, QTableWidgetItem(category))
            t.setItem(row, 1, QTableWidgetItem(v.get("material_name", "")))

            # Show full detail for all rows
            qty_unit = f"{v.get('quantity', 0)} {v.get('unit', '')}".strip()
            emission = f"{v.get('carbon_emission', 0)} {v.get('carbon_unit', '')}".strip()

            t.setItem(row, 2, QTableWidgetItem(qty_unit))
            t.setItem(row, 3, QTableWidgetItem(str(v.get("conversion_factor", 1))))
            t.setItem(row, 4, QTableWidgetItem(emission))
            t.setItem(row, 5, QTableWidgetItem(reason))

            # Warning column
            warn_text = "! Unit Mismatch" if reason == "Suspicious Data" else ""
            warn_item = QTableWidgetItem(warn_text)
            warn_item.setTextAlignment(Qt.AlignCenter)
            t.setItem(row, 6, warn_item)

            # Action button
            if reason == "Missing Data":
                btn = QPushButton("Fix")
                btn.setStyleSheet("background-color: #f39c12; color: white;")
                btn.clicked.connect(
                    lambda _, ci=chunk_id, cn=comp_name, i=idx, it=item: self._open_fix_dialog(ci, cn, i, it)
                )
            elif reason == "Suspicious Data":
                btn = QPushButton("I Confirm")
                btn.setStyleSheet("background-color: #f39c12; color: white;")
                btn.clicked.connect(
                    lambda _, ci=chunk_id, cn=comp_name, i=idx: self._confirm_suspicious(ci, cn, i)
                )
            else:
                btn = QPushButton("Include")
                btn.clicked.connect(
                    lambda _, ci=chunk_id, cn=comp_name, i=idx: self._toggle_inclusion(ci, cn, i, True)
                )

            btn.setFocusPolicy(Qt.NoFocus)
            t.setCellWidget(row, 7, btn)

        t.update_height()

    def _confirm_suspicious(self, chunk_id: str, comp_name: str, data_index: int):
        data = self.controller.engine.fetch_chunk(chunk_id) or {}
        if comp_name in data and data_index < len(data[comp_name]):
            data[comp_name][data_index]["state"]["carbon_conversion_confirmed"] = True
            data[comp_name][data_index]["state"]["included_in_carbon_emission"] = True
            self.controller.engine.stage_update(chunk_name=chunk_id, data=data)
            self._mark_dirty()
            QTimer.singleShot(0, self.on_refresh)

    def _update_summary(
        self, total: float, included: int, total_count: int, cat_totals: dict
    ):
        self.total_lbl.setText(f"Total: {total:,.2f} kgCO2e")
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

    # ── Actions ──────────────────────────────────────────────────────────

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

    def _open_fix_dialog(
        self, chunk_id: str, comp_name: str, data_index: int, item: dict
    ):
        dialog = CarbonFixDialog(item, self)
        if dialog.exec():
            new_vals = dialog.get_values()
            data = self.controller.engine.fetch_chunk(chunk_id) or {}
            if comp_name in data and data_index < len(data[comp_name]):
                target = data[comp_name][data_index]
                target["values"].update(new_vals)
                target["state"]["included_in_carbon_emission"] = True
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
            except Exception:
                pass

    def showEvent(self, event):
        super().showEvent(event)
        self.on_refresh()
