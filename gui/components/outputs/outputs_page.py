"""
gui/components/outputs/outputs_page.py
"""

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from gui.components.base_widget import ScrollableForm
from gui.components.utils.form_builder.form_definitions import ValidationStatus

CHUNK = "outputs_data"


class OutputsPage(ScrollableForm):

    navigate_requested = Signal(str)

    def __init__(self, controller=None):
        super().__init__(controller=controller, chunk_name=CHUNK)
        self._pages = {}
        self._build_ui()

    def _build_ui(self):
        f = self.form
        header = QLabel("Outputs")
        bold = QFont()
        bold.setBold(True)
        bold.setPointSize(13)
        header.setFont(bold)
        f.addRow(header)

        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 8, 0, 8)

        self.btn_calculate = QPushButton("Validate  ▶")
        self.btn_calculate.setMinimumHeight(38)
        self.btn_calculate.setFixedWidth(160)
        self.btn_calculate.clicked.connect(self.run_validation)
        btn_layout.addWidget(self.btn_calculate)
        btn_layout.addStretch()
        f.addRow(btn_row)

        self._status_widget = QWidget()
        self._status_layout = QVBoxLayout(self._status_widget)
        self._status_layout.setContentsMargins(0, 0, 0, 0)
        f.addRow(self._status_widget)

        self._show_idle()

    # ── Status area ───────────────────────────────────────────────────────────

    def _clear_status(self):
        while self._status_layout.count():
            item = self._status_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)

    def _show_idle(self):
        self._clear_status()
        note = QLabel("Press Calculate to validate all pages.")
        note.setStyleSheet("color: gray; font-style: italic;")
        self._status_layout.addWidget(note)

    def show_results(self, all_errors: dict, all_warnings: dict):
        """Show errors and warnings together. Proceed button only when no errors."""
        self._clear_status()

        if all_errors:
            banner = QGroupBox()
            banner.setStyleSheet("QGroupBox { border: 2px solid #dc3545; padding: 8px; }")
            layout = QVBoxLayout(banner)
            title = QLabel("🛑  Calculation Blocked — Please fix the errors below.")
            title.setStyleSheet("color: #b02a37; font-weight: bold;")
            layout.addWidget(title)
            self._status_layout.addWidget(banner)
            self._status_layout.addSpacing(10)

            for page, issues in all_errors.items():
                self._status_layout.addWidget(self._create_card(page, issues, "❌"))

        if all_warnings:
            if all_errors:
                self._status_layout.addSpacing(12)
            banner = QGroupBox()
            banner.setStyleSheet("QGroupBox { border: 2px solid #ffc107; padding: 8px; }")
            layout = QVBoxLayout(banner)
            label = "⚠️  Warnings — fix errors above before proceeding." if all_errors \
                else "⚠️  Warnings — Data looks unusual but you can proceed."
            title = QLabel(label)
            title.setStyleSheet("color: #856404; font-weight: bold;")
            layout.addWidget(title)
            self._status_layout.addWidget(banner)
            self._status_layout.addSpacing(10)

            for page, issues in all_warnings.items():
                self._status_layout.addWidget(self._create_card(page, issues, "🟡"))

        if not all_errors and all_warnings:
            run_btn = QPushButton("Proceed with Calculation ▶")
            run_btn.setMinimumHeight(35)
            run_btn.clicked.connect(self._on_proceed)
            self._status_layout.addWidget(run_btn)

        self._status_layout.addStretch()
        self._save_state("issues", {"errors": all_errors, "warnings": all_warnings})

    def show_success(self):
        self._clear_status()
        banner = QGroupBox()
        banner.setStyleSheet("QGroupBox { border: 2px solid #198754; padding: 8px; }")
        layout = QVBoxLayout(banner)
        layout.addWidget(QLabel("✅  All checks passed — Ready to calculate."))
        self._status_layout.addWidget(banner)
        self._status_layout.addStretch()
        self._save_state("success", {"errors": {}, "warnings": {}})

    # ── Validation / calculation ───────────────────────────────────────────────

    def register_pages(self, widget_map: dict):
        self._pages = {
            name: page
            for name, page in widget_map.items()
            if name != "Outputs" and hasattr(page, "validate")
        }

    def run_validation(self):
        all_errors = {}
        all_warnings = {}

        for name, page in self._pages.items():
            result = page.validate()

            if isinstance(result, dict):
                errors = result.get("errors", [])
                warnings = result.get("warnings", [])
                if errors:
                    all_errors[name] = errors
                if warnings:
                    all_warnings[name] = warnings
            else:
                # legacy tuple format (status, issues)
                status, issues = result
                if status == ValidationStatus.ERROR and issues:
                    all_errors[name] = issues
                elif status == ValidationStatus.WARNING and issues:
                    all_warnings[name] = issues

        if all_errors or all_warnings:
            self.show_results(all_errors, all_warnings)
        else:
            self.show_success()
            self.run_calculation()

    def run_calculation(self):
        from pprint import pprint
        all_data = {}
        for name, page in self._pages.items():
            if hasattr(page, "get_data"):
                result = page.get_data()
                # print("===============================")
                # pprint(result)
                # print("===============================")
                all_data[result["chunk"]] = result["data"]
        
        # Print to check
        print("=========INPUT=OBJECT=====================")
        pprint(all_data)
        print("==========================================")

        # Pass all_data to calculator
        is_global, data_object = self._prepare_data_object(all_data)
        wpi_metadata = None
        if not is_global:
            # If Global than WPI is not needed
            wpi_metadata = self._prepare_wpi_object(all_data)
        life_cycle_construction_cost_breakdown = self._prepare_life_cycle_construction_cost(all_data)

        from three_ps_lcca_core.core.main import run_full_lcc_analysis
        try:
            results = run_full_lcc_analysis(
                data_object, life_cycle_construction_cost_breakdown, wpi=wpi_metadata, debug=False
            )

            print("LCC Analysis Completed Successfully.")
            print(results)

        except Exception as e:
            print("Error during LCC analysis:")
            print(e)
    
    #==========Prepare-Mapping-for-Core==============================================
    
    def _prepare_life_cycle_construction_cost(self, data: dict):
        """
        This function creates the life cycle construction cost breakdown dict using the data from saved chunks.
        ex. life_cycle_construction_cost_breakdown = {
                    "initial_construction_cost": 12843979.44,
                    "initial_carbon_emissions_cost": 2065434.91,
                    "superstructure_construction_cost": 9356038.92,
                    "total_scrap_value": 2164095.02,
                }
        """
        carbon_emissions  = data.get("carbon_emission_data")
        carbon_cost_per_kg = carbon_emissions.get("social_cost_data").get("result").get("cost_of_carbon_local")  # INR/kgCO₂e

        total_kgCO2e = (
              float(carbon_emissions.get("material_emissions_data").get("total_kgCO2e"))    # Embodied carbon of materials used
            + float(carbon_emissions.get("transport_emissions_data").get("total_kgCO2e"))   # Emissions from transporting materials to site
            + float(carbon_emissions.get("machinery_emissions_data").get("total_kgCO2e"))   # Emissions from construction machinery (fuel/electricity)
        )
        return {
            "initial_construction_cost": float(data.get("construction_work_data").get("grand_total")),
            "initial_carbon_emissions_cost": total_kgCO2e * carbon_cost_per_kg,
            "superstructure_construction_cost": float(data.get("construction_work_data").get("Super Structure").get("total")),
            "total_scrap_value": float(data.get("recycling_data").get("total_recovered_value")),
        }

        
    def _prepare_wpi_object(self, data: dict):
        """
        This function creates a WPI object using the data from saved chunks.
        """
        from three_ps_lcca_core.inputs.wpi import WPIMetaData

        wpi_dict = data.get("traffic_and_road_data").get("wpi").get("data_snapshot").get("ratio")
        year = int(data.get("traffic_and_road_data").get("wpi").get("selected_profile_name"))
        
        return WPIMetaData.from_dict(
            {
                "year": year,
                "WPI": wpi_dict
            }
        )

    def _prepare_data_object(self, data: dict):
        """
        This function creates Core Data Object using the data from saved chunks.
        To be passed to 3psLCCA-core for calculation.
        """
        from three_ps_lcca_core.inputs.input import (
            InputMetaData,
            ProjectMetaData,
            GeneralParameters,
            TrafficAndRoadData,
            VehicleData,
            VehicleMetaData,
            AccidentSeverityDistribution,
            AdditionalInputs,
            MaintenanceAndStageParameters,
            UseStageCost,
            Routine,
            RoutineInspection,
            RoutineMaintenance,
            Major,
            MajorInspection,
            MajorRepair,
            ReplacementCost,
            EndOfLifeStageCosts,
            DemolitionDisposal,
        )
        from three_ps_lcca_core.inputs.input_global import (
            InputGlobalMetaData,
            DailyRoadUserCost,
            TotalCarbonEmission,
        )

        #--------------Prepare-General-Parameters-Start-------------------------------------------------
        _financial_data = data.get("financial_data")
        
        analysis_period_years             = int(_financial_data.get("analysis_period"))
        discount_rate_percent             = float(_financial_data.get("discount_rate"))
        inflation_rate_percent            = float(_financial_data.get("inflation_rate"))
        interest_rate_percent             = float(_financial_data.get("interest_rate"))
        investment_ratio                  = float(_financial_data.get("investment_ratio"))

        _niti = data.get("carbon_emission_data").get("social_cost_data").get("niti")
        social_cost_of_carbon_per_mtco2e  = float(_niti.get("cost_local"))
        currency_conversion               = float(_niti.get("inr_to_local_rate"))

        _bridge_data = data.get("bridge_data")
        service_life_years                = int(_bridge_data.get("design_life"))
        construction_period_months        = float(_bridge_data.get("duration_construction_months"))
        working_days_per_month            = float(_bridge_data.get("working_days_per_month"))
        days_per_month                    = float(_bridge_data.get("days_per_month"))

        use_global_road_user_calculations = data.get("traffic_and_road_data").get("mode") == "GLOBAL"

        general_parameters=GeneralParameters(
            service_life_years                = service_life_years,
            analysis_period_years             = analysis_period_years,
            discount_rate_percent             = discount_rate_percent,
            inflation_rate_percent            = inflation_rate_percent,
            interest_rate_percent             = interest_rate_percent,
            investment_ratio                  = investment_ratio,
            social_cost_of_carbon_per_mtco2e  = social_cost_of_carbon_per_mtco2e,
            currency_conversion               = currency_conversion,
            construction_period_months        = construction_period_months,
            working_days_per_month            = working_days_per_month,
            days_per_month                    = days_per_month,
            use_global_road_user_calculations = use_global_road_user_calculations,
        )
        #--------------Prepare-General-Parameters-End-------------------------------------------------

        #--------------Prepare-Maintenance-&-EOL-Start-------------------------------------------------
        _maintenance_data = data.get("maintenance_data")
        _demolition_data = data.get("demolition_data")

        routine_inspection_picc_per_year      = float(_maintenance_data.get("routine_inspection_cost"))
        routine_inspection_interval_in_years  = int(_maintenance_data.get("routine_inspection_freq"))

        routine_maintenance_picc_per_year     = float(_maintenance_data.get("periodic_maintenance_cost"))
        routine_maintenance_picec             = float(_maintenance_data.get("periodic_maintenance_carbon_cost"))
        routine_maintenance_interval_in_years = int(_maintenance_data.get("periodic_maintenance_freq"))
    
        major_inspection_picc                 = float(_maintenance_data.get("major_inspection_cost"))
        major_inspection_interval_in_years    = int(_maintenance_data.get("major_inspection_freq"))

        major_repair_picc                     = float(_maintenance_data.get("major_repair_cost"))
        major_repair_picec                    = float(_maintenance_data.get("major_repair_carbon_cost"))
        major_repair_interval_in_years        = int(_maintenance_data.get("major_repair_freq"))
        major_repair_duration_months          = int(_maintenance_data.get("major_repair_duration"))

        replace_bne_joint_pssc                = float(_maintenance_data.get("bearing_exp_joint_cost"))
        replace_bne_joint_interval_in_years   = int(_maintenance_data.get("bearing_exp_joint_freq"))
        replace_bne_joint_duration_in_days    = int(_maintenance_data.get("bearing_exp_joint_duration"))

        eol_picc                              = float(_demolition_data.get("demolition_cost_pct"))
        eol_picec                             = float(_demolition_data.get("demolition_carbon_cost_pct"))
        eol_dd_in_months                      = int(_demolition_data.get("demolition_duration"))

        maintenance_and_stage_parameters=MaintenanceAndStageParameters(
            use_stage_cost=UseStageCost(
                routine=Routine(
                    inspection=RoutineInspection(
                        percentage_of_initial_construction_cost_per_year = routine_inspection_picc_per_year,
                        interval_in_years                                = routine_inspection_interval_in_years,
                    ),
                    maintenance=RoutineMaintenance(
                        percentage_of_initial_construction_cost_per_year = routine_maintenance_picc_per_year,
                        percentage_of_initial_carbon_emission_cost       = routine_maintenance_picec,
                        interval_in_years                                = routine_maintenance_interval_in_years,
                    ),
                ),
                major=Major(
                    inspection=MajorInspection(
                        percentage_of_initial_construction_cost          = major_inspection_picc,
                        interval_for_repair_and_rehabitation_in_years    = major_inspection_interval_in_years,
                    ),
                    repair=MajorRepair(
                        percentage_of_initial_construction_cost          = major_repair_picc,
                        percentage_of_initial_carbon_emission_cost       = major_repair_picec,
                        interval_for_repair_and_rehabitation_in_years    = major_repair_interval_in_years,
                        repairs_duration_months                          = major_repair_duration_months,
                    ),
                ),
                replacement_costs_for_bearing_and_expansion_joint=ReplacementCost(
                    percentage_of_super_structure_cost = replace_bne_joint_pssc,
                    interval_of_replacement_in_years   = replace_bne_joint_interval_in_years,
                    duration_of_replacement_in_days    = replace_bne_joint_duration_in_days,
                ),
            ),
            end_of_life_stage_costs=EndOfLifeStageCosts(
                demolition_and_disposal=DemolitionDisposal(
                    percentage_of_initial_construction_cost        = eol_picc,
                    percentage_of_initial_carbon_emission_cost     = eol_picec,
                    duration_for_demolition_and_disposal_in_months = eol_dd_in_months,
                )
            ),
        )

        #--------------Prepare-Maintenance-&-EOL-End-------------------------------------------------

        # Object to return
        object = None

        if not use_global_road_user_calculations:
            #--------------Prepare-Project-Metadata-Start-------------------------------------------------
            description = data.get("general_info").get("project_description")
            standard    = "IRC 106:1990 / IRC SP 30-2019"
            country     = data.get("general_info").get("project_country")

            project_metadata = ProjectMetaData(
                description  = description,
                standard     = standard,
                country      = country,
            )
            #--------------Prepare-Project-Metadata-End-------------------------------------------------

            #------------------------------------Traffic-and-Road-Data-India-Start--------------------------------------------
            _traffic_road_data = data.get("traffic_and_road_data")
            _traffic_vehicle_data = _traffic_road_data.get("vehicle_data")
            _emission_factors = data.get("carbon_emission_data").get("diversion_emissions").get("emission_factors")

            small_cars    = VehicleMetaData(
                                int(_traffic_vehicle_data.get("small_cars").get("vehicles_per_day")), 
                                float(_emission_factors.get("small_cars")), 
                                float(_traffic_vehicle_data.get("small_cars").get("accident_percentage"))
                            )
            big_cars      = VehicleMetaData(
                                int(_traffic_vehicle_data.get("big_cars").get("vehicles_per_day")), 
                                float(_emission_factors.get("big_cars")), 
                                float(_traffic_vehicle_data.get("big_cars").get("accident_percentage"))
                            )
            two_wheelers  = VehicleMetaData(
                                int(_traffic_vehicle_data.get("two_wheelers").get("vehicles_per_day")), 
                                float(_emission_factors.get("two_wheelers")), 
                                float(_traffic_vehicle_data.get("two_wheelers").get("accident_percentage"))
                            )
            o_buses       = VehicleMetaData(
                                int(_traffic_vehicle_data.get("o_buses").get("vehicles_per_day")), 
                                float(_emission_factors.get("o_buses")), 
                                float(_traffic_vehicle_data.get("o_buses").get("accident_percentage"))
                            )
            d_buses       = VehicleMetaData(
                                int(_traffic_vehicle_data.get("d_buses").get("vehicles_per_day")), 
                                float(_emission_factors.get("d_buses")), 
                                float(_traffic_vehicle_data.get("d_buses").get("accident_percentage"))
                            )
            lcv           = VehicleMetaData(
                                int(_traffic_vehicle_data.get("lcv").get("vehicles_per_day")), 
                                float(_emission_factors.get("lcv")), 
                                float(_traffic_vehicle_data.get("lcv").get("accident_percentage"))
                            )
            hcv           = VehicleMetaData(
                                int(_traffic_vehicle_data.get("hcv").get("vehicles_per_day")), 
                                float(_emission_factors.get("hcv")), 
                                float(_traffic_vehicle_data.get("hcv").get("accident_percentage")),
                                pwr=float(_traffic_vehicle_data.get("hcv").get("pwr"))
                            )
            mcv           = VehicleMetaData(
                                int(_traffic_vehicle_data.get("mcv").get("vehicles_per_day")), 
                                float(_emission_factors.get("mcv")), 
                                float(_traffic_vehicle_data.get("mcv").get("accident_percentage")),
                                pwr=float(_traffic_vehicle_data.get("mcv").get("pwr"))
                            )

            minor = float(_traffic_road_data.get("severity_minor"))
            major = float(_traffic_road_data.get("severity_major"))
            fatal = float(_traffic_road_data.get("severity_fatal"))

            alternate_road_carriageway            = _traffic_road_data.get("alternate_road_carriageway")
            carriage_width_in_m                   = float(_traffic_road_data.get("carriage_width_in_m"))
            road_roughness_mm_per_km              = float(_traffic_road_data.get("road_roughness_mm_per_km"))
            road_rise_m_per_km                    = float(_traffic_road_data.get("road_rise_m_per_km"))
            road_fall_m_per_km                    = float(_traffic_road_data.get("road_fall_m_per_km"))
            additional_reroute_distance_km        = float(_traffic_road_data.get("additional_reroute_distance_km"))
            additional_travel_time_min            = float(_traffic_road_data.get("additional_travel_time_min"))
            crash_rate_accidents_per_million_km   = float(_traffic_road_data.get("crash_rate_accidents_per_million_km"))
            work_zone_multiplier                  = float(_traffic_road_data.get("work_zone_multiplier"))
            # Make the list of values for each hour of the day from the dict with hour keys
            peak_hour_traffic_percent_per_hour    = list(_traffic_road_data.get("peak_hour_distribution").values())
            hourly_capacity                       = int(_traffic_road_data.get("hourly_capacity"))
            force_free_flow_off_peak              = bool(_traffic_road_data.get("force_free_flow_off_peak"))
            
            traffic_and_road_data=TrafficAndRoadData(
                vehicle_data=VehicleData(
                    small_cars    = small_cars,
                    big_cars      = big_cars,
                    two_wheelers  = two_wheelers,
                    o_buses       = o_buses,
                    d_buses       = d_buses,
                    lcv           = lcv,
                    hcv           = hcv,
                    mcv           = mcv
                ),
                accident_severity_distribution=AccidentSeverityDistribution(
                    minor = minor,
                    major = major,
                    fatal = fatal,
                ),
                additional_inputs=AdditionalInputs(
                    alternate_road_carriageway          = alternate_road_carriageway,
                    carriage_width_in_m                 = carriage_width_in_m,
                    road_roughness_mm_per_km            = road_roughness_mm_per_km,
                    road_rise_m_per_km                  = road_rise_m_per_km,
                    road_fall_m_per_km                  = road_fall_m_per_km,
                    additional_reroute_distance_km      = additional_reroute_distance_km,
                    additional_travel_time_min          = additional_travel_time_min,
                    crash_rate_accidents_per_million_km = crash_rate_accidents_per_million_km,
                    work_zone_multiplier                = work_zone_multiplier,
                    peak_hour_traffic_percent_per_hour  = peak_hour_traffic_percent_per_hour,
                    hourly_capacity                     = hourly_capacity,
                    force_free_flow_off_peak            = force_free_flow_off_peak,
                ),
            )
            #------------------------------------Traffic-and-Road-Data-India-End--------------------------------------------
        
            object = InputMetaData(
                project_metadata                 = project_metadata,
                general_parameters               = general_parameters,
                traffic_and_road_data            = traffic_and_road_data,
                maintenance_and_stage_parameters = maintenance_and_stage_parameters,
            )
        else:
            #------------------------------------Traffic-and-Road-Data-Global-Start--------------------------------------------
            total_vehicular_carbon_emission = float(data.get("carbon_emission_data").get("transport_emissions_data").get("total_kgCO2e"))
            total_daily_ruc = float(data.get("traffic_and_road_data").get("road_user_cost_per_day"))
            
            daily_road_user_cost_with_vehicular_emissions=DailyRoadUserCost(
                total_daily_ruc=total_daily_ruc,
                total_carbon_emission=TotalCarbonEmission(
                    total_emission_kgCO2e=total_vehicular_carbon_emission
                ),
            )
            #------------------------------------Traffic-and-Road-Data-Global-End--------------------------------------------

            object = InputGlobalMetaData(
                general_parameters                            = general_parameters,
                daily_road_user_cost_with_vehicular_emissions = daily_road_user_cost_with_vehicular_emissions,
                maintenance_and_stage_parameters              = maintenance_and_stage_parameters,
            )
        
        return use_global_road_user_calculations, object
    #===================================================================================

    def _on_proceed(self):
        self.run_calculation()

    # ── Card widget ───────────────────────────────────────────────────────────

    def _create_card(self, page_name, issues, icon):
        card = QGroupBox()
        card.setStyleSheet(
            "QGroupBox { border: 1px solid #dee2e6; border-radius: 4px; }"
        )
        layout = QVBoxLayout(card)

        h_row = QWidget()
        h_lay = QHBoxLayout(h_row)
        h_lay.setContentsMargins(0, 0, 0, 0)
        h_lay.addWidget(QLabel(f"<b>{page_name}</b>"))
        h_lay.addStretch()

        go_btn = QPushButton("Go →")
        go_btn.setFixedWidth(60)
        go_btn.clicked.connect(
            lambda checked=False, p=page_name: self.navigate_requested.emit(p)
        )
        h_lay.addWidget(go_btn)

        layout.addWidget(h_row)
        for msg in issues:
            layout.addWidget(QLabel(f"{icon} {msg}"))
        return card

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_state(self, status: str, data: dict):
        if self.controller and self.controller.engine:
            self.controller.engine.stage_update(
                chunk_name=self.chunk_name, data={"status": status, "data": data}
            )

    def on_refresh(self):
        if not self.controller or not self.controller.engine:
            return
        state = self.controller.engine.fetch_chunk(CHUNK) or {}
        status = state.get("status", "idle")
        data = state.get("data", {})
        if status == "issues":
            self.show_results(data.get("errors", {}), data.get("warnings", {}))
        elif status == "success":
            self.show_success()
        else:
            self._show_idle()
