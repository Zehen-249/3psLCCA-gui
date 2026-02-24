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
    QDialog,
    QLineEdit,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDoubleValidator, QDesktopServices
import time
import datetime
from ..utils.definitions import FIELD_DEFINITIONS, BASE_DOCS_URL


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


def is_recyclable_valid(item: dict) -> bool:
    """
    Item is valid if:
      - recyclability_percentage > 0
      - scrap_rate > 0  (needed for cost calculation)
      - quantity > 0
    """
    v = item.get("values", {})
    try:
        return all(
            [
                float(v.get("recyclability_percentage", 0) or 0) > 0,
                float(v.get("scrap_rate", 0) or 0) > 0,
                float(v.get("quantity", 0) or 0) > 0,
            ]
        )
    except (TypeError, ValueError):
        return False


def calc_recyclable_qty(item: dict) -> float:
    """Recyclable Qty = quantity × (recyclability% / 100)"""
    v = item.get("values", {})
    try:
        qty = float(v.get("quantity", 0) or 0)
        pct = float(v.get("recyclability_percentage", 0) or 0)
        return qty * (pct / 100)
    except (TypeError, ValueError):
        return 0.0


def calc_recovered_value(item: dict) -> float:
    """Recovered Value = Recyclable Qty × scrap_rate"""
    v = item.get("values", {})
    try:
        recyclable_qty = calc_recyclable_qty(item)
        scrap_rate = float(v.get("scrap_rate", 0) or 0)
        return recyclable_qty * scrap_rate
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Recycling Table
# ---------------------------------------------------------------------------


