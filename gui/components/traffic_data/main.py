from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)
from PySide6.QtCore import Qt

from ..base_widget import ScrollableForm
from ..utils.form_builder.form_definitions import FieldDef, Section
from ..utils.form_builder.form_builder import build_form
from ..utils.remarks_editor import RemarksEditor

LANE_TYPES = [
    {
        "code": "SL",
        "name": "Single Lane",
        "width": 3.75,
        "capacity": 435,
        "velocity_class": "SL",
    },
    {
        "code": "IL",
        "name": "Intermediate Lane",
        "width": 5.5,
        "capacity": 1158,
        "velocity_class": "IL",
    },
    {
        "code": "2L",
        "name": "Two Lane (Two Way)",
        "width": 7.0,
        "capacity": 2400,
        "velocity_class": "2L",
    },
    {
        "code": "2L_1W",
        "name": "Two Lane (One Way)",
        "width": 7.0,
        "capacity": 2700,
        "velocity_class": "4L",
    },
    {
        "code": "3L_1W",
        "name": "Three Lane (One Way)",
        "width": 10.5,
        "capacity": 4200,
        "velocity_class": "6L",
    },
    {
        "code": "4L",
        "name": "Four Lane (Two Way)",
        "width": 7.0,
        "capacity": 5400,
        "velocity_class": "4L",
    },
    {
        "code": "6L",
        "name": "Six Lane (Two Way)",
        "width": 10.5,
        "capacity": 8400,
        "velocity_class": "6L",
    },
    {
        "code": "8L",
        "name": "Eight Lane (Two Way)",
        "width": 14.0,
        "capacity": 13600,
        "velocity_class": "8L",
    },
    {
        "code": "EW4",
        "name": "4 Lane Expressway (Two Way)",
        "width": None,
        "capacity": 5000,
        "velocity_class": "EW",
    },
    {
        "code": "EW6",
        "name": "6 Lane Expressway (Two Way)",
        "width": None,
        "capacity": 7500,
        "velocity_class": "EW",
    },
    {
        "code": "EW8",
        "name": "8 Lane Expressway (Two Way)",
        "width": None,
        "capacity": 9200,
        "velocity_class": "EW",
    },
]

_BY_NAME = {lt["name"]: lt for lt in LANE_TYPES}
_LANE_NAMES = [lt["name"] for lt in LANE_TYPES]

_VEHICLES = [
    ("small_cars", "Small Car"),
    ("big_cars", "Big Car"),
    ("two_wheelers", "Two Wheeler"),
    ("o_buses", "Ordinary Buses"),
    ("d_buses", "Deluxe Buses"),
    ("lcv", "LCV"),
    ("hcv", "HCV"),
    ("mcv", "MCV"),
]
_HAS_PWR = {"hcv", "mcv"}


BRIDGE_CHUNK = "bridge_data"
CHUNK = "traffic_and_road_data"
BASE_DOCS_URL = "https://yourdocs.com/traffic/"

TRAFFIC_FIELDS = [
    Section("Alternate Road Configuration"),
    FieldDef(
        "alternate_road_carriageway",
        "Alternate Road Carriageway",
        "Lane configuration of the alternate route — auto-fills capacity and width.",
        "combo",
        options=_LANE_NAMES,
    ),
    FieldDef(
        "carriage_width_in_m",
        "Carriageway Width",
        "",
        "float",
        (0.0, 999.0, 2),
        unit="m",
    ),
    FieldDef(
        "hourly_capacity", "Hourly Capacity", "", "int", (0, 99999), unit="veh/hr"
    ),
    Section("Accident Severity Distribution"),
    FieldDef(
        "severity_minor", "Minor Injury", "", "float", (0.0, 100.0, 2), unit="(%)"
    ),
    FieldDef(
        "severity_major", "Major Injury", "", "float", (0.0, 100.0, 2), unit="(%)"
    ),
    FieldDef(
        "severity_fatal", "Fatal Accident", "", "float", (0.0, 100.0, 2), unit="(%)"
    ),
    Section("Road Parameters"),
    FieldDef(
        "road_roughness_mm_per_km",
        "Road Roughness",
        "",
        "float",
        (0.0, 99_999.0, 2),
        unit="(mm/km)",
    ),
    FieldDef(
        "road_rise_m_per_km", "Road Rise", "", "float", (0.0, 9_999.0, 3), unit="(m/km)"
    ),
    FieldDef(
        "road_fall_m_per_km", "Road Fall", "", "float", (0.0, 9_999.0, 3), unit="(m/km)"
    ),
    FieldDef(
        "additional_reroute_distance_km",
        "Additional Reroute Distance",
        "",
        "float",
        (0.0, 9_999.0, 3),
        unit="(km)",
    ),
    FieldDef(
        "additional_travel_time_min",
        "Additional Travel Time",
        "",
        "float",
        (0.0, 9_999.0, 3),
        unit="(min)",
    ),
    FieldDef(
        "crash_rate_accidents_per_million_km",
        "Crash Rate",
        "",
        "float",
        (0.0, 999_999.0, 2),
        unit="(acc / M km)",
    ),
    FieldDef(
        "work_zone_multiplier", "Work Zone Multiplier", "", "float", (0.0, 99.0, 2)
    ),
    Section("Traffic Flow"),
    FieldDef("num_peak_hours", "Number of Peak Hours", "", "int", (1, 12)),
]

