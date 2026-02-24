"""
gui/components/home_page.py

Home screen for the LCCA application.
"""

import os
from PySide6.QtCore import Qt, QSize, QPoint, QRect
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QSizePolicy,
    QMessageBox,
    QAbstractItemView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
)
from core.safechunk_engine import SafeChunkEngine


# ── Status config ─────────────────────────────────────────────────────────────

STATUS_CONFIG = {
    "ok": {"label": "OK", "color": "#22c55e"},
    "crashed": {"label": "Crashed", "color": "#ef4444"},
    "locked": {"label": "Open", "color": "#3b82f6"},
    "corrupted": {"label": "Corrupted", "color": "#f97316"},
}


# ── Custom delegate ───────────────────────────────────────────────────────────


class ProjectCardDelegate(QStyledItemDelegate):
    """
    Renders each project as a card:
      - Display name (bold)
      - Modified / Created dates (muted)
      - Status badge (coloured pill, top-right)
    """

    CARD_HEIGHT = 72
    PADDING_H = 14
    PADDING_V = 10
    BADGE_PADDING = 6
    BADGE_H = 18
    RADIUS = 6

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.CARD_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        data = index.data(Qt.UserRole)
        rect = option.rect.adjusted(6, 3, -6, -3)

        # ── Background ────────────────────────────────────────────────────────
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = bool(option.state & QStyle.State_MouseOver)

        palette = option.palette
        if is_selected:
            bg = palette.highlight().color()
        elif is_hovered:
            bg = palette.midlight().color()
        else:
            bg = palette.base().color()

        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        # ── Status badge ──────────────────────────────────────────────────────
        status = data.get("status", "ok") if data else "ok"
        cfg = STATUS_CONFIG.get(status, STATUS_CONFIG["ok"])
        badge_text = cfg["label"]
        badge_col = QColor(cfg["color"])

        badge_font = QFont()
        badge_font.setPointSize(7)
        badge_font.setBold(True)
        painter.setFont(badge_font)

        fm = painter.fontMetrics()
        badge_w = fm.horizontalAdvance(badge_text) + self.BADGE_PADDING * 2
        badge_rect = QRect(
            rect.right() - badge_w - self.PADDING_H,
            rect.top() + self.PADDING_V,
            badge_w,
            self.BADGE_H,
        )

        pill_bg = QColor(badge_col)
        pill_bg.setAlpha(30)
        painter.setBrush(QBrush(pill_bg))
        painter.setPen(QPen(badge_col, 1))
        painter.drawRoundedRect(badge_rect, self.BADGE_H / 2, self.BADGE_H / 2)
        painter.setPen(badge_col)
        painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

        # ── Text colours ──────────────────────────────────────────────────────
        text_col = (
            palette.highlightedText().color() if is_selected else palette.text().color()
        )
        muted_col = (
            palette.highlightedText().color()
            if is_selected
            else palette.placeholderText().color()
        )

        text_x = rect.left() + self.PADDING_H
        text_maxw = badge_rect.left() - text_x - 8

        # Display name
        name_font = QFont()
        name_font.setPointSize(10)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(text_col)

        name = (data.get("display_name") or "Unnamed") if data else "Unnamed"
        name_fm = painter.fontMetrics()
        name_text = name_fm.elidedText(name, Qt.ElideRight, text_maxw)
        name_y = rect.top() + self.PADDING_V + name_fm.ascent()
        painter.drawText(QPoint(text_x, name_y), name_text)

        # Sub-labels
        sub_font = QFont()
        sub_font.setPointSize(8)
        painter.setFont(sub_font)
        painter.setPen(muted_col)

        sub_fm = painter.fontMetrics()
        sub_y = name_y + name_fm.descent() + 3 + sub_fm.ascent()

        parts = []
        if data:
            if data.get("last_modified"):
                parts.append(f"Modified {data['last_modified']}")
            if data.get("created_at"):
                parts.append(f"Created {data['created_at']}")

        if parts:
            painter.drawText(QPoint(text_x, sub_y), "   ·   ".join(parts))

        painter.restore()


# ── List item ─────────────────────────────────────────────────────────────────


class ProjectListItem(QListWidgetItem):
    def __init__(self, project_info: dict):
        super().__init__()
        self.project_id = project_info["project_id"]
        self.display_name = project_info.get("display_name", self.project_id)
        self.setData(Qt.UserRole, project_info)
        self.setSizeHint(QSize(0, ProjectCardDelegate.CARD_HEIGHT))


# ── Home page ─────────────────────────────────────────────────────────────────