class RecyclingTable(QTableWidget):

    INCLUDED_HEADERS = [
        "Category",
        "Material",
        "Qty (unit)",
        "Recyclability %",
        "Recyclable Qty",
        "Scrap Rate",
        "Recovered Value",
        "Warning",
        "Action",
    ]
    EXCLUDED_HEADERS = [
        "Category",
        "Material",
        "Qty (unit)",
        "Recyclability %",
        "Scrap Rate",
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
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self._set_column_widths()
        self.update_height()

    def _set_column_widths(self):
        if self.is_included:
            widths = [110, 160, 80, 100, 100, 90, 110, 80, 80]
        else:
            widths = [110, 160, 80, 100, 90, 100, 80, 80]
        for i, w in enumerate(widths):
            self.setColumnWidth(i, w)

    def update_height(self):
        header_h = self.horizontalHeader().height() or 35
        rows_h = self.rowCount() * self.verticalHeader().defaultSectionSize()
        self.setFixedHeight(max(60, header_h + rows_h + 10))

    def clear_rows(self):
        self.setRowCount(0)
        self.update_height()


class RecyclingFixDialog(QDialog):
    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fix Recyclability Data")
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        v = item.get("values", {})

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        name = v.get("material_name", "Material")
        layout.addWidget(QLabel(f"<b>{name}</b>"))

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        dbl = QDoubleValidator()
        dbl.setNotation(QDoubleValidator.StandardNotation)

        # Recyclability %
        layout.addWidget(self._field_label("recyclability_percentage"))
        self.recycle_in = QLineEdit(str(v.get("recyclability_percentage", "0.0")))
        self.recycle_in.setValidator(dbl)
        self.recycle_in.setMinimumHeight(30)
        layout.addWidget(self._field_row(self.recycle_in, "recyclability_percentage"))

        # Scrap Rate
        layout.addWidget(self._field_label("scrap_rate"))
        self.scrap_in = QLineEdit(str(v.get("scrap_rate", "0.0")))
        self.scrap_in.setValidator(dbl)
        self.scrap_in.setMinimumHeight(30)
        layout.addWidget(self._field_row(self.scrap_in, "scrap_rate"))

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
        defn = FIELD_DEFINITIONS.get(key, {})
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
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from ..utils.definitions import BASE_DOCS_URL

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
            r = float(self.recycle_in.text() or 0)
            s = float(self.scrap_in.text() or 0)
            if r <= 0 or s <= 0:
                QMessageBox.warning(
                    self,
                    "Incomplete",
                    "Recyclability % and Scrap Rate must be greater than zero.",
                )
                return
            self.accept()
        except ValueError:
            QMessageBox.critical(
                self, "Validation Error", "Please enter valid numbers."
            )

    def get_values(self) -> dict:
        return {
            "recyclability_percentage": float(self.recycle_in.text() or 0),
            "scrap_rate": float(self.scrap_in.text() or 0),
            "is_recyclable": True,
        }


# ---------------------------------------------------------------------------
# RecyclingWidget — main tab
# ---------------------------------------------------------------------------


class Recycling(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setObjectName("RecyclingWidget")

        self._details_visible = False

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # ── Summary Bar ──────────────────────────────────────────────────
        self.summary_bar = QWidget()
        summary_layout = QHBoxLayout(self.summary_bar)
        summary_layout.setContentsMargins(8, 8, 8, 8)

        self.total_lbl = QLabel("Total Recovered Value: —")
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
        main_layout.addWidget(self._section_label("Included in Recyclability"))

        self.included_table = RecyclingTable(is_included=True)
        main_layout.addWidget(self.included_table)

        main_layout.addWidget(self._hline())

        # ── Excluded Section ─────────────────────────────────────────────
        main_layout.addWidget(self._section_label("Excluded from Recyclability"))

        self.excluded_table = RecyclingTable(is_included=False)
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

    def _get_currency(self) -> str:
        """Pull currency from financial_data chunk, fallback to empty."""
        try:
            data = self.controller.engine.fetch_chunk("financial_data") or {}
            return data.get("currency", "")
        except Exception:
            return ""

    # ── Data Loading ─────────────────────────────────────────────────────

    def on_refresh(self):
        if not self.controller or not getattr(self.controller, "engine", None):
            return

        included_items = []
        excluded_items = []

        cat_totals = {label: 0.0 for _, label in CHUNKS}
        total_value = 0.0
        total_count = 0
        included_count = 0

        currency = self._get_currency()

        for chunk_id, category in CHUNKS:
            data = self.controller.engine.fetch_chunk(chunk_id) or {}

            for comp_name, items in data.items():
                for idx, item in enumerate(items):
                    if item.get("state", {}).get("in_trash", False):
                        continue

                    total_count += 1
                    valid = is_recyclable_valid(item)
                    included = item.get("state", {}).get(
                        "included_in_recyclability", True
                    )

                    if valid and included:
                        included_count += 1
                        value = calc_recovered_value(item)
                        total_value += value
                        cat_totals[category] += value

                        v = item.get("values", {})
                        qty = float(v.get("quantity", 0) or 0)
                        warn = "! Zero Qty" if qty == 0 else ""
                        included_items.append(
                            (category, chunk_id, comp_name, idx, item, value, warn)
                        )
                    else:
                        reason = "Missing Data" if not valid else "User Excluded"
                        excluded_items.append(
                            (category, chunk_id, comp_name, idx, item, reason)
                        )

        self._populate_included(included_items, currency)
        self._populate_excluded(excluded_items)
        self._update_summary(
            total_value, included_count, total_count, cat_totals, currency
        )

    def _populate_included(self, items, currency: str):
        t = self.included_table
        t.clear_rows()

        for category, chunk_id, comp_name, idx, item, value, warn in items:
            v = item.get("values", {})
            row = t.rowCount()
            t.insertRow(row)

            qty_unit = f"{v.get('quantity', 0)} {v.get('unit', '')}".strip()
            recyclable_qty = (
                f"{calc_recyclable_qty(item):.2f} {v.get('unit', '')}".strip()
            )
            value_str = f"{currency} {value:,.2f}".strip()

            t.setItem(row, 0, QTableWidgetItem(category))
            t.setItem(row, 1, QTableWidgetItem(v.get("material_name", "")))
            t.setItem(row, 2, QTableWidgetItem(qty_unit))
            t.setItem(
                row, 3, QTableWidgetItem(f"{v.get('recyclability_percentage', 0)}%")
            )
            t.setItem(row, 4, QTableWidgetItem(recyclable_qty))
            t.setItem(row, 5, QTableWidgetItem(str(v.get("scrap_rate", 0))))

            val_item = QTableWidgetItem(value_str)
            val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(row, 6, val_item)

            warn_item = QTableWidgetItem(warn)
            warn_item.setTextAlignment(Qt.AlignCenter)
            t.setItem(row, 7, warn_item)

            btn = QPushButton("Exclude")
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(
                lambda _, ci=chunk_id, cn=comp_name, i=idx: self._toggle_inclusion(
                    ci, cn, i, False
                )
            )
            t.setCellWidget(row, 8, btn)

        t.update_height()

    def _populate_excluded(self, items):
        t = self.excluded_table
        t.clear_rows()

        for category, chunk_id, comp_name, idx, item, reason in items:
            v = item.get("values", {})
            row = t.rowCount()
            t.insertRow(row)

            qty_unit = f"{v.get('quantity', 0)} {v.get('unit', '')}".strip()

            t.setItem(row, 0, QTableWidgetItem(category))
            t.setItem(row, 1, QTableWidgetItem(v.get("material_name", "")))
            t.setItem(row, 2, QTableWidgetItem(qty_unit))
            t.setItem(
                row, 3, QTableWidgetItem(f"{v.get('recyclability_percentage', 0)}%")
            )
            t.setItem(row, 4, QTableWidgetItem(str(v.get("scrap_rate", 0))))
            t.setItem(row, 5, QTableWidgetItem(reason))

            warn_item = QTableWidgetItem("")
            warn_item.setTextAlignment(Qt.AlignCenter)
            t.setItem(row, 6, warn_item)

            if reason == "Missing Data":
                btn = QPushButton("Fix")
                btn.setStyleSheet("background-color: #f39c12; color: white;")
                btn.clicked.connect(
                    lambda _, ci=chunk_id, cn=comp_name, i=idx: self._prompt_fix(
                        ci, cn, i
                    )
                )
            else:
                btn = QPushButton("Include")
                btn.clicked.connect(
                    lambda _, ci=chunk_id, cn=comp_name, i=idx: self._toggle_inclusion(
                        ci, cn, i, True
                    )
                )

            btn.setFocusPolicy(Qt.NoFocus)
            t.setCellWidget(row, 7, btn)

        t.update_height()

    def _update_summary(
        self,
        total: float,
        included: int,
        total_count: int,
        cat_totals: dict,
        currency: str,
    ):
        self.total_lbl.setText(
            f"Total Recovered Value: {currency} {total:,.2f}".strip()
        )
        self.count_lbl.setText(f"Included: {included} of {total_count} items")

        self.foundation_lbl.setText(
            f"Foundation: {currency} {cat_totals.get('Foundation', 0):,.2f}".strip()
        )
        self.sub_lbl.setText(
            f"Sub Structure: {currency} {cat_totals.get('Sub Structure', 0):,.2f}".strip()
        )
        self.super_lbl.setText(
            f"Super Structure: {currency} {cat_totals.get('Super Structure', 0):,.2f}".strip()
        )
        self.misc_lbl.setText(
            f"Misc: {currency} {cat_totals.get('Misc', 0):,.2f}".strip()
        )

    # ── Actions ──────────────────────────────────────────────────────────

    def _toggle_inclusion(
        self, chunk_id: str, comp_name: str, data_index: int, include: bool
    ):
        data = self.controller.engine.fetch_chunk(chunk_id) or {}
        if comp_name in data and data_index < len(data[comp_name]):
            data[comp_name][data_index]["state"]["included_in_recyclability"] = include
            self.controller.engine.stage_update(chunk_name=chunk_id, data=data)
            self._mark_dirty()
            QTimer.singleShot(0, self.on_refresh)

    def _prompt_fix(self, chunk_id: str, comp_name: str, data_index: int):
        data = self.controller.engine.fetch_chunk(chunk_id) or {}
        if comp_name not in data or data_index >= len(data[comp_name]):
            return

        item = data[comp_name][data_index]
        dialog = RecyclingFixDialog(item, self)
        if dialog.exec():
            new_vals = dialog.get_values()
            import datetime

            item["values"].update(new_vals)
            item["state"]["included_in_recyclability"] = True
            item["meta"]["modified_on"] = datetime.datetime.now().isoformat()
            self.controller.engine.stage_update(chunk_name=chunk_id, data=data)
            self._mark_dirty()
            QTimer.singleShot(0, self.on_refresh)

    def _mark_dirty(self):
        if self.controller and self.controller.engine:
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