OUTSIDE_INDIA_FIELDS = [
    FieldDef(
        "road_user_cost_per_day",
        "Road User Cost per Day",
        "",
        "float",
        (0.0, 1e15, 2),
        unit="/ day",
    ),
]


PROJECT_MODE_FIELDS = [
    FieldDef(
        "mode",
        "Calculation Mode",
        "",
        "combo",
        options=["INDIA", "GLOBAL"],
    ),
]

# ── Vehicle Table ─────────────────────────────────────────────────────────────


class _VehicleTrafficTable(QTableWidget):
    def __init__(self, on_change, parent=None):
        super().__init__(len(_VEHICLES), 4, parent)
        self.on_change = on_change
        self.setHorizontalHeaderLabels(
            ["Vehicle Type", "Vehicles / Day", "Accident %", "PWR"]
        )
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(36)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionMode(QTableWidget.NoSelection)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self._vpd, self._acc, self._pwr = {}, {}, {}
        for row, (key, label) in enumerate(_VEHICLES):
            item = QTableWidgetItem(label)
            item.setFlags(Qt.ItemIsEnabled)
            self.setItem(row, 0, item)

            vpd = QSpinBox()
            vpd.setRange(0, 9_999_999)
            vpd.setButtonSymbols(QSpinBox.NoButtons)
            vpd.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            vpd.valueChanged.connect(self.on_change)
            self.setCellWidget(row, 1, vpd)
            self._vpd[key] = vpd

            acc = QDoubleSpinBox()
            acc.setRange(0.0, 100.0)
            acc.setDecimals(2)
            acc.setButtonSymbols(QDoubleSpinBox.NoButtons)
            acc.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            acc.valueChanged.connect(self.on_change)
            self.setCellWidget(row, 2, acc)
            self._acc[key] = acc

            if key in _HAS_PWR:
                pwr = QDoubleSpinBox()
                pwr.setRange(0.0, 999.9)
                pwr.setDecimals(2)
                pwr.setButtonSymbols(QDoubleSpinBox.NoButtons)
                pwr.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                pwr.valueChanged.connect(self.on_change)
                self.setCellWidget(row, 3, pwr)
                self._pwr[key] = pwr
            else:
                na = QTableWidgetItem("—")
                na.setFlags(Qt.ItemIsEnabled)
                na.setTextAlignment(Qt.AlignCenter)
                self.setItem(row, 3, na)

        self.update_height()

    def update_height(self):
        h = self.horizontalHeader().height() or 35
        for r in range(self.rowCount()):
            h += self.rowHeight(r)
        self.setFixedHeight(h + 10)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.viewport().width()
        self.setColumnWidth(0, int(w * 0.35))
        self.setColumnWidth(1, int(w * 0.25))
        self.setColumnWidth(2, int(w * 0.20))
        self.setColumnWidth(3, int(w * 0.20))

    def collect_to_dict(self) -> dict:
        return {
            key: {
                "vehicles_per_day": int(self._vpd[key].value()),
                "accident_percentage": float(self._acc[key].value()),
                "pwr": float(self._pwr[key].value()) if key in _HAS_PWR else 0.0,
            }
            for key, _ in _VEHICLES
        }

    def load_from_dict(self, data: dict):
        self.blockSignals(True)
        for key, _ in _VEHICLES:
            v = data.get(key, {})
            self._vpd[key].setValue(int(v.get("vehicles_per_day", 0)))
            self._acc[key].setValue(float(v.get("accident_percentage", 0.0)))
            if key in _HAS_PWR:
                self._pwr[key].setValue(float(v.get("pwr", 0.0)))
        self.blockSignals(False)


# ── Peak Hours Table ──────────────────────────────────────────────────────────


