# gui/components/new_project_dialog.py
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt


class NewProjectDialog(QDialog):
    """Simple dialog to collect a display name before creating a project."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setFixedWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        layout.addWidget(QLabel("<b>Project Name</b>"))

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Highway 5 Bridge Replacement")
        self.name_input.setFixedHeight(34)
        layout.addWidget(self.name_input)

        hint = QLabel("You can rename this later.")
        hint.setEnabled(False)
        layout.addWidget(hint)

        layout.addSpacing(8)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self.name_input.returnPressed.connect(self._on_accept)

    def _on_accept(self):
        if self.name_input.text().strip():
            self.accept()

    def get_name(self) -> str:
        return self.name_input.text().strip()