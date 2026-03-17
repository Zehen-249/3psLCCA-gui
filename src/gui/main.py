import sys
import os
from PySide6.QtWidgets import QApplication, QSpinBox, QDoubleSpinBox, QComboBox
from PySide6.QtCore import QObject, QEvent
from PySide6.QtGui import QPalette, QColor
from gui.project_manager import ProjectManager


# ── Accent ────────────────────────────────────────────────────────────────────
_ACCENT         = QColor("#2ecc71")
_ACCENT_TEXT    = QColor("#0f1f14")   # dark text on green — green is a light colour
_ACCENT_VISITED = QColor("#1e8449")
_ACCENT_DIM     = QColor("#4a7a58")   # desaturated, for disabled state


def _apply_accent(app: QApplication) -> None:
    """
    Take the current OS palette exactly as-is and only override the
    interaction roles with the green accent. Nothing else is touched —
    surfaces, text, borders all stay native.
    """
    p = app.palette()

    for group in (QPalette.Active, QPalette.Inactive):
        p.setColor(group, QPalette.Highlight,       _ACCENT)
        p.setColor(group, QPalette.HighlightedText, _ACCENT_TEXT)

    p.setColor(QPalette.Disabled, QPalette.Highlight,       _ACCENT_DIM)
    p.setColor(QPalette.Disabled, QPalette.HighlightedText, p.color(QPalette.Disabled, QPalette.Text))

    p.setColor(QPalette.Link,        _ACCENT)
    p.setColor(QPalette.LinkVisited, _ACCENT_VISITED)

    app.setPalette(p)


# ── Wheel blocker ─────────────────────────────────────────────────────────────
class DisableSpinBoxScroll(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            if isinstance(obj, (QSpinBox, QDoubleSpinBox, QComboBox)):
                if obj.parent():
                    QApplication.instance().sendEvent(obj.parent(), event)
                return True
        return super().eventFilter(obj, event)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_SCALE_FACTOR"] = "1.1"

    app = QApplication(sys.argv)

    # Load user-defined custom units from DB into the global cache
    try:
        from gui.components.utils.unit_resolver import load_custom_units
        load_custom_units()
    except Exception as _e:
        print(f"Warning: Could not load custom units: {_e}")

    wheel_filter = DisableSpinBoxScroll()
    app.installEventFilter(wheel_filter)

    app.setApplicationName("OS Bridge LCCA")
    app.setOrganizationName("OSBridge")

    qss_path = os.path.join("gui", "assets", "themes", "lightstyle.qss")
    if os.path.exists(qss_path):
        try:
            with open(qss_path, "r") as f:
                app.setStyleSheet(f.read())
        except Exception as e:
            print(f"Warning: Could not load stylesheet: {e}")

    # Stamp accent onto whatever palette the OS is currently using
    _apply_accent(app)

    # Re-apply when OS switches dark ↔ light (Qt 6.5+)
    try:
        app.styleHints().colorSchemeChanged.connect(lambda _: _apply_accent(app))
    except AttributeError:
        pass

    manager = ProjectManager()
    manager.open_project()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()