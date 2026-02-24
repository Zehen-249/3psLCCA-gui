import json
import os
import copy
import threading
import time
import shutil
import zipfile
import psutil
import re
import functools
from pathlib import Path


def requires_active(func):
    """
    Decorator to ensure engine methods only run if the engine is properly
    attached and hasn't been deleted or detached.
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self._engine_active:
            self._log(
                f"Execution Blocked: '{func.__name__}' called on inactive engine."
            )
            return None
        return func(self, *args, **kwargs)

    return wrapper


class SafeChunkEngine:
    VERSION = "1.5.0"

    def __init__(
        self,
        project_id: str,
        debounce_delay: float = 1.0,
        force_save_delay: float = 2.0,
        base_dir: str = "user_projects",
    ):
        """
        Main Engine Constructor.

        Args:
            project_id:       Unique string ID for the project folder.
            debounce_delay:   Seconds of idle time before a lightweight commit fires.
                              Resets on every keystroke. Keeps disk writes low during
                              active typing.
            force_save_delay: Seconds after the FIRST keystroke in a burst before a
                              guaranteed fsync commit is forced, regardless of whether
                              the user is still typing. Protects against power loss
                              during continuous input. Default 2 seconds.
            base_dir:         The root folder where all user projects are stored.
        """
        # Configuration
        self.project_id = project_id
        self.debounce_delay = debounce_delay
        self.force_save_delay = force_save_delay
        self.base_dir_path = Path(base_dir).resolve()

        # Path Architecture
        self.project_path = self.base_dir_path / self.project_id
        self.chunks_path = self.project_path / "chunks"
        self.backup_path = self.project_path / "chunks_bak"
        self.checkpoint_path = self.project_path / "checkpoints"
        self.lock_file = self.project_path / ".lock"
        self.version_file = self.project_path / "version.json"

        # Threading and Memory Synchronization
        self._write_lock = threading.Lock()
        self._debounce_timer = None  # Resets on every keystroke; fires after idle
        self._force_save_timer = (
            None  # Set ONCE per typing burst; fires force_save_delay
        )
        # after the FIRST keystroke — power-loss guard
        self._staged_data = {}  # High-speed write-ahead buffer (RAM)
        self._dirty_chunks = set()  # Tracks which chunks have unsaved changes
        self.log_history = []

        # Communication Hooks (Callbacks)
        self.on_status = None  # For UI status bar updates
        self.on_sync = None  # Triggered after disk write is verified
        self.on_fault = None  # Triggered on critical IO errors
        self.on_dirty = None  # Triggered when unsaved changes exist (for UI indicator)

        # Engine Lifecycle State
        self._engine_active = False

        # 1. Prepare Folders -> 2. Claim Lock
        self._initialize_env()
        self.attach()

    # --------------------------------------------------------------------------
    # FACTORY & ROOT MANAGEMENT
    # --------------------------------------------------------------------------

    @staticmethod
    def list_all_projects(base_dir: str = "user_projects") -> list:
        root = Path(base_dir)
        if not root.exists():
            return []

        valid_projects = []
        for item in root.iterdir():
            if item.is_dir():
                has_chunks = (item / "chunks").exists()
                has_backup = (item / "chunks_bak").exists()
                if has_chunks or has_backup:  # accept either
                    valid_projects.append(item.name)
        return valid_projects

    @classmethod
    def new(cls, project_id: str = None, base_dir: str = "user_projects", **kwargs):
        """
        Creates a brand new project. Handles ID collisions by auto-incrementing.
        """
        root = Path(base_dir)
        root.mkdir(parents=True, exist_ok=True)

        base_name = project_id or "new_project"
        target_id = base_name
        counter = 1

        while (root / target_id).exists():
            target_id = f"{base_name}_{counter}"
            counter += 1

        try:
            instance = cls(target_id, base_dir=str(root), **kwargs)
            return instance, "SUCCESS"
        except Exception as e:
            return None, f"FAILED_TO_CREATE: {str(e)}"

    # In core/safechunk_engine.py
    # Replace the open() classmethod with this version.
    # It cleans stale lock files before attempting to attach,
    # so crashed sessions don't permanently block reopening a project.

    @classmethod
    def open(cls, project_id: str, base_dir: str = "user_projects", **kwargs):
        """
        Opens an existing project.
        Automatically removes stale lock files left by crashed processes.
        Returns (None, reason) if the project is actively locked by another live process.
        """
        import psutil

        root = Path(base_dir)
        if not (root / project_id).exists():
            return None, "PROJECT_NOT_FOUND"

        # Pre-check: clean stale lock before attempting attach
        lock_file = root / project_id / ".lock"
        if lock_file.exists():
            try:
                lock_data = lock_file.read_text()
                existing_pid = int(lock_data.split(":")[1].strip())
                if not psutil.pid_exists(existing_pid):
                    lock_file.unlink()  # stale — remove it so attach() succeeds
            except Exception:
                try:
                    lock_file.unlink()  # unreadable lock — remove it
                except Exception:
                    pass

        try:
            instance = cls(project_id, base_dir=str(root), **kwargs)
            if not instance.is_active():
                return None, "PROJECT_ALREADY_OPEN_IN_ANOTHER_PROCESS"
            return instance, "SUCCESS"
        except Exception as e:
            return None, f"OPEN_ERROR: {str(e)}"

    # --------------------------------------------------------------------------
    # LIFECYCLE MANAGEMENT
    # --------------------------------------------------------------------------

    def attach(self):
        """Claims the project directory by creating a PID-based lock file."""
        if self.lock_file.exists():
            try:
                lock_data = self.lock_file.read_text()
                existing_pid = int(lock_data.split(":")[1].strip())

                if not psutil.pid_exists(existing_pid):
                    self._log(
                        f"Removing stale lock file from crashed PID {existing_pid}"
                    )
                    self.lock_file.unlink()
                else:
                    self._engine_active = False
                    self._log(
                        "ATTACH_DENIED: Project is currently open in another window."
                    )
                    return
            except Exception as e:
                self._log(f"Lock Validation Error: {e}")

        try:
            self.lock_file.write_text(f"PID: {os.getpid()}")
            self.version_file.write_text(
                json.dumps(
                    {
                        "engine_version": self.VERSION,
                        "attached_at": time.time(),
                        "project_id": self.project_id,
                    },
                    indent=4,
                )
            )

            self._engine_active = True
            self._log(f"Engine attached to {self.project_id} successfully.")
        except Exception as e:
            self._engine_active = False
            self._handle_error(f"Critical Lock Failure: {e}")

    def detach(self):
        """Gracefully shuts down the engine, ensuring all data is flushed."""
        if not self._engine_active:
            return

        self._log("Detaching engine. Performing final sync...")
        self.force_sync()

        with self._write_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            if self._force_save_timer:
                self._force_save_timer.cancel()
                self._force_save_timer = None

        if self.lock_file.exists():
            self.lock_file.unlink()

        self._engine_active = False
        self._log("Engine detached. Lock released.")

    def is_active(self) -> bool:
        """Returns True if the engine is healthy and holds the lock."""
        return self._engine_active

    def is_dirty(self) -> bool:
        """Returns True if there are unsaved (staged but not yet committed) changes."""
        with self._write_lock:
            return bool(self._staged_data)

    # --------------------------------------------------------------------------
    # CORE DATA OPERATIONS
    # --------------------------------------------------------------------------

    @requires_active
    def stage_update(self, data: dict, chunk_name: str):
        """
        Updates memory buffer and manages two independent timers:

          debounce_timer   — resets on EVERY call. Fires _commit_to_disk() after
                             debounce_delay seconds of inactivity. Keeps disk writes
                             low during rapid typing.

          force_save_timer — started ONCE when a burst begins (not reset on each call).
                             Fires force_sync() after force_save_delay seconds regardless
                             of whether the user is still typing.
                             POWER-LOSS GUARD: at most force_save_delay seconds of work
                             can be lost even during continuous non-stop input.
        """
        with self._write_lock:
            # 1. Update the in-memory shard
            self._staged_data[chunk_name] = copy.deepcopy(data)
            self._dirty_chunks.add(chunk_name)

            # 2. Emergency backup (lightweight, no fsync — best-effort crash protection)
            self._write_emergency_backup(chunk_name, data)

            # 3. Debounce timer — reset on every keystroke
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(
                self.debounce_delay, self._commit_to_disk
            )
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

            # 4. Force-save timer — only start if not already running for this burst.
            #    This guarantees a full fsync commit within force_save_delay seconds
            #    even if the user never stops typing.
            if self._force_save_timer is None:
                self._force_save_timer = threading.Timer(
                    self.force_save_delay, self._force_save_from_timer
                )
                self._force_save_timer.daemon = True
                self._force_save_timer.start()

        # Notify UI of pending unsaved changes
        if self.on_dirty:
            self.on_dirty(True)
        if self.on_status:
            self.on_status("Unsaved changes...")

    def _write_emergency_backup(self, chunk_name: str, data: dict):
        """
        Writes staged data to a SEPARATE .ebak (emergency backup) file without fsync.
        Called inside stage_update (already under write_lock).

        BUG FIX: Previously wrote to .bak, overwriting the authoritative committed-state
        backup produced by _commit_to_disk. After one keystroke the .bak would contain
        un-fsync'd staged data instead of the last known-good committed state.

        Now uses .ebak as a separate file. fetch_chunk() falls back to .ebak only if
        BOTH the primary .json AND the authoritative .bak are unreadable — worst-case
        scenario where even the committed backup is gone.
        """
        try:
            ebak_file = self.backup_path / f"{chunk_name}.ebak"
            with open(ebak_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            self._log(f"Emergency backup write failed for '{chunk_name}': {e}")

    @requires_active
    def fetch_chunk(self, chunk_name: str) -> dict:
        """
        High-integrity data retrieval.
        Hierarchy: RAM -> Primary Disk -> Backup Disk.
        """
        # Step 1: Check Memory Buffer (most recent, uncommitted data)
        with self._write_lock:
            if chunk_name in self._staged_data:
                return copy.deepcopy(self._staged_data[chunk_name])

        # Step 2: Try Primary JSON
        primary_file = self.chunks_path / f"{chunk_name}.json"
        backup_file = self.backup_path / f"{chunk_name}.bak"

        if primary_file.exists():
            try:
                with open(primary_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                self._log(f"Primary shard '{chunk_name}' corrupt. Trying backup...")

        # Step 3: Try authoritative .bak (last committed state)
        if backup_file.exists():
            try:
                with open(backup_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._log(
                        f"Recovered '{chunk_name}' from .bak. Restoring primary..."
                    )
                    self.stage_update(data, chunk_name)
                    return data
            except Exception:
                self._log(
                    f"Authoritative .bak for '{chunk_name}' also corrupt. Trying emergency backup..."
                )

        # Step 4: Try .ebak (emergency backup — staged data, no fsync guarantee)
        #         Last resort: may be slightly ahead of .bak but not fsync'd.
        ebak_file = self.backup_path / f"{chunk_name}.ebak"
        if ebak_file.exists():
            try:
                with open(ebak_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._log(
                        f"Recovered '{chunk_name}' from emergency .ebak. Data may be incomplete."
                    )
                    self.stage_update(data, chunk_name)
                    return data
            except Exception as e:
                self._handle_error(f"Total data loss for shard '{chunk_name}': {e}")

        return {}

    read_chunk = fetch_chunk

    def delete_project(self, confirmed: bool = False):
        """
        Removes the entire project folder and all its contents.
        Requires explicit confirmation to prevent accidental deletion.
        """
        if not confirmed:
            self._log("Delete project rejected: Missing confirmation.")
            return False

        try:
            self.detach()
            if self.project_path.exists():
                shutil.rmtree(self.project_path)
            self._log(f"Project '{self.project_id}' was successfully wiped.")
            return True
        except Exception as e:
            self._handle_error(f"Failed to delete project: {e}")
            return False

    @requires_active
    def force_sync(self):
        """Immediately writes all memory-staged data to disk, bypassing the debounce."""
        with self._write_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            if self._force_save_timer:
                self._force_save_timer.cancel()
                self._force_save_timer = None
        self._commit_to_disk()

    def _force_save_from_timer(self):
        """
        Called by the force_save_timer after force_save_delay seconds from the
        first keystroke in a burst. Performs a full fsync commit and resets the
        force_save_timer so the next burst can start a fresh one.

        This runs on a daemon thread — it must be safe to call concurrently
        with stage_update() calls on the main thread.
        """
        with self._write_lock:
            self._force_save_timer = None  # Reset so next burst starts a fresh timer
        self._commit_to_disk()
        self._log(
            f"Force-save committed (power-loss guard fired after {self.force_save_delay}s)"
        )

    # --------------------------------------------------------------------------
    # ATOMIC PERSISTENCE MECHANISM
    # --------------------------------------------------------------------------

    def _commit_to_disk(self):
        """
        The Atomic Write-Ahead-Log (WAL) Logic.
        Flow: Write Temp -> Backup Current -> Replace Current with Temp.

        FIX: Now correctly generates a .bak from the PREVIOUS committed state
        (not from staged data), giving a true rollback point. Also notifies
        the UI via on_sync and clears the dirty flag.
        """
        with self._write_lock:
            if not self._staged_data or not self._engine_active:
                return

            failed_chunks = []

            for chunk_name in list(self._staged_data.keys()):
                data = self._staged_data[chunk_name]

                p_file = self.chunks_path / f"{chunk_name}.json"
                b_file = self.backup_path / f"{chunk_name}.bak"
                t_file = self.chunks_path / f"{chunk_name}.tmp"

                try:
                    # 1. Write to temp file first (safest)
                    with open(t_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                        f.flush()
                        os.fsync(f.fileno())  # Force OS flush to physical hardware

                    # 2. Backup the EXISTING primary (last known-good committed state).
                    #    This is the authoritative .bak — never overwritten by emergency backup.
                    if p_file.exists():
                        shutil.copy2(p_file, b_file)

                    # 3. Atomic swap: temp becomes the new primary
                    t_file.replace(p_file)

                    # 4. Remove from staging — this chunk is safe on disk
                    del self._staged_data[chunk_name]
                    self._dirty_chunks.discard(chunk_name)

                except Exception as e:
                    # BUG FIX: Per-chunk error handling. One bad chunk does NOT prevent
                    # the remaining chunks from being written. Failed chunks stay in
                    # _staged_data so they will be retried on the next commit cycle.
                    failed_chunks.append(chunk_name)
                    self._log(f"Sync failed for chunk '{chunk_name}': {e}")
                    # Clean up any partial .tmp file
                    try:
                        if t_file.exists():
                            t_file.unlink()
                    except Exception:
                        pass

            self._debounce_timer = None

            if failed_chunks:
                # Some chunks failed — notify fault but don't mark as clean
                self._handle_error(
                    f"Sync failed for chunks: {failed_chunks}. Will retry."
                )
            else:
                # All chunks committed — notify UI: all clean
                if self.on_dirty:
                    self.on_dirty(False)
                if self.on_sync:
                    self.on_sync()

    # --------------------------------------------------------------------------
    # SNAPSHOTS & RECOVERY
    # --------------------------------------------------------------------------

    @requires_active
    def create_checkpoint(
        self, label: str = "manual", notes: str = "", retention: int = 10
    ) -> str | None:
        """
        Creates a time-stamped ZIP snapshot of the entire project state.
        Always force-syncs first so the checkpoint captures the latest data.

        Returns the zip filename on success, None on failure.
        """
        self.force_sync()

        clean_label = re.sub(r"[^\w\-_]", "_", label)[:30]
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        zip_name = f"cp_{clean_label}_{timestamp}.zip"
        zip_full_path = self.checkpoint_path / zip_name

        try:
            with zipfile.ZipFile(zip_full_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in self.chunks_path.glob("*.json"):
                    zf.write(f, arcname=f"chunks/{f.name}")

                meta = {
                    "timestamp": timestamp,
                    "label": label,
                    "notes": notes,
                    "engine_ver": self.VERSION,
                    "project_id": self.project_id,
                }
                zf.writestr("checkpoint_meta.json", json.dumps(meta, indent=4))

            # Retention policy: remove oldest if over limit
            history = sorted(self.checkpoint_path.glob("*.zip"), key=os.path.getmtime)
            while len(history) > retention:
                oldest = history.pop(0)
                oldest.unlink()
                self._log(f"Retention policy: removed old checkpoint {oldest.name}")

            self._log(f"Checkpoint created: {zip_name}")
            if self.on_status:
                self.on_status(f"Checkpoint saved: {label}")
            return zip_name

        except Exception as e:
            self._handle_error(f"Checkpoint failed: {e}")
            return None

    @requires_active
    def restore_checkpoint(self, zip_name: str) -> bool:
        """
        Full system restoration from a checkpoint ZIP file.
        Clears all staged/pending data before restoring.

        BUG FIX: Previously wiped chunks/ and chunks_bak/ then extracted the ZIP all
        inside a single try block with no rollback. If extraction failed halfway, the
        project would be left with empty folders and no data at all.

        Now uses a safe staging approach:
          1. Extract ZIP to a temp staging folder first
          2. Only if extraction succeeds, swap the staging folder into place
          3. If anything fails, the original files are untouched
        """
        zip_full_path = self.checkpoint_path / zip_name
        if not zip_full_path.exists():
            self._log(f"Restore failed: {zip_name} not found.")
            return False

        staging_path = self.project_path / "_restore_staging"

        try:
            # Cancel all pending writes first
            with self._write_lock:
                if self._debounce_timer:
                    self._debounce_timer.cancel()
                    self._debounce_timer = None
                if self._force_save_timer:
                    self._force_save_timer.cancel()
                    self._force_save_timer = None
                self._staged_data.clear()
                self._dirty_chunks.clear()

            # Step 1: Extract to a safe staging folder (original files untouched)
            if staging_path.exists():
                shutil.rmtree(staging_path)
            staging_path.mkdir()

            with zipfile.ZipFile(zip_full_path, "r") as zf:
                zf.extractall(path=staging_path)

            # Step 2: Validate the staging folder has the expected chunks folder
            staging_chunks = staging_path / "chunks"
            if not staging_chunks.exists():
                raise ValueError("Checkpoint ZIP is missing the chunks/ folder.")

            # Step 3: Swap — only now do we touch the live data
            with self._write_lock:
                # Wipe current active data
                for folder in [self.chunks_path, self.backup_path]:
                    for f in folder.glob("*"):
                        try:
                            f.unlink()
                        except Exception:
                            pass

                # Move staged files into place
                for f in staging_chunks.glob("*"):
                    shutil.copy2(f, self.chunks_path / f.name)

            # Step 4: Clean up staging folder
            shutil.rmtree(staging_path, ignore_errors=True)

            if self.on_dirty:
                self.on_dirty(False)
            if self.on_sync:
                self.on_sync()

            self._log(f"Project successfully restored from: {zip_name}")
            if self.on_status:
                self.on_status(f"Restored from checkpoint: {zip_name}")
            return True

        except Exception as e:
            # Clean up staging folder if it exists
            shutil.rmtree(staging_path, ignore_errors=True)
            self._handle_error(f"Restore failed: {e}")
            return False

    def list_checkpoints(self) -> list:
        """Returns metadata for all available snapshots, sorted newest first."""
        cp_list = []
        for zp in self.checkpoint_path.glob("*.zip"):
            try:
                with zipfile.ZipFile(zp, "r") as zf:
                    meta = json.loads(zf.read("checkpoint_meta.json"))
                    cp_list.append(
                        {
                            "filename": zp.name,
                            "label": meta.get("label", ""),
                            "date": meta.get("timestamp", ""),
                            "notes": meta.get("notes", ""),
                            "engine_ver": meta.get("engine_ver", ""),
                        }
                    )
            except Exception:
                continue
        return sorted(cp_list, key=lambda x: x["date"], reverse=True)

    def delete_checkpoint(self, zip_name: str) -> bool:
        """Deletes a specific checkpoint file."""
        zip_full_path = self.checkpoint_path / zip_name
        if zip_full_path.exists():
            try:
                zip_full_path.unlink()
                self._log(f"Checkpoint deleted: {zip_name}")
                return True
            except Exception as e:
                self._handle_error(f"Failed to delete checkpoint: {e}")
        return False

    # --------------------------------------------------------------------------
    # DIAGNOSTICS
    # --------------------------------------------------------------------------

    def get_health_report(self) -> dict:
        """Returns a diagnostic summary of the current engine state."""
        return {
            "active": self._engine_active,
            "project": self.project_id,
            "root_path": str(self.base_dir_path),
            "shards_count": len(list(self.chunks_path.glob("*.json"))),
            "backups_count": len(list(self.backup_path.glob("*.bak"))),
            "checkpoints_count": len(list(self.checkpoint_path.glob("*.zip"))),
            "pending_syncs": len(self._staged_data),
            "dirty_chunks": list(self._dirty_chunks),
        }

    # --------------------------------------------------------------------------
    # INTERNAL HELPERS
    # --------------------------------------------------------------------------

    def _initialize_env(self):
        """Creates directory structure, cleans up crash artifacts, and recovers from missing chunks/."""
        for path in [self.chunks_path, self.backup_path, self.checkpoint_path]:
            path.mkdir(parents=True, exist_ok=True)

        # Recovery: if chunks/ is empty but chunks_bak/ has .bak files, restore them
        existing_chunks = list(self.chunks_path.glob("*.json"))
        backup_files = list(self.backup_path.glob("*.bak"))

        if not existing_chunks and backup_files:
            recovered = []
            for bak_file in backup_files:
                try:
                    chunk_name = bak_file.stem
                    target = self.chunks_path / f"{chunk_name}.json"
                    shutil.copy2(bak_file, target)
                    recovered.append(chunk_name)
                except Exception as e:
                    self._log(f"Recovery failed for '{bak_file.name}': {e}")

            if recovered:
                self._log(
                    f"RECOVERY: chunks/ was missing. Restored {len(recovered)} chunk(s) "
                    f"from backup: {recovered}. Project data has been recovered."
                )
                # Fire on_status if available, else it will print via _log
                if self.on_status:
                    self.on_status(
                        f"⚠️ Project recovered from backup ({len(recovered)} chunks restored)"
                    )

        # Clean up orphaned .tmp files from previous crashes
        for tmp_file in self.chunks_path.glob("*.tmp"):
            try:
                tmp_file.unlink()
                self._log(f"Cleaned up orphaned temp file: {tmp_file.name}")
            except Exception:
                pass

    def _log(self, message: str):
        timestamped_msg = f"[{time.strftime('%H:%M:%S')}] {message}"
        self.log_history.append(timestamped_msg)
        if len(self.log_history) > 100:  # Increased from 50 for better diagnostics
            self.log_history.pop(0)

        if self.on_status:
            self.on_status(message)
        else:
            print(timestamped_msg)

    def _handle_error(self, error_message: str):
        """Logs a critical fault and fires the on_fault callback for UI notification."""
        self._log(f"CRITICAL FAULT: {error_message}")
        if self.on_fault:
            self.on_fault(str(error_message))
