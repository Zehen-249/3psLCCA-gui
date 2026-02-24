# gui/main.py
import sys
import os
from PySide6.QtWidgets import QApplication, QSpinBox, QDoubleSpinBox
from PySide6.QtCore import QObject, QEvent
from gui.project_manager import ProjectManager


class DisableSpinBoxScroll(QObject):
    """
    Global event filter to disable mouse wheel changes
    on all QSpinBox and QDoubleSpinBox widgets.
    """
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            if isinstance(obj, (QSpinBox, QDoubleSpinBox)):
                return True  # Block wheel event completely
        return super().eventFilter(obj, event)


def main():
    """
    Main entry point for the OS Bridge LCCA application.
    Initializes the QApplication and delegates window management to ProjectManager.
    """

    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_SCALE_FACTOR"] = "1.1"  # try 1.1 – 1.3

    app = QApplication(sys.argv)

    # Install global wheel blocker
    wheel_filter = DisableSpinBoxScroll()
    app.installEventFilter(wheel_filter)

    # Optional: Set Application Name for OS-level identification
    app.setApplicationName("OS Bridge LCCA")
    app.setOrganizationName("OSBridge")

    # Optional: Load the QSS theme if available
    qss_path = os.path.join("gui", "assets", "themes", "lightstyle.qss")
    if os.path.exists(qss_path):
        try:
            with open(qss_path, "r") as f:
                app.setStyleSheet(f.read())
        except Exception as e:
            print(f"Warning: Could not load stylesheet: {e}")

    # Initialize the Manager
    manager = ProjectManager()
    manager.open_project()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()