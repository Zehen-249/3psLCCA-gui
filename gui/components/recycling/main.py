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
import time
import datetime



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


_UNIT_DISPLAY = {
    "m2": "m²", "m3": "m³", "sqm": "m²", "cum": "m³",
    "sqft": "sq.ft", "sqyd": "sq.yd",
}


def _fmt_unit(code: str) -> str:
    return _UNIT_DISPLAY.get(code.lower(), code) if code else code


def _recycle_pct(v: dict) -> float:
    """Read recyclability % — checks both field names for backward compat."""
    return float(
        v.get("post_demolition_recovery_percentage")
        or v.get("recyclability_percentage")
        or 0
    )


def is_recyclable_valid(item: dict) -> bool:
    v = item.get("values", {})
    try:
        return all([
            _recycle_pct(v) > 0,
            float(v.get("scrap_rate", 0) or 0) > 0,
            float(v.get("quantity", 0) or 0) > 0,
        ])
    except (TypeError, ValueError):
        return False


def calc_recyclable_qty(item: dict) -> float:
    """Recyclable Qty = quantity × (recyclability% / 100)"""
    v = item.get("values", {})
    try:
        return float(v.get("quantity", 0) or 0) * (_recycle_pct(v) / 100)
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

        h = self.horizontalHeader()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Category
        h.setSectionResizeMode(1, QHeaderView.Stretch)           # Material
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionMode(QTableWidget.NoSelection)
        self.verticalHeader().setDefaultSectionSize(35)
        self.verticalHeader().setVisible(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self._set_column_widths()

    def _set_column_widths(self):
        if self.is_included:
            # Cat(RTC) | Material(S) | Qty | Recycle% | RecyclableQty | ScrapRate | RecoveredVal | Warn | Action
            for col, w in [(2, 90), (3, 100), (4, 115), (5, 80), (6, 125), (7, 70), (8, 155)]:
                self.setColumnWidth(col, w)
        else:
            # Cat(RTC) | Material(S) | Qty | Recycle% | ScrapRate | Reason | Warn | Action
            for col, w in [(2, 90), (3, 100), (4, 80), (5, 110), (6, 70), (7, 155)]:
                self.setColumnWidth(col, w)

    def sizeHint(self):
        header_h = self.horizontalHeader().height() or 35
        rows_h = self.rowCount() * self.verticalHeader().defaultSectionSize()
        return QSize(super().sizeHint().width(), max(60, header_h + rows_h + 10))

    def minimumSizeHint(self):
        return self.sizeHint()

    def update_height(self):
        self.updateGeometry()

    def clear_rows(self):
        self.setRowCount(0)
        self.updateGeometry()


# ---------------------------------------------------------------------------
# RecyclingWidget — main tab
# ---------------------------------------------------------------------------


class Recycling(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setObjectName("RecyclingWidget")

        self._details_visible = False

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
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

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

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

        result = self._compute()

        # Augment included items with per-row warning for display
        included_with_warn = [
            (cat, chunk_id, comp, idx, item, value,
             "! Zero Qty" if float(item.get("values", {}).get("quantity", 0) or 0) == 0 else "")
            for cat, chunk_id, comp, idx, item, value in result["included_items"]
        ]

        self._populate_included(included_with_warn, result["currency"])
        self._populate_excluded(result["excluded_items"])
        self._update_summary(
            result["total_recovered_value"],
            result["included_count"],
            result["total_count"],
            result["cat_totals"],
            result["currency"],
        )

    def _populate_included(self, items, currency: str):
        t = self.included_table
        t.clear_rows()

        for category, chunk_id, comp_name, idx, item, value, warn in items:
            v = item.get("values", {})
            row = t.rowCount()
            t.insertRow(row)

            qty_unit = f"{v.get('quantity', 0)} {_fmt_unit(v.get('unit', ''))}".strip()
            recyclable_qty = (
                f"{calc_recyclable_qty(item):.2f} {_fmt_unit(v.get('unit', ''))}".strip()
            )
            value_str = f"{currency} {value:,.2f}".strip()

            t.setItem(row, 0, QTableWidgetItem(category))
            t.setItem(row, 1, QTableWidgetItem(v.get("material_name", "")))
            t.setItem(row, 2, QTableWidgetItem(qty_unit))
            t.setItem(row, 3, QTableWidgetItem(f"{_recycle_pct(v):.1f}%"))
            t.setItem(row, 4, QTableWidgetItem(recyclable_qty))
            t.setItem(row, 5, QTableWidgetItem(str(v.get("scrap_rate", 0))))

            val_item = QTableWidgetItem(value_str)
            val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(row, 6, val_item)

            warn_item = QTableWidgetItem(warn)
            warn_item.setTextAlignment(Qt.AlignCenter)
            t.setItem(row, 7, warn_item)

            edit_btn = QPushButton("Edit")
            edit_btn.setFocusPolicy(Qt.NoFocus)
            edit_btn.clicked.connect(
                lambda _, ci=chunk_id, cn=comp_name, i=idx, it=item: self._open_recyclability_edit(ci, cn, i, it)
            )
            excl_btn = QPushButton("Exclude")
            excl_btn.setFocusPolicy(Qt.NoFocus)
            excl_btn.clicked.connect(
                lambda _, ci=chunk_id, cn=comp_name, i=idx: self._toggle_inclusion(ci, cn, i, False)
            )
            t.setCellWidget(row, 8, self._btn_container(edit_btn, excl_btn))

        t.update_height()

    def _populate_excluded(self, items):
        t = self.excluded_table
        t.clear_rows()

        for category, chunk_id, comp_name, idx, item, reason in items:
            v = item.get("values", {})
            row = t.rowCount()
            t.insertRow(row)

            qty_unit = f"{v.get('quantity', 0)} {_fmt_unit(v.get('unit', ''))}".strip()

            t.setItem(row, 0, QTableWidgetItem(category))
            t.setItem(row, 1, QTableWidgetItem(v.get("material_name", "")))
            t.setItem(row, 2, QTableWidgetItem(qty_unit))
            t.setItem(row, 3, QTableWidgetItem(f"{_recycle_pct(v):.1f}%"))
            t.setItem(row, 4, QTableWidgetItem(str(v.get("scrap_rate", 0))))
            t.setItem(row, 5, QTableWidgetItem(reason))

            warn_item = QTableWidgetItem("")
            warn_item.setTextAlignment(Qt.AlignCenter)
            t.setItem(row, 6, warn_item)

            edit_btn = QPushButton("Edit")
            edit_btn.setFocusPolicy(Qt.NoFocus)
            edit_btn.clicked.connect(
                lambda _, ci=chunk_id, cn=comp_name, i=idx, it=item: self._open_recyclability_edit(ci, cn, i, it)
            )

            if reason == "Missing Data":
                t.setCellWidget(row, 7, self._btn_container(edit_btn))
            else:
                incl_btn = QPushButton("Include")
                incl_btn.setFocusPolicy(Qt.NoFocus)
                incl_btn.clicked.connect(
                    lambda _, ci=chunk_id, cn=comp_name, i=idx: self._toggle_inclusion(ci, cn, i, True)
                )
                t.setCellWidget(row, 7, self._btn_container(edit_btn, incl_btn))

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

    def _btn_container(self, *buttons) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(4)
        for btn in buttons:
            h.addWidget(btn)
        return w

    def _open_recyclability_edit(self, chunk_id: str, comp_name: str, data_index: int, item: dict):
        from ..structure.widgets.manager import MaterialDialog
        dialog = MaterialDialog(comp_name, parent=self, data=item, recyclability_only=True)
        if dialog.exec():
            vals = dialog.get_values()
            data = self.controller.engine.fetch_chunk(chunk_id) or {}
            if comp_name in data and data_index < len(data[comp_name]):
                target = data[comp_name][data_index]
                target["values"]["post_demolition_recovery_percentage"] = vals.get("post_demolition_recovery_percentage", 0.0)
                target["values"]["scrap_rate"] = vals.get("scrap_rate", 0.0)
                target["state"]["included_in_recyclability"] = vals.get("_included_in_recyclability", True)
                target["meta"]["modified_on"] = datetime.datetime.now().isoformat()
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

    def _compute(self) -> dict:
        """
        Core calculation logic shared by on_refresh(), validate(), and get_data().
        Returns raw computed data without touching any UI.
        """
        cat_totals = {label: 0.0 for _, label in CHUNKS}
        included_items = []
        excluded_items = []
        total_value = 0.0
        total_count = 0
        included_count = 0

        if not self.controller or not getattr(self.controller, "engine", None):
            return {
                "total_recovered_value": 0.0,
                "cat_totals": cat_totals,
                "included_count": 0,
                "total_count": 0,
                "included_items": [],
                "excluded_items": [],
                "currency": "",
            }

        currency = self._get_currency()

        for chunk_id, category in CHUNKS:
            data = self.controller.engine.fetch_chunk(chunk_id) or {}
            for comp_name, items in data.items():
                for idx, item in enumerate(items):
                    if item.get("state", {}).get("in_trash", False):
                        continue

                    total_count += 1
                    valid = is_recyclable_valid(item)
                    included = item.get("state", {}).get("included_in_recyclability", True)

                    if valid and included:
                        included_count += 1
                        value = calc_recovered_value(item)
                        total_value += value
                        cat_totals[category] += value
                        included_items.append(
                            (category, chunk_id, comp_name, idx, item, value)
                        )
                    else:
                        reason = "Missing Data" if not valid else "User Excluded"
                        excluded_items.append(
                            (category, chunk_id, comp_name, idx, item, reason)
                        )

        return {
            "total_recovered_value": total_value,
            "cat_totals": cat_totals,
            "included_count": included_count,
            "total_count": total_count,
            "included_items": included_items,
            "excluded_items": excluded_items,
            "currency": currency,
        }

    def validate(self) -> dict:
        result = self._compute()
        warnings = []

        if result["total_count"] == 0:
            warnings.append(
                "No materials found — add items in the Construction Work Data section."
            )
        elif result["total_recovered_value"] == 0.0:
            warnings.append(
                f"Total recovered value is 0 — "
                f"{result['included_count']} of {result['total_count']} items are included."
            )

        missing = sum(
            1 for *_, reason in result["excluded_items"] if reason == "Missing Data"
        )
        if missing:
            warnings.append(
                f"{missing} item{'s' if missing != 1 else ''} excluded — "
                f"missing recyclability % or scrap rate data."
            )

        return {"errors": [], "warnings": warnings}

    def get_data(self) -> dict:
        result = self._compute()
        currency = result["currency"]
        included = [
            {
                "material_id": item.get("id", ""),
                "category": cat,
                "component": comp,
                "material": item.get("values", {}).get("material_name", ""),
                "quantity": float(item.get("values", {}).get("quantity", 0) or 0),
                "unit": item.get("values", {}).get("unit", ""),
                "recyclability_pct": _recycle_pct(item.get("values", {})),
                "recyclable_qty": calc_recyclable_qty(item),
                "scrap_rate": float(item.get("values", {}).get("scrap_rate", 0) or 0),
                "recovered_value": value,
            }
            for cat, chunk_id, comp, idx, item, value in result["included_items"]
        ]
        return {
            "chunk": "recycling_data",
            "data": {
                "included_items": included,
                "cat_totals": result["cat_totals"],
                "total_recovered_value": result["total_recovered_value"],
                "included_count": result["included_count"],
                "total_count": result["total_count"],
                "currency": currency,
            },
        }

    def showEvent(self, event):
        super().showEvent(event)
        self.on_refresh()