class _PeakHoursTable(QTableWidget):
    def __init__(self, on_change, parent=None):
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Hour Category", "Traffic Proportion (%)"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(36)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self._on_change = on_change
        self._spinboxes = []
        self._other_label = None
        self._rebuilding = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.viewport().width()
        self.setColumnWidth(0, int(w * 0.60))
        self.setColumnWidth(1, int(w * 0.40))

    def rebuild(self, n: int):
        self._rebuilding = True
        old_vals = [sb.value() for sb in self._spinboxes]
        self.setRowCount(n + 1)
        self._spinboxes.clear()

        for i in range(n):
            self.setItem(i, 0, QTableWidgetItem(f"Peak Hour {i + 1}"))
            sb = QDoubleSpinBox()
            sb.setRange(0.0, 100.0)
            sb.setDecimals(2)
            sb.setSuffix(" %")
            sb.setButtonSymbols(QDoubleSpinBox.NoButtons)
            sb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sb.setValue(old_vals[i] if i < len(old_vals) else 4.0)
            sb.valueChanged.connect(self._on_value_changed)
            self.setCellWidget(i, 1, sb)
            self._spinboxes.append(sb)

        self.setItem(n, 0, QTableWidgetItem("Other Hours (Average)"))
        self._other_label = QLabel("—")
        self._other_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._other_label.setStyleSheet("padding-right: 10px; font-weight: bold;")
        self.setCellWidget(n, 1, self._other_label)

        self._rebuilding = False
        self._recalculate()
        self.update_height()

    def update_height(self):
        h = self.horizontalHeader().height() or 35
        for r in range(self.rowCount()):
            h += self.rowHeight(r)
        self.setFixedHeight(h + 10)

    def _on_value_changed(self):
        if not self._rebuilding:
            self._recalculate()
            self._on_change()

    def _recalculate(self):
        if self._rebuilding or not self._spinboxes:
            return
        total = sum(sb.value() for sb in self._spinboxes)
        for sb in self._spinboxes:
            others = total - sb.value()
            sb.blockSignals(True)
            sb.setMaximum(max(0.0, 100.0 - others))
            sb.blockSignals(False)

        rem = 24 - len(self._spinboxes)
        avg = (
            max(0.0, (100.0 - sum(sb.value() for sb in self._spinboxes)) / rem)
            if rem > 0
            else 0
        )
        if self._other_label:
            self._other_label.setText(f"{avg:.2f} %")

    def collect_to_dict(self) -> dict:
        return {
            f"peak_hour_{i+1}": float(sb.value() / 100.0)
            for i, sb in enumerate(self._spinboxes)
        }

    def load_from_dict(self, data: dict):
        self._rebuilding = True
        for i, sb in enumerate(self._spinboxes):
            key = f"peak_hour_{i+1}"
            if key in data:
                sb.setValue(float(data[key]) * 100.0)
        self._rebuilding = False
        self._recalculate()


# ── Main Class ────────────────────────────────────────────────────────────────


