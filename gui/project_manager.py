# gui/project_manager.py
import os
from PySide6.QtWidgets import QApplication
from gui.project_controller import ProjectController


class ProjectManager:
    def __init__(self):
        self.windows = []
        print("[DEBUG] ProjectManager: Initialized")

    # ── WINDOW HELPERS ────────────────────────────────────────────────────────

    def _create_window(self):
        """Creates a new window with its own isolated controller."""
        from gui.project_window import ProjectWindow

        new_controller = ProjectController()
        print(f"[DEBUG] Manager: Created NEW Controller ID: {id(new_controller)}")
        win = ProjectWindow(manager=self, controller=new_controller)
        self.windows.append(win)
        return win

    def _find_empty_window(self):
        """Returns the first window that has no project loaded, or None."""
        for win in self.windows:
            if not win.has_project_loaded():
                return win
        return None

    def _find_window_for_project(self, project_id: str):
        """Returns the window currently showing this project, or None."""
        for win in self.windows:
            if win.project_id == project_id:
                return win
        return None

    # ── PUBLIC API ────────────────────────────────────────────────────────────

    def open_project(self, project_id=None, is_new=False):
        print(f"[DEBUG] Manager: open_project(id={project_id}, new={is_new})")

        if not project_id and not is_new:
            target = self._find_empty_window() or self._create_window()
            target.show_home()
            target.show()
            target.activateWindow()
            return

        if project_id:
            existing = self._find_window_for_project(project_id)
            if existing:
                existing.show_project_view()
                existing.raise_()
                existing.activateWindow()
                return

        # Ask for display name if new
        display_name = None
        if is_new:
            from gui.components.new_project_dialog import NewProjectDialog

            dialog = NewProjectDialog()
            if dialog.exec() != NewProjectDialog.Accepted:
                return
            display_name = dialog.get_name()

        target = self._find_empty_window()
        if target is None:
            target = self._create_window()
            target.show()

        success = False
        if is_new:
            new_id = f"proj_{os.urandom(4).hex()}"
            success = target.controller.init_project(
                new_id, is_new=True, display_name=display_name
            )
        elif project_id:
            success = target.controller.init_project(project_id, is_new=False)

        if success:
            target.project_id = target.controller.active_project_id

            # ── Show recovery dialog if needed ────────────────────────────────
            if target.controller.recovery_needed and not is_new:
                from gui.components.recovery_dialog import RecoveryDialog

                dlg = RecoveryDialog(
                    engine=target.controller.engine,
                    health=target.controller.recovery_health,
                    parent=target,
                )
                dlg.exec()

                if dlg.was_cancelled():
                    # User cancelled — close the window, don't open project
                    target.controller.close_project()
                    target.project_id = None
                    target.show_home()
                    target.show()
                    target.activateWindow()
                    self.refresh_all_home_screens()
                    return

            print(f"[DEBUG] Manager: Success — {target.project_id}")
            target.show_project_view()
            self.refresh_all_home_screens()
        else:
            print(f"[DEBUG] Manager: Init failed for {project_id}")
            target.show_home()

        target.show()
        target.activateWindow()

    def is_project_open(self, project_id: str) -> bool:
        """Returns True if any window currently has this project loaded."""
        return self._find_window_for_project(project_id) is not None

    def remove_window(self, win):
        """Called when a window is closed."""
        if win in self.windows:
            self.windows.remove(win)
            print(f"[DEBUG] Manager: Window closed. Remaining: {len(self.windows)}")
        if not self.windows:
            QApplication.quit()

    def refresh_all_home_screens(self):
        """Tell every open window's home widget to reload the project list."""
        for win in self.windows:
            win.home_widget.refresh_project_list()
