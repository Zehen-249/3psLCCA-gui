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
from PySide6.QtGui import QDoubleValidator, QDesktopServices, QColor
import datetime

from ...utils.definitions import FIELD_DEFINITIONS, BASE_DOCS_URL
from ...utils.unit_resolver import analyze_conversion_sympy


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
# Mini Fix Dialog
# ---------------------------------------------------------------------------


class CarbonFixDialog(QDialog):
    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fix Carbon Data")
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        v = item.get("values", {})
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        name = v.get("material_name", "Material")
        header = QLabel(f"<b>{name}</b>")
        layout.addWidget(header)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        dbl = QDoubleValidator()
        dbl.setNotation(QDoubleValidator.StandardNotation)

        layout.addWidget(self._field_label("carbon_emission"))
        self.emission_in = QLineEdit(str(v.get("carbon_emission", "0.0")))
        self.emission_in.setValidator(dbl)
        self.emission_in.setMinimumHeight(30)
        layout.addWidget(self._field_row(self.emission_in, "carbon_emission"))

        layout.addWidget(self._field_label("carbon_unit"))
        self.unit_in = QLineEdit(v.get("carbon_unit", "kgCO2e/kg"))
        self.unit_in.setMinimumHeight(30)
        layout.addWidget(self._field_row(self.unit_in, "carbon_unit"))

        layout.addWidget(self._field_label("conversion_factor"))
        self.conv_in = QLineEdit(str(v.get("conversion_factor", "1.0")))
        self.conv_in.setValidator(dbl)
        self.conv_in.setMinimumHeight(30)
        layout.addWidget(self._field_row(self.conv_in, "conversion_factor"))

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
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._set_column_widths()

    def _set_column_widths(self):
        widths = (
            [110, 180, 80, 90, 110, 100, 70, 80]
            if self.is_included
            else [110, 160, 80, 90, 110, 100, 90, 90]
        )
        for i, w in enumerate(widths):
            self.setColumnWidth(i, w)

    def update_height(self):
        header_h = self.horizontalHeader().height() or 35
        rows_h = self.rowCount() * self.verticalHeader().defaultSectionSize()
        self.setFixedHeight(max(60, header_h + rows_h + 10))

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

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # Summary Bar
        self.summary_bar = QWidget()
        summary_layout = QHBoxLayout(self.summary_bar)
        self.total_lbl = QLabel("Total: — kgCO2e")
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

                    # SymPy Resolver Analysis
                    analysis = analyze_conversion_sympy(
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
        t.clear_rows()
        for category, chunk_id, comp_name, idx, item, carbon, analysis in items:
            v = item.get("values", {})
            row = t.rowCount()
            t.insertRow(row)

            t.setItem(row, 0, QTableWidgetItem(category))
            t.setItem(row, 1, QTableWidgetItem(v.get("material_name", "")))
            t.setItem(
                row, 2, QTableWidgetItem(f"{v.get('quantity', 0)} {v.get('unit', '')}")
            )
            t.setItem(row, 3, QTableWidgetItem(str(v.get("conversion_factor", 1))))
            t.setItem(
                row,
                4,
                QTableWidgetItem(
                    f"{v.get('carbon_emission', 0)} {v.get('carbon_unit', '')}"
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

            btn = QPushButton("Exclude")
            btn.clicked.connect(
                lambda _, ci=chunk_id, cn=comp_name, i=idx: self._toggle_inclusion(
                    ci, cn, i, False
                )
            )
            t.setCellWidget(row, 7, btn)

            # t.set_row_style(row, "#ffffff")

        t.update_height()

    def _populate_excluded(self, items):
        t = self.excluded_table
        t.clear_rows()
        for category, chunk_id, comp_name, idx, item, reason, analysis in items:
            v = item.get("values", {})
            row = t.rowCount()
            t.insertRow(row)

            t.setItem(row, 0, QTableWidgetItem(category))
            t.setItem(row, 1, QTableWidgetItem(v.get("material_name", "")))
            t.setItem(
                row, 2, QTableWidgetItem(f"{v.get('quantity', 0)} {v.get('unit', '')}")
            )
            t.setItem(row, 3, QTableWidgetItem(str(v.get("conversion_factor", 1))))
            t.setItem(
                row,
                4,
                QTableWidgetItem(
                    f"{v.get('carbon_emission', 0)} {v.get('carbon_unit', '')}"
                ),
            )
            t.setItem(row, 5, QTableWidgetItem(reason))

            warn_text = "! Factor" if reason == "Suspicious Data" else ""
            t.setItem(row, 6, QTableWidgetItem(warn_text))

            # Action Button: If item needs fixing (Missing or Suspicious), show 'Fix' button.
            # If item is valid but excluded, show 'Include' button.
            if reason in ["Missing Data", "Suspicious Data"]:
                btn = QPushButton("Fix")
                btn.setStyleSheet("background-color: #f39c12; color: white;")
                btn.clicked.connect(
                    lambda _, ci=chunk_id, cn=comp_name, i=idx, it=item: self._open_fix_dialog(
                        ci, cn, i, it
                    )
                )
                t.set_row_style(
                    row, BG_INVALID if reason == "Missing Data" else BG_SUSPICIOUS
                )
            else:
                btn = QPushButton("Include")
                btn.clicked.connect(
                    lambda _, ci=chunk_id, cn=comp_name, i=idx: self._toggle_inclusion(
                        ci, cn, i, True
                    )
                )
                # t.set_row_style(row, "#ffffff")

            t.setCellWidget(row, 7, btn)
        t.update_height()

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
                # User manually fixed/saved values, so we treat it as confirmed
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

    def showEvent(self, event):
        super().showEvent(event)
        self.on_refresh()