class TrafficData(ScrollableForm):
    def __init__(self, controller=None):
        super().__init__(controller=controller, chunk_name=CHUNK)
        self._suppress_lane_signal = False
        self._build_ui()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_mode_from_country()

    def _on_severity_changed(self):
        sender = self.sender()
        minor = self.severity_minor
        major = self.severity_major
        fatal = self.severity_fatal

        if sender == minor:
            # Adjust fatal first, then major if fatal exhausted
            remaining = max(0.0, 100.0 - minor.value())
            if major.value() <= remaining:
                # Major fits, fatal takes the rest
                fatal.blockSignals(True)
                fatal.setValue(remaining - major.value())
                fatal.blockSignals(False)
            else:
                # Fatal exhausted (0), major absorbs the rest
                fatal.blockSignals(True)
                fatal.setValue(0.0)
                fatal.blockSignals(False)
                major.blockSignals(True)
                major.setValue(remaining)
                major.blockSignals(False)

        elif sender == major:
            # Only adjust fatal
            total_fixed = minor.value() + major.value()
            if total_fixed > 100.0:
                sender.blockSignals(True)
                sender.setValue(100.0 - minor.value())
                sender.blockSignals(False)
            fatal.blockSignals(True)
            fatal.setValue(max(0.0, 100.0 - minor.value() - major.value()))
            fatal.blockSignals(False)

        elif sender == fatal:
            # Only adjust major
            total_fixed = minor.value() + fatal.value()
            if total_fixed > 100.0:
                sender.blockSignals(True)
                sender.setValue(100.0 - minor.value())
                sender.blockSignals(False)
            major.blockSignals(True)
            major.setValue(max(0.0, 100.0 - minor.value() - fatal.value()))
            major.blockSignals(False)

        self._on_field_changed()

    def _build_ui(self):
        main_form = self.form

        # ── Mode Selector ─────────────────────────────────────────────────────
        _temp_form = self.form
        self.form = main_form
        build_form(self, PROJECT_MODE_FIELDS, BASE_DOCS_URL)
        self.form = _temp_form

        self.mode.setFixedWidth(220)
        self.mode.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # Constrain the parent section container too
        if self.mode.parentWidget():
            self.mode.parentWidget().setFixedWidth(300)
            self.mode.parentWidget().setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Wire mode combo to stack switcher
        self.mode.currentIndexChanged.connect(self._on_mode_changed)

        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        # ── Panel: India ──────────────────────────────────────────────────────
        india_widget = QWidget()
        india_layout = QFormLayout(india_widget)
        india_layout.setContentsMargins(0, 0, 0, 0)

        india_layout.addRow(QLabel("<b>Vehicle Traffic Data</b>"))
        self._vehicle_table = _VehicleTrafficTable(on_change=self._on_field_changed)
        india_layout.addRow(self._vehicle_table)

        self._force_free_flow = QCheckBox("Force free-flow conditions off-peak")
        self._force_free_flow.stateChanged.connect(self._on_field_changed)
        india_layout.addRow(self._force_free_flow)

        # Inject TRAFFIC_FIELDS into india_layout via build_form
        _temp_form = self.form
        self.form = india_layout
        build_form(self, TRAFFIC_FIELDS, BASE_DOCS_URL)
        self.form = _temp_form

        # Wire severity fields for auto-adjustment
        self.severity_minor.valueChanged.connect(self._on_severity_changed)
        self.severity_major.valueChanged.connect(self._on_severity_changed)
        self.severity_fatal.valueChanged.connect(self._on_severity_changed)

        india_layout.addRow(QLabel("<b>Peak Hour Distribution</b>"))
        self._peak_table = _PeakHoursTable(on_change=self._on_field_changed)
        india_layout.addRow(self._peak_table)

        # Wire up auto-fill and peak count listeners
        if hasattr(self, "alternate_road_carriageway"):
            self.alternate_road_carriageway.currentIndexChanged.connect(
                self._on_lane_changed
            )
        if hasattr(self, "num_peak_hours"):
            self.num_peak_hours.valueChanged.connect(self._on_peak_count_changed)
            self._peak_table.rebuild(self.num_peak_hours.value())

        self._stack.addWidget(india_widget)  # index 0

        # ── Panel: Outside India ──────────────────────────────────────────────
        outside_widget = QWidget()
        outside_layout = QFormLayout(outside_widget)
        outside_layout.setContentsMargins(0, 0, 0, 0)

        _temp_form = self.form
        self.form = outside_layout
        build_form(self, OUTSIDE_INDIA_FIELDS, BASE_DOCS_URL)
        self.form = _temp_form

        self._stack.addWidget(outside_widget)  # index 1

        # ── Shared bottom widgets ─────────────────────────────────────────────
        main_form.addRow(self._stack)

        self._remarks = RemarksEditor(
            title="Remarks / Notes", on_change=self._on_field_changed
        )
        main_form.addRow(self._remarks)

        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 10, 0, 10)
        btn_layout.setSpacing(10)

        btn_clear = QPushButton("Clear All")
        btn_clear.setMinimumHeight(35)
        btn_clear.setFixedWidth(120)
        btn_clear.clicked.connect(self.clear_all)
        btn_clear.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()

        btn_widget = QWidget()
        btn_widget.setLayout(btn_row)
        btn_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        main_form.addRow(btn_widget)

    # ── Slot handlers ─────────────────────────────────────────────────────────

    def _on_mode_changed(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self._on_field_changed()  # This saves the mode to the chunk

    def _on_lane_changed(self, _idx: int):
        if self._suppress_lane_signal:
            return
        lane = _BY_NAME.get(self.alternate_road_carriageway.currentText())
        if not lane:
            return
        w = lane.get("width")
        self.carriage_width_in_m.setValue(float(w) if w is not None else 0.0)
        self.hourly_capacity.setValue(int(lane.get("capacity", 0)))
        self._on_field_changed()

    def _on_peak_count_changed(self, n: int):
        self._peak_table.rebuild(n)
        self._on_field_changed()

    def _sync_mode_from_country(self):
        if not self.controller or not self.controller.engine:
            return

        bridge = self.controller.engine.fetch_chunk(BRIDGE_CHUNK) or {}
        country = bridge.get("location_country", "GLOBAL")

        is_india = country.strip().upper() == "INDIA"

        self.mode.setEnabled(is_india)

        if not is_india:
            # Empty chunk OR non-India country → force Outside India
            idx = self.mode.findText("GLOBAL")
            if idx >= 0:
                self.mode.blockSignals(True)
                self.mode.setCurrentIndex(idx)
                self.mode.blockSignals(False)
                self._stack.setCurrentIndex(idx)
        else:
            self._stack.setCurrentIndex(self.mode.currentIndex())

    # ── Data collection ───────────────────────────────────────────────────────

    def collect_data(self) -> dict:
        """Collect ALL UI data into a single dict for saving."""
        # 1. All registered scalar fields (TRAFFIC_FIELDS + OUTSIDE_INDIA_FIELDS)
        #    via _field_map — handles QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, etc.
        data = super().get_data_dict()

        # 2. Non-field-map fields
        data["mode"] = self.mode.currentText()

        data["remarks"] = self._remarks.to_html()
        data["force_free_flow_off_peak"] = bool(self._force_free_flow.isChecked())

        # 3. Vehicle table — merge with existing engine data to preserve extra keys
        existing_veh = {}
        if self.controller and self.controller.engine:
            existing_veh = (self.controller.engine.fetch_chunk(CHUNK) or {}).get(
                "vehicle_data", {}
            )
        veh_table_dict = self._vehicle_table.collect_to_dict()
        merged_veh = {}
        for key, _ in _VEHICLES:
            base = dict(existing_veh.get(key, {}))
            base.update(veh_table_dict.get(key, {}))
            merged_veh[key] = base
        data["vehicle_data"] = merged_veh

        # 4. Peak hour distribution
        data["peak_hour_distribution"] = self._peak_table.collect_to_dict()

        return data

    # ── Data loading ──────────────────────────────────────────────────────────

    def load_data(self, data: dict):
        """Populate all UI widgets from a saved dict."""
        if not data:
            return
        self.blockSignals(True)
        self._suppress_lane_signal = True
        try:
            # 1. Non-field-map fields
            self._remarks.from_html(data.get("remarks", ""))
            self._force_free_flow.setChecked(
                bool(data.get("force_free_flow_off_peak", False))
            )

            # 2. All scalar fields via base — block self.mode separately to
            #    prevent _on_mode_changed firing and triggering autosave during load
            self.mode.blockSignals(True)
            super().load_data_dict(data)
            self.mode.blockSignals(False)

            # 3. Sync stack to loaded mode value (since signal was blocked)
            self._stack.setCurrentIndex(self.mode.currentIndex())

            # 4. Vehicle table
            self._vehicle_table.load_from_dict(data.get("vehicle_data", {}))

            # 5. Peak hours table
            n_peak = int(data.get("num_peak_hours", 1))
            if hasattr(self, "num_peak_hours"):
                self.num_peak_hours.blockSignals(True)
                self.num_peak_hours.setValue(n_peak)
                self.num_peak_hours.blockSignals(False)
            self._peak_table.rebuild(n_peak)
            self._peak_table.load_from_dict(data.get("peak_hour_distribution", {}))

        finally:
            self.blockSignals(False)
            self._suppress_lane_signal = False
            self._vehicle_table.update_height()
            self._peak_table.update_height()
            # Force stack to correct height after load
            current = self._stack.currentWidget()
            if current:
                self._stack.setFixedHeight(current.sizeHint().height())

    # ── Clear all ─────────────────────────────────────────────────────────────

    def clear_all(self):
        self.blockSignals(True)
        self._vehicle_table.load_from_dict({})
        self._peak_table.rebuild(1)
        self._remarks.clear_content()
        # Reset all registered scalar fields to their minimum value
        for f in PROJECT_MODE_FIELDS + TRAFFIC_FIELDS + OUTSIDE_INDIA_FIELDS:
            if isinstance(f, FieldDef):
                attr = getattr(self, f.key, None)
                if isinstance(attr, (QSpinBox, QDoubleSpinBox)):
                    attr.setValue(attr.minimum())
        self.blockSignals(False)
        self._on_field_changed()

    # ── Base overrides ────────────────────────────────────────────────────────

    def get_data_dict(self) -> dict:
        """Override base: delegate to collect_data() for full save."""
        return self.collect_data()

    def load_data_dict(self, data: dict):
        """Override base: delegate to load_data() for full load."""
        self.load_data(data)

    def refresh_from_engine(self):
        """Override base: load full chunk including tables."""
        if not self.controller or not self.controller.engine:
            return
        if not self.controller.engine.is_active() or not self.chunk_name:
            return
        data = self.controller.engine.fetch_chunk(self.chunk_name)
        if data:
            self.load_data(data)
