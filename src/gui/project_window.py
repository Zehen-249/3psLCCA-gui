import os

from PySide6.QtCore import Qt, QRect, QSize, QEvent, QPoint
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSplitterHandle,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QAction, QColor, QPainter, QPalette
from PySide6.QtWidgets import QToolTip

from gui.components.save_status_bar import SaveStatusBar
from gui.components.logs import Logs
from gui.components.global_info.main import GeneralInfo
from gui.components.bridge_data.main import BridgeData
from gui.components.structure.main import StructureTabView
from gui.components.traffic_data.main import TrafficData
from gui.components.financial_data.main import FinancialData
from gui.components.carbon_emission.main import CarbonEmissionTabView
from gui.components.maintenance.main import Maintenance
from gui.components.recycling.main import Recycling
from gui.components.demolition.main import Demolition
from gui.components.home_page import HomePage
from gui.components.outputs.outputs_page import OutputsPage
from gui.components.utils.validation_helpers import set_lock_tooltip_target


# ── Sidebar tree definition ───────────────────────────────────────────────────

SIDEBAR_TREE = {
    "General Information": {},
    "Bridge Data": {},
    "Input Parameters": {
        "Construction Work Data": [
            "Foundation",
            "Sub Structure",
            "Super Structure",
            "Miscellaneous",
        ],
        "Traffic Data": [],
        "Financial Data": [],
        "Carbon Emission Data": [
            "Material Emissions",
            "Transportation Emissions",
            "Machinery Emissions",
            "Traffic Diversion Emissions",
            "Social Cost of Carbon",
        ],
        "Maintenance and Repair": [],
        "Recycling": [],
        "Demolition": [],
    },
    "Outputs": {},
}


# ── Sidebar tree ──────────────────────────────────────────────────────────────

_ACCENT = QColor("#2ecc71")
_HOVER_ALPHA = 30
_V_PAD = 3  # vertical padding per side (increases row height)
_H_PAD = 6  # left text indent (pushes text away from accent bar)
_ACCENT_W = 3  # width of the green left bar in px
_SEL_ALPHA = 55  # not padding but affects how "heavy" selection feels


class _SidebarDelegate(QStyledItemDelegate):
    """Owns text-column painting: padding, text color. Background is handled
    by _SidebarTree.drawRow so we only need to paint text here."""

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        return QSize(base.width(), base.height() + _V_PAD * 2)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # Strip ALL native state so Qt draws zero background/highlight
        option.state &= ~(
            QStyle.State_Selected | QStyle.State_MouseOver | QStyle.State_HasFocus
        )
        # Text only
        text = index.data(Qt.DisplayRole)
        if not text:
            return
        painter.save()
        is_sel = bool(option.state & QStyle.State_Selected)
        text_rect = option.rect.adjusted(
            _H_PAD + (_ACCENT_W if is_sel else 0), _V_PAD, -4, -_V_PAD
        )
        painter.setPen(option.palette.windowText().color())
        painter.setFont(option.font)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.restore()