class HomePage(QWidget):

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._active_project_id = None
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_header())

        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.addStretch(1)
        body_row.addWidget(self._make_body(), stretch=0)
        body_row.addStretch(1)

        body_wrapper = QWidget()
        body_wrapper.setLayout(body_row)
        body_wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(body_wrapper, stretch=1)

        root.addWidget(self._make_footer())

    def _make_header(self) -> QWidget:
        bar = QFrame()
        bar.setFrameShape(QFrame.StyledPanel)
        bar.setFixedHeight(64)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(28, 0, 28, 0)

        title = QLabel("OS Bridge  LCCA")
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)
        layout.addStretch()

        subtitle = QLabel("Life Cycle Cost Analysis")
        sub_f = QFont()
        sub_f.setPointSize(10)
        subtitle.setFont(sub_f)
        subtitle.setEnabled(False)
        layout.addWidget(subtitle)

        return bar

    def _make_body(self) -> QWidget:
        card = QWidget()
        card.setFixedWidth(500)
        card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 40, 0, 40)
        layout.setSpacing(0)

        # New project
        layout.addWidget(self._section_label("Start"))
        layout.addSpacing(8)

        self.btn_new = QPushButton("＋  New Project")
        self.btn_new.setFixedHeight(40)
        self.btn_new.setDefault(True)
        self.btn_new.clicked.connect(lambda: self.manager.open_project(is_new=True))
        layout.addWidget(self.btn_new)

        layout.addSpacing(32)
        layout.addWidget(self._divider())
        layout.addSpacing(24)

        # Project list header
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._section_label("Projects"))
        row.addStretch()
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(28, 28)
        refresh_btn.setToolTip("Refresh list")
        refresh_btn.clicked.connect(self.refresh_project_list)
        row.addWidget(refresh_btn)
        layout.addLayout(row)
        layout.addSpacing(8)

        # Project list with card delegate
        self.project_list = QListWidget()
        self.project_list.setMinimumHeight(240)
        self.project_list.setItemDelegate(ProjectCardDelegate())
        self.project_list.setMouseTracking(True)
        self.project_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.project_list.itemDoubleClicked.connect(self._open_selected)
        layout.addWidget(self.project_list)

        layout.addSpacing(10)

        # Open / Delete buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_open = QPushButton("Open")
        self.btn_open.setFixedHeight(34)
        self.btn_open.clicked.connect(self._open_selected)
        btn_row.addWidget(self.btn_open)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setFixedHeight(34)
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.btn_delete)

        layout.addLayout(btn_row)

        layout.addSpacing(32)
        layout.addWidget(self._divider())
        layout.addSpacing(24)

        # Return to active project
        self.btn_return = QPushButton("← Return to Active Project")
        self.btn_return.setFixedHeight(36)
        self.btn_return.hide()
        self.btn_return.clicked.connect(
            lambda: self.manager.open_project(project_id=self._active_project_id)
        )
        layout.addWidget(self.btn_return)

        return card

    def _make_footer(self) -> QWidget:
        bar = QFrame()
        bar.setFrameShape(QFrame.StyledPanel)
        bar.setFixedHeight(32)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        lbl = QLabel("OS Bridge LCCA  •  v1.5.0")
        lbl.setEnabled(False)
        f = QFont()
        f.setPointSize(9)
        lbl.setFont(f)
        layout.addWidget(lbl)
        layout.addStretch()

        return bar

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text.upper())
        f = QFont()
        f.setPointSize(8)
        f.setBold(True)
        lbl.setFont(f)
        lbl.setEnabled(False)
        return lbl

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    # ── Public API ────────────────────────────────────────────────────────────

    def set_active_project(self, project_id: str | None):
        self._active_project_id = project_id
        if project_id:
            display = project_id
            for win in self.manager.windows:
                if win.project_id == project_id:
                    display = win.controller.active_display_name or project_id
                    break
            self.btn_return.show()
            self.btn_return.setText(f"← Return to  {display}")
        else:
            self.btn_return.hide()

    def refresh_project_list(self):
        self.project_list.clear()
        projects = sorted(
            SafeChunkEngine.list_all_projects(),
            key=lambda p: p.get("last_modified") or "",
            reverse=True,
        )

        # Build a map of open projects: id -> window
        open_windows = {
            win.project_id: win
            for win in self.manager.windows
            if win.project_id is not None
        }

        if not projects:
            placeholder = QListWidgetItem("No projects found.")
            placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsSelectable)
            placeholder.setForeground(QColor("#888888"))
            self.project_list.addItem(placeholder)
        else:
            for p in projects:
                pid = p["project_id"]
                if pid in open_windows:
                    p["status"] = "locked"
                    # Use in-memory display name — more up to date than disk
                    mem_name = open_windows[pid].controller.active_display_name
                    if mem_name:
                        p["display_name"] = mem_name
                elif p["status"] == "locked":
                    p["status"] = "ok"  # stale lock, project not open here

                self.project_list.addItem(ProjectListItem(p))

    # ── Internal slots ────────────────────────────────────────────────────────

    def _selected_pid(self) -> str | None:
        item = self.project_list.currentItem()
        if isinstance(item, ProjectListItem):
            return item.project_id
        return None

    def _open_selected(self):
        pid = self._selected_pid()
        if pid:
            self.manager.open_project(project_id=pid)

    def _delete_selected(self):
        pid = self._selected_pid()
        if not pid:
            QMessageBox.information(self, "Delete", "Select a project first.")
            return

        if self.manager.is_project_open(pid):
            QMessageBox.warning(
                self,
                "Cannot Delete",
                "This project is currently open in a window.\n\n"
                "Close it first, then delete it.",
            )
            return

        item = self.project_list.currentItem()
        display = item.display_name if isinstance(item, ProjectListItem) else pid

        result = QMessageBox.warning(
            self,
            "Delete Project",
            f"Permanently delete '{display}'?\n\nThis cannot be undone.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if result == QMessageBox.Ok:
            engine, _ = SafeChunkEngine.open(pid)
            if engine:
                engine.delete_project(confirmed=True)
            self.manager.refresh_all_home_screens()
