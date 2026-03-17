"""
gui/components/checkpoint_dialog.py

Two dialogs for the checkpoint system:

  SaveCheckpointDialog  — prompts for a label + notes, then calls controller.save_checkpoint()
  CheckpointManagerDialog — lists all checkpoints with date/label/notes, allows restore or delete
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView, QSizePolicy, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor


# ---------------------------------------------------------------------------
# Save Checkpoint Dialog
# ---------------------------------------------------------------------------

class SaveCheckpointDialog(QDialog):
    """
    Modal dialog that lets the user name and annotate a checkpoint before saving.
    """

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Save Checkpoint")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel("💾  Save Checkpoint")
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)

        desc = QLabel(
            "A checkpoint is a full snapshot of your current project data.\n"
            "You can restore it at any time from the Checkpoint Manager."
        )
        desc.setWordWrap(True)
        # desc.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(desc)

        # Form
        form = QFormLayout()
        form.setSpacing(8)

        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("e.g. before client review, v2 cost update")
        self.label_edit.setMaxLength(30)
        form.addRow("Label:", self.label_edit)

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Optional notes about this snapshot...")
        self.notes_edit.setFixedHeight(80)
        form.addRow("Notes:", self.notes_edit)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Checkpoint")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save)
        # self.save_btn.setStyleSheet(
        #     "QPushButton { background-color: #4a7c10; color: white; border: none; "
        #     "border-radius: 5px; padding: 6px 16px; font-weight: bold; }"
        #     "QPushButton:hover { background-color: #5a9214; }"
        # )
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def _on_save(self):
        label = self.label_edit.text().strip() or "manual"
        notes = self.notes_edit.toPlainText().strip()

        self.save_btn.setEnabled(False)
        self.save_btn.setText("Saving...")

        zip_name = self.controller.save_checkpoint(label=label, notes=notes)

        if zip_name:
            QMessageBox.information(
                self, "Checkpoint Saved",
                f"Checkpoint '{label}' saved successfully.\n\nFile: {zip_name}"
            )
            self.accept()
        else:
            QMessageBox.critical(
                self, "Save Failed",
                "Failed to create checkpoint. Check the engine logs for details."
            )
            self.save_btn.setEnabled(True)
            self.save_btn.setText("Save Checkpoint")


# ---------------------------------------------------------------------------
# Checkpoint Manager Dialog
# ---------------------------------------------------------------------------

class CheckpointManagerDialog(QDialog):
    """
    Full checkpoint browser: lists all snapshots with metadata,
    and provides Restore + Delete actions.
    """

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Checkpoint Manager")
        self.setMinimumSize(700, 420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel("🕓  Checkpoint Manager")
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)

        desc = QLabel(
            "Select a checkpoint to restore or delete it. "
            "Restoring will replace all current project data with the snapshot."
        )
        desc.setWordWrap(True)
        # desc.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(desc)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Label", "Date & Time", "Notes", "File"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

        # Action buttons
        btn_row = QHBoxLayout()

        self.new_btn = QPushButton("+ New Checkpoint")
        self.new_btn.clicked.connect(self._on_new_checkpoint)
        btn_row.addWidget(self.new_btn)

        btn_row.addStretch()

        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete)
        self.delete_btn.setStyleSheet(
            "QPushButton:enabled { color: #c0392b; border-color: #c0392b; }"
            "QPushButton:enabled:hover { background-color: #c0392b; color: white; }"
        )
        btn_row.addWidget(self.delete_btn)

        self.restore_btn = QPushButton("↩  Restore")
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self._on_restore)
        # self.restore_btn.setStyleSheet(
        #     "QPushButton:enabled { background-color: #4a7c10; color: white; border: none; "
        #     "border-radius: 5px; padding: 6px 16px; font-weight: bold; }"
        #     "QPushButton:enabled:hover { background-color: #5a9214; }"
        # )
        btn_row.addWidget(self.restore_btn)

        layout.addLayout(btn_row)

        self._populate_table()

    def _populate_table(self):
        """Loads checkpoints from the controller and fills the table."""
        checkpoints = self.controller.list_checkpoints()

        self.table.setRowCount(len(checkpoints))
        self._checkpoints = checkpoints  # store for action reference

        for row, cp in enumerate(checkpoints):
            # Format date nicely
            raw_date = cp.get("date", "")
            try:
                from datetime import datetime
                dt = datetime.strptime(raw_date, "%Y%m%d_%H%M%S")
                formatted_date = dt.strftime("%Y-%m-%d  %H:%M:%S")
            except Exception:
                formatted_date = raw_date

            label_item = QTableWidgetItem(cp.get("label", ""))
            label_item.setFont(QFont("", -1, QFont.Bold))

            self.table.setItem(row, 0, label_item)
            self.table.setItem(row, 1, QTableWidgetItem(formatted_date))
            self.table.setItem(row, 2, QTableWidgetItem(cp.get("notes", "")))
            self.table.setItem(row, 3, QTableWidgetItem(cp.get("filename", "")))

        if not checkpoints:
            self.table.setRowCount(1)
            empty_item = QTableWidgetItem("No checkpoints found. Create one using '+ New Checkpoint'.")
            empty_item.setForeground(QColor("#999"))
            self.table.setItem(0, 0, empty_item)
            self.table.setSpan(0, 0, 1, 4)

    def _on_selection_changed(self):
        has_selection = bool(self.table.selectedItems()) and bool(self._checkpoints)
        self.restore_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    def _selected_checkpoint(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._checkpoints):
            return self._checkpoints[row]
        return None

    def _on_new_checkpoint(self):
        dlg = SaveCheckpointDialog(self.controller, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._populate_table()

    def _on_restore(self):
        cp = self._selected_checkpoint()
        if not cp:
            return

        result = QMessageBox.warning(
            self,
            "Confirm Restore",
            f"Restore checkpoint '{cp['label']}' from {cp['date']}?\n\n"
            "⚠️  This will REPLACE all current project data with this snapshot.\n"
            "Any unsaved changes will be lost.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel
        )

        if result == QMessageBox.Ok:
            success = self.controller.load_checkpoint(cp["filename"])
            if success:
                QMessageBox.information(
                    self, "Restore Complete",
                    f"Project restored from '{cp['label']}' successfully.\n"
                    "The UI will now refresh."
                )
                self.accept()
            else:
                QMessageBox.critical(
                    self, "Restore Failed",
                    "Failed to restore the checkpoint. Check the engine logs for details."
                )

    def _on_delete(self):
        cp = self._selected_checkpoint()
        if not cp:
            return

        result = QMessageBox.warning(
            self,
            "Confirm Delete",
            f"Permanently delete checkpoint '{cp['label']}'?\n\nThis cannot be undone.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel
        )

        if result == QMessageBox.Ok:
            success = self.controller.delete_checkpoint(cp["filename"])
            if success:
                self._populate_table()
            else:
                QMessageBox.critical(self, "Delete Failed", "Could not delete the checkpoint file.")