class _SidebarTree(QTreeWidget):
    """
    QTreeWidget subclass that overrides drawRow() and drawBranches() —
    the only two methods that own the full row width including the
    indentation/branch zone. The delegate only handles text after we've
    painted the correct background across the entire row.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setItemDelegate(_SidebarDelegate(self))

        # Sync Base/AlternateBase → Window so the viewport background matches
        p = self.palette()
        p.setColor(QPalette.Base, p.color(QPalette.Window))
        p.setColor(QPalette.AlternateBase, p.color(QPalette.Window))
        # Keep Highlight neutral — we paint selection ourselves
        p.setColor(QPalette.Highlight, p.color(QPalette.Window))
        p.setColor(QPalette.HighlightedText, p.color(QPalette.WindowText))
        self.setPalette(p)

    def _row_state(self, index):
        """Return (is_selected, is_hovered) for a model index."""
        item = self.itemFromIndex(index)
        is_sel = item in self.selectedItems()
        is_hovered = index == self.indexAt(
            self.viewport().mapFromGlobal(self.cursor().pos())
        )
        return is_sel, is_hovered

    def drawRow(self, painter: QPainter, option, index):
        """Paint the full-width row background before the delegate runs."""
        is_sel, is_hovered = self._row_state(index)
        full = option.rect  # spans full widget width

        painter.save()
        painter.setPen(Qt.NoPen)

        # Base fill — always paint Window color first to erase everything
        painter.setBrush(self.palette().window())
        painter.drawRect(full)

        if is_hovered and not is_sel:
            tint = QColor(_ACCENT)
            tint.setAlpha(_HOVER_ALPHA)
            painter.setBrush(tint)
            painter.drawRect(full)

        if is_sel:
            fill = QColor(_ACCENT)
            fill.setAlpha(_SEL_ALPHA)
            painter.setBrush(fill)
            painter.drawRect(full)
            # Left accent bar — flush to viewport left edge
            painter.setBrush(_ACCENT)
            painter.drawRect(full.left(), full.top(), _ACCENT_W, full.height())

        painter.restore()

        # Now let Qt draw the branch arrows + delegate text on top
        super().drawRow(painter, option, index)

    def drawBranches(self, painter: QPainter, rect: QRect, index):
        """Fill the branch/indentation zone with the same background as drawRow
        so there is never a differently-colored strip on the left."""
        is_sel, is_hovered = self._row_state(index)

        painter.save()
        painter.setPen(Qt.NoPen)

        painter.setBrush(self.palette().window())
        painter.drawRect(rect)

        if is_hovered and not is_sel:
            tint = QColor(_ACCENT)
            tint.setAlpha(_HOVER_ALPHA)
            painter.setBrush(tint)
            painter.drawRect(rect)

        if is_sel:
            fill = QColor(_ACCENT)
            fill.setAlpha(_SEL_ALPHA)
            painter.setBrush(fill)
            painter.drawRect(rect)

        painter.restore()

        # Let Qt draw the expand/collapse arrows on top
        super().drawBranches(painter, rect, index)


# ── Hover-highlight splitter ──────────────────────────────────────────────────


class _HoverHandle(QSplitterHandle):
    """
    Splitter handle that draws a 2px green accent line on hover/drag —
    identical visual language to VS Code's panel resize handles.
    No QSS used; painting is done entirely via QPainter + QPalette.
    """

    _ACCENT = QColor("#2ecc71")

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self._hovered = False

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        # Always let Qt draw the base handle first
        super().paintEvent(event)
        if not self._hovered:
            return
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._ACCENT)
        r = self.rect()
        if self.orientation() == Qt.Horizontal:
            x = (r.width() - 3) // 2
            painter.drawRect(x, 0, 3, r.height())
        else:
            y = (r.height() - 3) // 2
            painter.drawRect(0, y, r.width(), 3)
        painter.end()


class _HoverSplitter(QSplitter):
    """QSplitter that uses _HoverHandle for all its handles."""

    def createHandle(self):
        return _HoverHandle(self.orientation(), self)


# ── Main window ───────────────────────────────────────────────────────────────


class ProjectWindow(QMainWindow):
    def __init__(self, manager, controller=None):
        super().__init__()
        self.manager = manager

        if controller is not None:
            self.controller = controller
        else:
            from gui.project_controller import ProjectController

            self.controller = ProjectController()

        self.project_id = None

        self.setWindowTitle("LCCA - Home")
        self.resize(1100, 750)

        self.main_stack = QStackedWidget()
        self.setCentralWidget(self.main_stack)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._setup_home_ui()  # index 0
        self._setup_project_ui()  # index 1

        # ── Controller signals ────────────────────────────────────────────
        self.controller.fault_occurred.connect(self._on_fault)
        self.controller.project_loaded.connect(self._on_project_loaded)
        self.controller.sync_completed.connect(
            lambda: self.status_bar.showMessage("All changes saved.", 3000)
        )
        self.controller.dirty_changed.connect(
            lambda d: self.status_bar.showMessage("Unsaved changes...") if d else None
        )

        self.show_home()

    # ── Home screen ───────────────────────────────────────────────────────────

    def _setup_home_ui(self):
        self.home_widget = HomePage(manager=self.manager)
        self.main_stack.addWidget(self.home_widget)  # index 0

    # ── Project view ──────────────────────────────────────────────────────────

    def _setup_project_ui(self):
        self.project_widget = QWidget()
        master_layout = QVBoxLayout(self.project_widget)
        master_layout.setContentsMargins(0, 0, 0, 0)
        master_layout.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(8, 4, 8, 4)
        top_bar_layout.setSpacing(8)

        self.menubar = QMenuBar()

        self.menuFile = QMenu("&File", self.menubar)
        for label in ["New", "Open"]:
            self.menuFile.addAction(QAction(label, self))
        self.menuFile.addSeparator()
        self.actionSave = QAction("Save", self)
        self.menuFile.addAction(self.actionSave)
        for label in ["Save As...", "Create a Copy", "Print"]:
            self.menuFile.addAction(QAction(label, self))
        self.menuFile.addSeparator()
        for label in ["Rename", "Export", "Version History", "Info"]:
            self.menuFile.addAction(QAction(label, self))

        self.menuHelp = QMenu("&Help", self.menubar)
        for label in ["Contact us", "Feedback"]:
            self.menuHelp.addAction(QAction(label, self))
        self.menuHelp.addSeparator()
        for label in ["Video Tutorials", "Join our Community"]:
            self.menuHelp.addAction(QAction(label, self))

        home_action = QAction("Home", self)
        home_action.triggered.connect(self.show_home)

        self.log_action = QAction("Logs", self)

        self.menubar.addAction(home_action)
        self.menubar.addMenu(self.menuFile)
        self.menubar.addMenu(self.menuHelp)
        self.menubar.addAction(QAction("Tutorials", self))
        self.menubar.addAction(self.log_action)

        top_bar_layout.addWidget(self.menubar)
        top_bar_layout.addStretch()
        self.save_status_bar = SaveStatusBar(controller=self.controller)
        top_bar_layout.addWidget(self.save_status_bar)

        self.btn_calculate = QPushButton("Calculate")
        self.btn_calculate.clicked.connect(self._run_calculate)
        top_bar_layout.addWidget(self.btn_calculate)

        self._frozen = False
        self._lock_tooltip = "Lock project to prevent editing"
        self.btn_lock = QPushButton("Lock")
        self.btn_lock.setCheckable(True)
        self.btn_lock.installEventFilter(self)
        self.btn_lock.clicked.connect(self._on_lock_toggled)
        top_bar_layout.addWidget(self.btn_lock)

        master_layout.setMenuBar(top_bar)

        # ── Sidebar ───────────────────────────────────────────────────────
        self.sidebar = _SidebarTree()
        self.sidebar.setMinimumWidth(80)

        for header, subheaders in SIDEBAR_TREE.items():
            top_item = QTreeWidgetItem(self.sidebar)
            top_item.setText(0, header)
            for subheader, subitems in subheaders.items():
                sub_item = QTreeWidgetItem(top_item)
                sub_item.setText(0, subheader)
                for subitem in subitems:
                    leaf = QTreeWidgetItem(sub_item)
                    leaf.setText(0, subitem)

        self.sidebar.expandAll()
        self.sidebar.itemPressed.connect(self._select_sidebar)

        # ── Content stack ─────────────────────────────────────────────────
        self.content_stack = QStackedWidget()

        self.metadata_page = QLabel()
        self.metadata_page.setAlignment(Qt.AlignCenter)

        self.logs_page = Logs(controller=self.controller)

        self.outputs_page = OutputsPage(controller=self.controller)
        self.outputs_page.navigate_requested.connect(self._navigate_to_page)
        self.outputs_page.calculation_completed.connect(self._on_calculation_done)

        self.widget_map = {
            "General Information": GeneralInfo(controller=self.controller),
            "Bridge Data": BridgeData(controller=self.controller),
            "Construction Work Data": StructureTabView(controller=self.controller),
            "Traffic Data": TrafficData(controller=self.controller),
            "Financial Data": FinancialData(controller=self.controller),
            "Carbon Emission Data": CarbonEmissionTabView(controller=self.controller),
            "Maintenance and Repair": Maintenance(controller=self.controller),
            "Recycling": Recycling(controller=self.controller),
            "Demolition": Demolition(controller=self.controller),
            "Outputs": self.outputs_page,
        }

        self.outputs_page.register_pages(self.widget_map)

        for widget in self.widget_map.values():
            self.content_stack.addWidget(widget)
        self.content_stack.addWidget(self.logs_page)

        self.log_action.triggered.connect(
            lambda: self.content_stack.setCurrentWidget(self.logs_page)
        )

        # ── Splitter ──────────────────────────────────────────────────────
        self.splitter = _HoverSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.sidebar)
        self.splitter.setHandleWidth(8)
        self.splitter.addWidget(self.content_stack)
        self.splitter.setSizes([220, 880])

        master_layout.addWidget(self.splitter, stretch=1)
        self.main_stack.addWidget(self.project_widget)  # index 1

    def _select_sidebar(self, item: QTreeWidgetItem):
        header = item.text(0)
        parent = item.parent()
        item.setExpanded(True)

        if header in self.widget_map:
            self.content_stack.setCurrentWidget(self.widget_map[header])
            return

        if parent is None:
            return

        parent_header = parent.text(0)

        if parent_header == "Construction Work Data":
            self.content_stack.setCurrentWidget(
                self.widget_map["Construction Work Data"]
            )
            self.widget_map["Construction Work Data"].select_tab(header)

        elif parent_header == "Carbon Emission Data":
            self.content_stack.setCurrentWidget(self.widget_map["Carbon Emission Data"])
            self.widget_map["Carbon Emission Data"].select_tab(header)

    # ── View switching ────────────────────────────────────────────────────────

    def show_home(self):
        self.setWindowTitle("LCCA - Home")
        self.home_widget.set_active_project(
            self.project_id if self.has_project_loaded() else None
        )
        self.home_widget.refresh_project_list()
        self.main_stack.setCurrentWidget(self.home_widget)
        self.manager.refresh_all_home_screens()

    def show_project_view(self):
        if not self.has_project_loaded():
            return
        display = self.controller.active_display_name or self.project_id
        self.setWindowTitle(f"LCCA - {display}")
        self.main_stack.setCurrentWidget(self.project_widget)
        self.content_stack.setCurrentWidget(self.widget_map["General Information"])
        items = self.sidebar.findItems("General Information", Qt.MatchExactly)
        if items:
            self.sidebar.setCurrentItem(items[0])

    def has_project_loaded(self):
        return self.project_id is not None

    # ── Calculate ─────────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self.btn_lock:
            if event.type() == QEvent.Type.Enter:
                pos = self.btn_lock.mapToGlobal(
                    QPoint(self.btn_lock.width() // 2, self.btn_lock.height() + 4)
                )
                QToolTip.showText(pos, self._lock_tooltip, None, QRect(), 3000)
            elif event.type() == QEvent.Type.Leave:
                QToolTip.hideText()
        return super().eventFilter(obj, event)

    def _on_calculation_done(self):
        """Auto-lock the project after a successful calculation."""
        self.btn_lock.setChecked(True)
        self._on_lock_toggled(True)

    def _on_lock_toggled(self, checked: bool):
        if not checked and self.outputs_page._has_results:
            reply = QMessageBox.warning(
                self,
                "Unlock Project",
                "Unlocking will clear the current calculation results.\n\n"
                "All inputs will become editable again and the output will be reset.\n\n"
                "Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self.btn_lock.blockSignals(True)
                self.btn_lock.setChecked(True)
                self.btn_lock.blockSignals(False)
                return
            self.outputs_page.reset_for_edit()

        self._frozen = checked
        self.btn_lock.setText("Unlock" if checked else "Lock")
        self._lock_tooltip = (
            "Project is locked — click here to unlock"
            if checked else
            "Lock project to prevent editing"
        )
        set_lock_tooltip_target(self.btn_lock if checked else None)
        for page in self.widget_map.values():
            if hasattr(page, "freeze"):
                page.freeze(checked)

    def _run_calculate(self):
        self.outputs_page.run_validation()
        self.content_stack.setCurrentWidget(self.outputs_page)
        items = self.sidebar.findItems("Outputs", Qt.MatchExactly)
        if items:
            self.sidebar.setCurrentItem(items[0])

    def _navigate_to_page(self, page_name: str):
        """Navigate sidebar + content stack to a named page."""
        widget = self.widget_map.get(page_name)
        if widget:
            self.content_stack.setCurrentWidget(widget)
        items = self.sidebar.findItems(page_name, Qt.MatchExactly | Qt.MatchRecursive)
        if items:
            self.sidebar.setCurrentItem(items[0])

    # ── Controller signals ────────────────────────────────────────────────────

    def _on_project_loaded(self):
        if not self.controller.active_project_id:
            return
        self.project_id = self.controller.active_project_id
        display = self.controller.active_display_name or self.project_id
        self.setWindowTitle(f"LCCA - {display}")
        self.status_bar.showMessage(f"Project: {display}")
        self.show_project_view()

    def _on_fault(self, error_message: str):
        QMessageBox.critical(
            self,
            "Engine Error — Data may not be saved",
            f"A critical storage error occurred:\n\n{error_message}\n\n"
            "Save a checkpoint immediately if possible, then restart.",
        )

    # ── Close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self.controller.engine:
            self.controller.close_project()
        self.project_id = None
        self.manager.remove_window(self)
        self.manager.refresh_all_home_screens()
        event.accept()
