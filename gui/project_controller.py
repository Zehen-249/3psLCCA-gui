from PySide6.QtCore import QObject, Signal, QTimer
from core.safechunk_engine import SafeChunkEngine


class ProjectController(QObject):
    """
    Central mediator between the SafeChunkEngine and the UI.
    """

    status_message = Signal(str)
    sync_completed = Signal()
    fault_occurred = Signal(str)
    dirty_changed = Signal(bool)
    project_loaded = Signal()

    def __init__(self):
        super().__init__()
        self.engine = None
        self.active_project_id = None
        self.active_display_name = None
        self.recovery_needed = False
        self.recovery_health = None
        

    def get_chunk(self, chunk_name: str) -> dict:
        """Helper for widgets to retrieve their specific data."""
        if self.engine and self.engine.is_active():
            # Use fetch_chunk or read_chunk depending on your Engine implementation
            return self.engine.read_chunk(chunk_name)
        return {}

    def init_project(
        self, project_id: str, is_new: bool = False, display_name: str = None
    ) -> bool:
        if self.engine:
            self.close_project()

        if is_new:
            self.engine, status = SafeChunkEngine.new(
                project_id, display_name=display_name
            )
        else:
            self.engine, status = SafeChunkEngine.open(project_id)

        if self.engine and self.engine.is_active():
            self.active_project_id = project_id
            self.active_display_name = self.engine.display_name
            self.recovery_needed = self.engine._recovery_needed
            self.recovery_health = self.engine._recovery_health

            self.engine.on_sync = lambda: self.sync_completed.emit()
            self.engine.on_status = lambda msg: self.status_message.emit(msg)
            self.engine.on_fault = lambda msg: self.fault_occurred.emit(msg)
            self.engine.on_dirty = lambda dirty: self.dirty_changed.emit(dirty)

            if is_new:
                self.engine.create_checkpoint(
                    label="initial", notes="Auto-checkpoint on creation."
                )

            QTimer.singleShot(0, self.project_loaded.emit)
            return True

        return False

    def save_chunk_data(self, chunk_name: str, data: dict):
        """Passes data to the engine's staging area (debounced write)."""
        if self.engine and self.engine.is_active():
            self.engine.stage_update(data, chunk_name)

    def load_checkpoint(self, zip_name: str) -> bool:
        """Restores the project from a checkpoint ZIP."""
        if self.engine and self.engine.is_active():
            # SAFETY: Ensure we don't have pending writes before restoring
            self.engine.force_sync()

            success = self.engine.restore_checkpoint(zip_name)
            if success:
                # Tell widgets to discard their current memory state and reload
                self.sync_completed.emit()
                self.project_loaded.emit()
            return success
        return False

    def close_project(self):
        """Force-syncs and detaches the engine cleanly."""
        if self.engine:
            try:
                self.engine.force_sync()
                self.engine.detach()
            except Exception as e:
                self.fault_occurred.emit(f"Error during close: {e}")
            finally:
                self.engine = None
                self.active_project_id = None
                self.active_display_name = None
                self.dirty_changed.emit(False)
                self.recovery_needed = False
                self.recovery_health = None

    # --- Pass-through Checkpoint API ---
    def save_checkpoint(self, label: str = "manual", notes: str = "") -> str | None:
        if self.engine and self.engine.is_active():
            return self.engine.create_checkpoint(label=label, notes=notes)
        return None

    def list_checkpoints(self) -> list:
        return self.engine.list_checkpoints() if self.engine else []

    def delete_checkpoint(self, zip_name: str) -> bool:
        return self.engine.delete_checkpoint(zip_name) if self.engine else False

    def is_dirty(self) -> bool:
        return self.engine.is_dirty() if self.engine else False

    def get_engine_logs(self) -> list:
        """Returns the engine's rolling log history for display in the Logs panel."""
        if self.engine:
            return list(self.engine.log_history)
        return []

    def get_health_report(self) -> dict:
        """Returns engine diagnostics for technical support/debugging."""
        if self.engine:
            return self.engine.get_health_report()
        return {}


# Single instance
controller = ProjectController()
