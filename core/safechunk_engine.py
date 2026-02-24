import json
import hashlib
import hmac
import os
import copy
import threading
import time
import shutil
import zipfile
import psutil
import re
import secrets
import functools
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Tuple


def requires_active(func):
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
    """
    SafeChunk Engine v2.1 - Content-Addressed Storage (CAS)

    Phase 1 safety additions:
    - WAL (Write-Ahead Log): every staged write is logged before commit
    - Manifest ring buffer: last 3 manifests kept as fallback
    - Manifest HMAC: detects external tampering of manifest
    """

    VERSION = "2.1.0"
    MANIFEST_RING_SIZE = 3

    def __init__(
        self,
        project_id: str,
        display_name: str = None,
        app_version: str = "1.0.0",
        debounce_delay: float = 1.0,
        force_save_delay: float = 2.0,
        base_dir: str = "user_projects",
    ):
        self.project_id = project_id
        self.display_name = display_name or project_id
        self.app_version = app_version
        self.debounce_delay = debounce_delay
        self.force_save_delay = force_save_delay
        self.base_dir_path = Path(base_dir).resolve()

        # Path Architecture
        self.project_path = self.base_dir_path / self.project_id
        self.object_store = self.project_path / "objects"
        self.manifest_path = self.project_path / "manifest.json"
        self.forensics_path = self.project_path / "forensics"
        self.checkpoint_path = self.project_path / "checkpoints"
        self.backup_path = self.project_path / "backups"
        self.lock_file = self.project_path / ".lock"
        self.version_file = self.project_path / "version.json"
        self.key_file = self.project_path / "project.key"
        self.sig_file = self.project_path / "manifest.sig"
        self.wal_file = self.project_path / "wal.log"

        # Threading
        self._write_lock = threading.Lock()
        self._debounce_timer = None
        self._force_save_timer = None
        self._staged_data = {}
        self.log_history = []

        # Session tracking
        self._session_dirty = False  # tracks if anything was written this session

        # Callbacks
        self.on_status: Optional[Callable[[str], None]] = None
        self.on_sync: Optional[Callable[[], None]] = None
        self.on_fault: Optional[Callable[[str], None]] = None
        self.on_dirty: Optional[Callable[[bool], None]] = None

        self._engine_active = False

        self._initialize_env()
        self.attach()
        self._recovery_needed  = False
        self._recovery_health  = None

    # --------------------------------------------------------------------------
    # FACTORY & ROOT MANAGEMENT
    # --------------------------------------------------------------------------

    @staticmethod
    def _check_project_integrity(project_path: Path) -> str:
        try:
            manifest_file = project_path / "manifest.json"
            if not manifest_file.exists():
                objects_path = project_path / "objects"
                if objects_path.exists() and any(objects_path.iterdir()):
                    return "corrupted"
                return "ok"

            manifest = json.loads(manifest_file.read_text())
            chunks = manifest.get("chunks", {})

            if not chunks:
                return "ok"

            objects_path = project_path / "objects"
            for chunk_name, content_hash in chunks.items():
                obj_path = objects_path / content_hash[:2] / content_hash
                if not obj_path.exists():
                    return "corrupted"

            return "ok"
        except Exception:
            return "corrupted"

    @staticmethod
    def _read_display_from_manifest(project_path: Path) -> str | None:
        try:
            manifest_file = project_path / "manifest.json"
            if not manifest_file.exists():
                return None

            manifest = json.loads(manifest_file.read_text())
            content_hash = manifest.get("chunks", {}).get("project_meta")
            if not content_hash:
                return None

            obj_path = project_path / "objects" / content_hash[:2] / content_hash
            if not obj_path.exists():
                return None

            with open(obj_path, "rb") as f:
                compressed = f.read()
            wrapped = json.loads(zlib.decompress(compressed).decode("utf-8"))
            return wrapped.get("payload", {}).get("display_name")
        except Exception:
            return None

    @staticmethod
    def list_all_projects(base_dir: str = "user_projects") -> list[dict]:
        """
        Lightweight scan — reads only version.json and filesystem stats.
        Safe to call frequently (home screen refresh).
        """
        root = Path(base_dir)
        if not root.exists():
            return []

        results = []
        for item in root.iterdir():
            if not item.is_dir():
                continue

            is_valid = (
                (item / "objects").exists()
                or (item / "manifest.json").exists()
                or (item / "chunks").exists()
            )
            if not is_valid:
                continue

            info = {
                "project_id": item.name,
                "display_name": item.name,
                "created_at": None,
                "last_modified": None,
                "status": "ok",
            }

            # ── status detection ──────────────────────────────────────────────
            lock_file = item / ".lock"
            if lock_file.exists():
                try:
                    locked_pid = int(lock_file.read_text().split(":")[1].strip())
                    if psutil.pid_exists(locked_pid):
                        info["status"] = "locked"
                except Exception:
                    pass

            forensics_path = item / "forensics"
            if forensics_path.exists() and any(forensics_path.glob("FAULT_*")):
                if info["status"] == "ok":
                    info["status"] = "crashed"

            # ── integrity check ───────────────────────────────────────────────
            if info["status"] == "ok":
                if SafeChunkEngine._check_project_integrity(item) == "corrupted":
                    info["status"] = "corrupted"

            # ── version.json ──────────────────────────────────────────────────
            version_file = item / "version.json"
            if version_file.exists():
                try:
                    data = json.loads(version_file.read_text())
                    display = data.get("display_name", "").strip()
                    info["display_name"] = (
                        display if display and display != item.name else item.name
                    )
                except Exception:
                    info["status"] = "corrupted"

            # ── fallback: project_meta chunk ──────────────────────────────────
            if info["display_name"] == item.name:
                try:
                    fallback = SafeChunkEngine._read_display_from_manifest(item)
                    if fallback:
                        info["display_name"] = fallback
                except Exception:
                    pass

            # ── filesystem timestamps ─────────────────────────────────────────
            try:
                stat = item.stat()
                info["created_at"] = time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(stat.st_ctime)
                )
                info["last_modified"] = time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)
                )
            except Exception:
                pass

            results.append(info)

        return results

    @staticmethod
    def get_project_info(
        project_id: str, base_dir: str = "user_projects"
    ) -> dict | None:
        root = Path(base_dir)
        item = root / project_id

        if not item.exists() or not item.is_dir():
            return None

        info = {
            "project_id": project_id,
            "display_name": project_id,
            "created_at": None,
            "last_modified": None,
            "status": "ok",
            "app_version": None,
            "engine_version": None,
            "last_opened": None,
            "chunk_count": 0,
            "checkpoint_count": 0,
            "last_checkpoint_date": None,
            "fault_count": 0,
            "fault_dates": [],
            "is_locked": False,
            "locked_by_pid": None,
            "size_kb": 0,
        }

        lock_file = item / ".lock"
        if lock_file.exists():
            try:
                locked_pid = int(lock_file.read_text().split(":")[1].strip())
                if psutil.pid_exists(locked_pid):
                    info["is_locked"] = True
                    info["locked_by_pid"] = locked_pid
                    info["status"] = "locked"
            except Exception:
                pass

        version_file = item / "version.json"
        if version_file.exists():
            try:
                data = json.loads(version_file.read_text())
                info["display_name"] = data.get("display_name", project_id)
                info["app_version"] = data.get("app_version")
                info["engine_version"] = data.get("engine_version")
                attached_at = data.get("attached_at")
                if attached_at:
                    info["last_opened"] = time.strftime(
                        "%Y-%m-%d %H:%M", time.localtime(attached_at)
                    )
            except Exception:
                info["status"] = "corrupted"

        manifest_file = item / "manifest.json"
        if manifest_file.exists():
            try:
                manifest = json.loads(manifest_file.read_text())
                info["chunk_count"] = len(manifest.get("chunks", {}))
            except Exception:
                if info["status"] == "ok":
                    info["status"] = "corrupted"

        try:
            stat = item.stat()
            info["created_at"] = time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(stat.st_ctime)
            )
            info["last_modified"] = time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)
            )
        except Exception:
            pass

        cp_path = item / "checkpoints"
        if cp_path.exists():
            zips = sorted(cp_path.glob("*.zip"), key=os.path.getmtime, reverse=True)
            info["checkpoint_count"] = len(zips)
            if zips:
                info["last_checkpoint_date"] = time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(zips[0]))
                )

        forensics_path = item / "forensics"
        if forensics_path.exists():
            fault_dirs = sorted(forensics_path.glob("FAULT_*"))
            info["fault_count"] = len(fault_dirs)
            info["fault_dates"] = [
                time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(fd)))
                for fd in fault_dirs
            ]
            if fault_dirs and info["status"] == "ok":
                info["status"] = "crashed"

        try:
            total = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
            info["size_kb"] = round(total / 1024, 1)
        except Exception:
            pass

        return info

    @classmethod
    def new(
        cls,
        project_id: str = None,
        display_name: str = None,
        base_dir: str = "user_projects",
        **kwargs,
    ):
        root = Path(base_dir)
        root.mkdir(parents=True, exist_ok=True)

        base_name = project_id or "new_project"
        target_id = base_name
        counter = 1
        while (root / target_id).exists():
            target_id = f"{base_name}_{counter}"
            counter += 1

        try:
            instance = cls(
                target_id, display_name=display_name, base_dir=str(root), **kwargs
            )
            return instance, "SUCCESS"
        except Exception as e:
            return None, f"FAILED_TO_CREATE: {str(e)}"

    @classmethod
    def open(cls, project_id: str, base_dir: str = "user_projects", **kwargs):
        root = Path(base_dir)
        if not (root / project_id).exists():
            return None, "PROJECT_NOT_FOUND"

        lock_file = root / project_id / ".lock"
        if lock_file.exists():
            try:
                lock_data = lock_file.read_text()
                existing_pid = int(lock_data.split(":")[1].strip())
                if not psutil.pid_exists(existing_pid):
                    lock_file.unlink()
            except Exception:
                try:
                    lock_file.unlink()
                except Exception:
                    pass

        try:
            instance = cls(project_id, base_dir=str(root), **kwargs)
            if not instance.is_active():
                return None, "PROJECT_ALREADY_OPEN_IN_ANOTHER_PROCESS"
            return instance, "SUCCESS"
        except Exception as e:
            return None, f"OPEN_ERROR: {str(e)}"

    def rename(self, new_display_name: str) -> bool:
        if not new_display_name.strip():
            return False
        self.display_name = new_display_name.strip()
        try:
            if self.version_file.exists():
                data = json.loads(self.version_file.read_text())
                data["display_name"] = self.display_name
                self.version_file.write_text(json.dumps(data, indent=4))
            self._log(f"Project renamed to '{self.display_name}'.")
            return True
        except Exception as e:
            self._handle_error(f"Rename failed: {e}")
            return False

    # --------------------------------------------------------------------------
    # PHASE 1 — KEY MANAGEMENT
    # --------------------------------------------------------------------------

    def _load_or_create_key(self) -> bytes:
        """
        Loads the project HMAC key or creates one if it doesn't exist.
        Key is generated once per project and never changes.
        """
        if self.key_file.exists():
            try:
                return bytes.fromhex(self.key_file.read_text().strip())
            except Exception:
                pass
        # Generate new key
        key = secrets.token_bytes(32)
        self.key_file.write_text(key.hex())
        return key

    def _compute_manifest_hmac(self, manifest_data: dict) -> str:
        """Computes HMAC-SHA256 of the manifest content."""
        key = self._load_or_create_key()
        content = json.dumps(
            manifest_data, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hmac.new(key, content, hashlib.sha256).hexdigest()

    def _sign_manifest(self, manifest_data: dict):
        """Writes manifest.sig alongside manifest.json."""
        try:
            sig = self._compute_manifest_hmac(manifest_data)
            self.sig_file.write_text(sig)
        except Exception as e:
            self._log(f"Warning: Could not sign manifest: {e}")

    def _verify_manifest_signature(self, manifest_data: dict) -> bool:
        """
        Returns True if manifest.sig matches current manifest content.
        Returns True if sig file doesn't exist yet (first open of old project).
        """
        if not self.sig_file.exists():
            return True  # no sig yet — old project, trust it
        try:
            stored_sig = self.sig_file.read_text().strip()
            expected_sig = self._compute_manifest_hmac(manifest_data)
            return hmac.compare_digest(stored_sig, expected_sig)
        except Exception:
            return False

    # --------------------------------------------------------------------------
    # PHASE 1 — WAL (WRITE-AHEAD LOG)
    # --------------------------------------------------------------------------

    def _wal_append(self, chunk_name: str, data: dict):
        """
        Appends a WAL entry synchronously before any disk write.
        Each entry: JSON line with checksum.
        Format: {"chunk": name, "ts": timestamp, "data": {...}, "crc": int}
        """
        try:
            entry = {
                "chunk": chunk_name,
                "ts": time.time(),
                "data": data,
            }
            line = json.dumps(entry, separators=(",", ":"))
            crc = zlib.crc32(line.encode("utf-8")) & 0xFFFFFFFF
            record = (
                json.dumps({"entry": line, "crc": crc}, separators=(",", ":")) + "\n"
            )

            with open(self.wal_file, "a", encoding="utf-8") as f:
                f.write(record)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            self._log(f"WAL append failed: {e}")

    def _wal_remove(self, chunk_name: str):
        """Removes committed entries for a chunk from the WAL."""
        if not self.wal_file.exists():
            return
        try:
            lines = self.wal_file.read_text(encoding="utf-8").splitlines()
            remaining = []
            for line in lines:
                try:
                    record = json.loads(line)
                    entry = json.loads(record["entry"])
                    if entry.get("chunk") != chunk_name:
                        remaining.append(line)
                except Exception:
                    remaining.append(line)  # keep unparseable lines

            if remaining:
                self.wal_file.write_text("\n".join(remaining) + "\n", encoding="utf-8")
            else:
                self.wal_file.unlink()
        except Exception as e:
            self._log(f"WAL remove failed: {e}")

    def _wal_replay(self) -> int:
        """
        Replays any uncommitted WAL entries into _staged_data.
        Called on attach() if WAL exists — recovers data from crashed session.
        Returns number of entries replayed.
        """
        if not self.wal_file.exists():
            return 0

        replayed = 0
        try:
            lines = self.wal_file.read_text(encoding="utf-8").splitlines()
            for line in lines:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    raw_line = record["entry"]
                    stored_crc = record["crc"]

                    # Verify CRC
                    actual_crc = zlib.crc32(raw_line.encode("utf-8")) & 0xFFFFFFFF
                    if actual_crc != stored_crc:
                        self._log(f"WAL: CRC mismatch, skipping corrupt entry.")
                        continue

                    entry = json.loads(raw_line)
                    chunk_name = entry["chunk"]
                    data = entry["data"]

                    # Replay into staged data
                    self._staged_data[chunk_name] = data
                    replayed += 1
                except Exception as e:
                    self._log(f"WAL: Skipping unreadable entry: {e}")
                    continue

            if replayed:
                self._log(
                    f"WAL: Replayed {replayed} uncommitted entries from last session."
                )

        except Exception as e:
            self._log(f"WAL replay failed: {e}")

        return replayed

    def _wal_clear(self):
        """Clears WAL after clean session close."""
        try:
            if self.wal_file.exists():
                self.wal_file.unlink()
                self._log("WAL cleared.")
        except Exception as e:
            self._log(f"WAL clear failed: {e}")

    # --------------------------------------------------------------------------
    # PHASE 1 — MANIFEST RING BUFFER
    # --------------------------------------------------------------------------

    def _rotate_manifest_ring(self, manifest_data: dict):
        """
        Rotates the manifest ring buffer before writing a new manifest.
        manifest.json   → manifest_1.json
        manifest_1.json → manifest_2.json
        manifest_2.json → manifest_3.json (oldest, dropped if > RING_SIZE)
        """
        try:
            # Shift existing ring entries back
            for i in range(self.MANIFEST_RING_SIZE - 1, 0, -1):
                src = self.project_path / f"manifest_{i}.json"
                dst = self.project_path / f"manifest_{i + 1}.json"
                if src.exists():
                    if i + 1 > self.MANIFEST_RING_SIZE:
                        src.unlink()  # drop oldest beyond ring size
                    else:
                        shutil.copy2(src, dst)

            # Current manifest → manifest_1.json
            if self.manifest_path.exists():
                shutil.copy2(self.manifest_path, self.project_path / "manifest_1.json")
        except Exception as e:
            self._log(f"Manifest ring rotation failed: {e}")

    def _load_manifest_with_fallback(self) -> dict:
        """
        Loads manifest, verifying HMAC. If corrupt or tampered,
        falls back through the ring buffer automatically.
        """
        # Try current manifest first
        candidates = [self.manifest_path] + [
            self.project_path / f"manifest_{i}.json"
            for i in range(1, self.MANIFEST_RING_SIZE + 1)
        ]

        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))

                # Verify signature only for the primary manifest
                if candidate == self.manifest_path:
                    if not self._verify_manifest_signature(data):
                        self._log(
                            f"TAMPER DETECTED: manifest.json signature mismatch. "
                            f"Falling back to ring buffer."
                        )
                        self._trigger_forensics(
                            "Manifest HMAC verification failed — possible tampering."
                        )
                        continue  # try next in ring

                self._log(f"Manifest loaded from: {candidate.name}")
                return data
            except Exception as e:
                self._log(f"Manifest load failed for {candidate.name}: {e}")
                continue

        self._log("All manifest candidates failed. Starting with empty manifest.")
        return {"chunks": {}}

    # --------------------------------------------------------------------------
    # LIFECYCLE MANAGEMENT
    # --------------------------------------------------------------------------

    def attach(self):
        if self.lock_file.exists():
            try:
                lock_data = self.lock_file.read_text()
                existing_pid = int(lock_data.split(":")[1].strip())
                if not psutil.pid_exists(existing_pid):
                    self._log(f"Removing stale lock from PID {existing_pid}")
                    self.lock_file.unlink()
                else:
                    self._engine_active = False
                    self._log("ATTACH_DENIED: Project open in another window.")
                    return
            except Exception as e:
                self._log(f"Lock validation error: {e}")

        try:
            # ── Preserve display_name ─────────────────────────────────────────
            existing_version = {}
            if self.version_file.exists():
                try:
                    existing_version = json.loads(self.version_file.read_text())
                except Exception:
                    pass

            saved_name = existing_version.get("display_name", "").strip()
            if self.display_name and self.display_name != self.project_id:
                final_name = self.display_name
            elif saved_name and saved_name != self.project_id:
                final_name = saved_name
            else:
                final_name = self.project_id
            self.display_name = final_name

            # ── Claim lock ────────────────────────────────────────────────────
            self.lock_file.write_text(f"PID: {os.getpid()}")

            # ── Load or create HMAC key ───────────────────────────────────────
            self._load_or_create_key()

            # ── WAL replay ────────────────────────────────────────────────────
            wal_entries = self._wal_replay()
            if wal_entries:
                self._session_dirty = True

            # ── Health check ──────────────────────────────────────────────────
            health = self.assess_health()

            if health["needs_recovery"]:
                self._log(
                    f"Health check failed: {health['issues']}. "
                    f"Creating .ebak before recovery."
                )
                # Create .ebak BEFORE touching anything
                self.create_ebak(reason="pre_recovery")
                self._recovery_needed = True
                self._recovery_health = health
            else:
                self._recovery_needed = False
                self._recovery_health = None

            # ── Write version.json ────────────────────────────────────────────
            self.version_file.write_text(
                json.dumps(
                    {
                        "engine_version": self.VERSION,
                        "app_version": self.app_version,
                        "attached_at": time.time(),
                        "project_id": self.project_id,
                        "display_name": self.display_name,
                        "wal_replayed": wal_entries,
                        "needs_recovery": self._recovery_needed,
                    },
                    indent=4,
                )
            )

            self._engine_active = True
            self._log(
                f"Engine v{self.VERSION} attached to "
                f"'{self.display_name}' ({self.project_id})."
                + (f" WAL replayed {wal_entries} entries." if wal_entries else "")
                + (" ⚠ Recovery needed." if self._recovery_needed else "")
            )

        except Exception as e:
            self._engine_active = False
            self._handle_error(f"Critical attach failure: {e}")

    def detach(self):
        if not self._engine_active:
            return

        self._log("Detaching. Performing final sync...")
        self.force_sync()

        with self._write_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            if self._force_save_timer:
                self._force_save_timer.cancel()
                self._force_save_timer = None

        # ── Auto-checkpoint if session had changes ────────────────────────────
        if self._session_dirty:
            try:
                self.create_checkpoint(
                    label="auto_close", notes="Automatic checkpoint on session close."
                )
                self._log("Auto-close checkpoint created.")
            except Exception as e:
                self._log(f"Auto-close checkpoint failed: {e}")

        # ── Clear WAL (clean close) ───────────────────────────────────────────
        self._wal_clear()

        # ── Write final version.json ──────────────────────────────────────────
        try:
            version_data = {}
            if self.version_file.exists():
                version_data = json.loads(self.version_file.read_text())
            version_data["display_name"] = self.display_name
            version_data["last_closed"] = time.time()
            self.version_file.write_text(json.dumps(version_data, indent=4))
        except Exception as e:
            self._log(f"Warning: Could not update version.json on detach: {e}")

        if self.lock_file.exists():
            self.lock_file.unlink()

        self._engine_active = False
        self._log("Engine detached. Lock released.")

    def is_active(self) -> bool:
        return self._engine_active

    def is_dirty(self) -> bool:
        with self._write_lock:
            return bool(self._staged_data)

    # --------------------------------------------------------------------------
    # CORE DATA OPERATIONS
    # --------------------------------------------------------------------------

    def _get_content_hash(self, data: Any) -> str:
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @requires_active
    def stage_update(self, data: dict, chunk_name: str):
        with self._write_lock:
            wrapped_data = {
                "_meta": {
                    "name": chunk_name,
                    "ts": time.time(),
                    "ver": self.VERSION,
                    "app_ver": self.app_version,
                },
                "payload": copy.deepcopy(data),
            }
            self._staged_data[chunk_name] = wrapped_data

            # ── WAL: append before debounce timer ────────────────────────────
            self._wal_append(chunk_name, wrapped_data)

            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(
                self.debounce_delay, self._commit_to_disk
            )
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

            if self._force_save_timer is None:
                self._force_save_timer = threading.Timer(
                    self.force_save_delay, self._force_save_from_timer
                )
                self._force_save_timer.daemon = True
                self._force_save_timer.start()

        if self.on_dirty:
            self.on_dirty(True)
        if self.on_status:
            self.on_status("Unsaved changes...")

    @requires_active
    def fetch_chunk(self, chunk_name: str) -> dict:
        with self._write_lock:
            if chunk_name in self._staged_data:
                return copy.deepcopy(self._staged_data[chunk_name]["payload"])

        manifest = self._load_manifest_with_fallback()
        content_hash = manifest.get("chunks", {}).get(chunk_name)
        if not content_hash:
            return {}

        obj_path = self.object_store / content_hash[:2] / content_hash
        if not obj_path.exists():
            self._trigger_forensics(
                f"Broken Manifest Link: {chunk_name} → {content_hash}"
            )
            return self._attempt_scavenge(chunk_name)

        try:
            with open(obj_path, "rb") as f:
                compressed_data = f.read()
            decompressed = zlib.decompress(compressed_data).decode("utf-8")
            wrapped_data = json.loads(decompressed)

            if self._get_content_hash(wrapped_data) != content_hash:
                self._trigger_forensics(
                    f"INTEGRITY MISMATCH: {chunk_name} modified externally.",
                    obj_path,
                )
                return {}

            return wrapped_data.get("payload", {})
        except Exception as e:
            self._trigger_forensics(f"Read error for {chunk_name}: {e}")
            return {}

    read_chunk = fetch_chunk

    @requires_active
    def force_sync(self):
        with self._write_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            if self._force_save_timer:
                self._force_save_timer.cancel()
                self._force_save_timer = None
        self._commit_to_disk()

    def _force_save_from_timer(self):
        with self._write_lock:
            self._force_save_timer = None
        self._commit_to_disk()
        self._log(f"Force-save fired after {self.force_save_delay}s.")

    # --------------------------------------------------------------------------
    # ATOMIC PERSISTENCE
    # --------------------------------------------------------------------------

    def _commit_to_disk(self):
        with self._write_lock:
            if not self._staged_data or not self._engine_active:
                return

            manifest = self._load_manifest_with_fallback()
            failed_chunks = []

            for chunk_name, data in list(self._staged_data.items()):
                content_hash = self._get_content_hash(data)

                shard_dir = self.object_store / content_hash[:2]
                shard_dir.mkdir(parents=True, exist_ok=True)
                obj_path = shard_dir / content_hash

                if not obj_path.exists():
                    try:
                        t_file = obj_path.with_suffix(".tmp")
                        compressed_data = zlib.compress(
                            json.dumps(data).encode("utf-8")
                        )
                        with open(t_file, "wb") as f:
                            f.write(compressed_data)
                            f.flush()
                            os.fsync(f.fileno())
                        t_file.replace(obj_path)
                    except Exception as e:
                        failed_chunks.append(chunk_name)
                        self._trigger_forensics(
                            f"Object sync failure [{chunk_name}]: {e}", obj_path
                        )
                        continue

                manifest["chunks"][chunk_name] = content_hash
                del self._staged_data[chunk_name]

                # ── WAL: remove committed entry ───────────────────────────────
                self._wal_remove(chunk_name)

            manifest["app_version"] = self.app_version

            # ── Rotate ring buffer then write + sign manifest ─────────────────
            self._rotate_manifest_ring(manifest)
            self._save_manifest_atomic(manifest)
            self._sign_manifest(manifest)

            self._session_dirty = True
            self._debounce_timer = None

            if failed_chunks:
                self._handle_error(f"Sync failed for: {failed_chunks}")
            else:
                if self.on_dirty:
                    self.on_dirty(False)
                if self.on_sync:
                    self.on_sync()
                self._log("Commit successful.")

    # --------------------------------------------------------------------------
    # FORENSICS & RECOVERY
    # --------------------------------------------------------------------------

    def _trigger_forensics(self, reason: str, offending_path: Optional[Path] = None):
        ts = time.strftime("%Y%m%d_%H%M%S")
        report_dir = self.forensics_path / f"FAULT_{ts}"
        report_dir.mkdir(parents=True, exist_ok=True)

        report = {
            "trigger": reason,
            "timestamp": time.time(),
            "engine_ver": self.VERSION,
            "app_ver": self.app_version,
            "project_id": self.project_id,
            "recent_logs": self.log_history[-20:],
        }

        try:
            with open(report_dir / "fault_report.json", "w") as f:
                json.dump(report, f, indent=4)

            if self.manifest_path.exists():
                shutil.copy2(self.manifest_path, report_dir / "manifest_snapshot.json")
            tmp_manifest = self.manifest_path.with_suffix(".tmp")
            if tmp_manifest.exists():
                shutil.copy2(tmp_manifest, report_dir / "manifest_partial.tmp")

            if offending_path and offending_path.exists():
                shutil.copy2(
                    offending_path, report_dir / f"offending_data_{offending_path.name}"
                )

            if self.lock_file.exists():
                shutil.copy2(self.lock_file, report_dir / "lock_state.lock")
            if self.version_file.exists():
                shutil.copy2(self.version_file, report_dir / "version_context.json")

            # Also preserve WAL if it exists
            if self.wal_file.exists():
                shutil.copy2(self.wal_file, report_dir / "wal_snapshot.log")

            self._log(f"Forensic snapshot: forensics/FAULT_{ts}")
        except Exception as e:
            self._log(f"Forensics capture failed: {e}")

        if self.on_fault:
            self.on_fault(f"Data Integrity Failure: {reason}")

    def _attempt_scavenge(self, chunk_name: str) -> dict:
        self._log(f"SCAVENGER: Searching for '{chunk_name}'...")
        for shard in self.object_store.iterdir():
            if not shard.is_dir():
                continue
            for obj in shard.glob("*"):
                try:
                    with open(obj, "rb") as f:
                        compressed_data = f.read()
                    decompressed = zlib.decompress(compressed_data).decode("utf-8")
                    data = json.loads(decompressed)
                    if data.get("_meta", {}).get("name") == chunk_name:
                        self._log(f"SCAVENGER: Found '{chunk_name}' in {obj.name}")
                        manifest = self._load_manifest_with_fallback()
                        manifest["chunks"][chunk_name] = obj.name
                        manifest["app_version"] = self.app_version
                        self._save_manifest_atomic(manifest)
                        self._sign_manifest(manifest)
                        return data.get("payload", {})
                except Exception:
                    continue
        return {}

    def rebuild_manifest_from_objects(self):
        self._log("RECOVERY: Rebuilding manifest from objects...")
        new_manifest = {
            "project_id": self.project_id,
            "chunks": {},
            "engine_version": self.VERSION,
            "app_version": self.app_version,
            "reconstructed_at": time.time(),
        }

        count = 0
        for shard in self.object_store.iterdir():
            if not shard.is_dir():
                continue
            for obj in shard.glob("*"):
                try:
                    with open(obj, "rb") as f:
                        compressed_data = f.read()
                    decompressed = zlib.decompress(compressed_data).decode("utf-8")
                    data = json.loads(decompressed)
                    name = data.get("_meta", {}).get("name")
                    if name:
                        new_manifest["chunks"][name] = obj.name
                        count += 1
                except Exception:
                    continue

        self._save_manifest_atomic(new_manifest)
        self._sign_manifest(new_manifest)
        self._log(f"RECOVERY: Manifest rebuilt with {count} chunks.")

    # --------------------------------------------------------------------------
    # CHECKPOINTS
    # --------------------------------------------------------------------------

    @requires_active
    def create_checkpoint(
        self, label: str = "manual", notes: str = "", retention: int = 10
    ) -> str | None:
        self.force_sync()
        clean_label = re.sub(r"[^\w\-_]", "_", label)[:30]
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        zip_name = f"cp_{clean_label}_{timestamp}.zip"
        zip_path = self.checkpoint_path / zip_name

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                if self.manifest_path.exists():
                    zf.write(self.manifest_path, arcname="manifest.json")
                if self.version_file.exists():
                    zf.write(self.version_file, arcname="version.json")
                if self.sig_file.exists():
                    zf.write(self.sig_file, arcname="manifest.sig")

                # Ring buffer manifests
                for i in range(1, self.MANIFEST_RING_SIZE + 1):
                    rb = self.project_path / f"manifest_{i}.json"
                    if rb.exists():
                        zf.write(rb, arcname=f"manifest_{i}.json")

                for shard in self.object_store.glob("*"):
                    if shard.is_dir():
                        for obj in shard.glob("*"):
                            zf.write(obj, arcname=f"objects/{shard.name}/{obj.name}")

                for fault_dir in self.forensics_path.glob("FAULT_*"):
                    if fault_dir.is_dir():
                        for f in fault_dir.glob("*"):
                            zf.write(f, arcname=f"forensics/{fault_dir.name}/{f.name}")

                meta = {
                    "timestamp": timestamp,
                    "label": label,
                    "notes": notes,
                    "engine_ver": self.VERSION,
                    "app_ver": self.app_version,
                    "project_id": self.project_id,
                }
                zf.writestr("checkpoint_meta.json", json.dumps(meta, indent=4))

            # Compute and store checkpoint HMAC
            key = self._load_or_create_key()
            zip_data = zip_path.read_bytes()
            cp_sig = hmac.new(key, zip_data, hashlib.sha256).hexdigest()
            (self.checkpoint_path / f"{zip_name}.sig").write_text(cp_sig)

            # Retention
            history = sorted(self.checkpoint_path.glob("*.zip"), key=os.path.getmtime)
            while len(history) > retention:
                oldest = history.pop(0)
                oldest.unlink()
                sig_file = oldest.with_suffix(".zip.sig")
                if sig_file.exists():
                    sig_file.unlink()

            self._log(f"Checkpoint created: {zip_name}")
            return zip_name
        except Exception as e:
            self._handle_error(f"Checkpoint failed: {e}")
            return None

    def verify_checkpoint(self, zip_name: str) -> bool:
        """Verifies checkpoint HMAC before restore."""
        zip_path = self.checkpoint_path / zip_name
        sig_path = self.checkpoint_path / f"{zip_name}.sig"

        if not zip_path.exists():
            return False
        if not sig_path.exists():
            return True  # old checkpoint without sig, trust it

        try:
            key = self._load_or_create_key()
            zip_data = zip_path.read_bytes()
            expected = hmac.new(key, zip_data, hashlib.sha256).hexdigest()
            stored = sig_path.read_text().strip()
            result = hmac.compare_digest(expected, stored)
            if not result:
                self._log(f"TAMPER DETECTED: Checkpoint {zip_name} signature mismatch.")
                self._trigger_forensics(f"Checkpoint HMAC failed: {zip_name}")
            return result
        except Exception as e:
            self._log(f"Checkpoint verification error: {e}")
            return False

    @requires_active
    def restore_checkpoint(self, zip_name: str) -> bool:
        zip_path = self.checkpoint_path / zip_name
        if not zip_path.exists():
            return False

        # Verify before restore
        if not self.verify_checkpoint(zip_name):
            self._log(f"Restore aborted: checkpoint {zip_name} failed verification.")
            return False

        staging_path = self.project_path / "_restore_staging"
        try:
            with self._write_lock:
                if self._debounce_timer:
                    self._debounce_timer.cancel()
                if self._force_save_timer:
                    self._force_save_timer.cancel()
                self._staged_data.clear()

            if staging_path.exists():
                shutil.rmtree(staging_path)
            staging_path.mkdir()

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(path=staging_path)

            with self._write_lock:
                if self.object_store.exists():
                    shutil.rmtree(self.object_store)
                if self.manifest_path.exists():
                    self.manifest_path.unlink()

                if (staging_path / "objects").exists():
                    shutil.move(str(staging_path / "objects"), str(self.object_store))
                if (staging_path / "manifest.json").exists():
                    shutil.move(
                        str(staging_path / "manifest.json"), str(self.manifest_path)
                    )
                if (staging_path / "manifest.sig").exists():
                    shutil.move(str(staging_path / "manifest.sig"), str(self.sig_file))

                # Restore ring buffer
                for i in range(1, self.MANIFEST_RING_SIZE + 1):
                    src = staging_path / f"manifest_{i}.json"
                    if src.exists():
                        shutil.move(
                            str(src), str(self.project_path / f"manifest_{i}.json")
                        )

            shutil.rmtree(staging_path, ignore_errors=True)
            self._wal_clear()
            self._log(f"Restored from: {zip_name}")
            return True
        except Exception as e:
            shutil.rmtree(staging_path, ignore_errors=True)
            self._handle_error(f"Restore failed: {e}")
            return False

    def list_checkpoints(self) -> list:
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
                            "verified": self.verify_checkpoint(zp.name),
                        }
                    )
            except Exception:
                continue
        return sorted(cp_list, key=lambda x: x["date"], reverse=True)

    def delete_project(self, confirmed: bool = False):
        if not confirmed:
            return False
        try:
            self.detach()
            if self.project_path.exists():
                shutil.rmtree(self.project_path)
            return True
        except Exception as e:
            self._handle_error(f"Failed to delete project: {e}")
            return False

    # --------------------------------------------------------------------------
    # INTERNAL HELPERS & DIAGNOSTICS
    # --------------------------------------------------------------------------

    def _initialize_env(self):
        for path in [
            self.object_store,
            self.forensics_path,
            self.checkpoint_path,
            self.backup_path,
        ]:
            path.mkdir(parents=True, exist_ok=True)

        v1_chunks = self.project_path / "chunks"
        if v1_chunks.exists() and not self.manifest_path.exists():
            self._log("MIGRATION: V1 → V2...")
            manifest = {
                "project_id": self.project_id,
                "chunks": {},
                "engine_version": self.VERSION,
                "app_version": self.app_version,
            }
            for chunk_file in v1_chunks.glob("*.json"):
                try:
                    with open(chunk_file, "r", encoding="utf-8") as f:
                        content = json.load(f)
                    wrapped = {
                        "_meta": {
                            "name": chunk_file.stem,
                            "ts": time.time(),
                            "ver": self.VERSION,
                            "app_ver": self.app_version,
                        },
                        "payload": content,
                    }
                    c_hash = self._get_content_hash(wrapped)
                    shard_dir = self.object_store / c_hash[:2]
                    shard_dir.mkdir(exist_ok=True)
                    compressed = zlib.compress(json.dumps(wrapped).encode("utf-8"))
                    with open(shard_dir / c_hash, "wb") as f:
                        f.write(compressed)
                    manifest["chunks"][chunk_file.stem] = c_hash
                except Exception:
                    continue
            self._save_manifest_atomic(manifest)
            self._sign_manifest(manifest)
            self._log("MIGRATION: Complete.")

        if not self.manifest_path.exists():
            has_objects = any(d.is_dir() for d in self.object_store.iterdir())
            if has_objects:
                self.rebuild_manifest_from_objects()
            else:
                empty = {
                    "project_id": self.project_id,
                    "chunks": {},
                    "engine_version": self.VERSION,
                    "app_version": self.app_version,
                }
                self._save_manifest_atomic(empty)
                self._sign_manifest(empty)

    def _save_manifest_atomic(self, manifest_data: dict):
        tmp = self.manifest_path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(self.manifest_path)
        except Exception as e:
            self._handle_error(f"Failed to save manifest: {e}")

    def _load_manifest(self) -> dict:
        """Direct manifest load without fallback — used internally."""
        if not self.manifest_path.exists():
            return {"chunks": {}}
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self._trigger_forensics(f"Manifest read error: {e}")
            return {"chunks": {}}

    def _log(self, message: str):
        timestamped = f"[{time.strftime('%H:%M:%S')}] {message}"
        self.log_history.append(timestamped)
        if len(self.log_history) > 100:
            self.log_history.pop(0)
        if self.on_status:
            self.on_status(message)
        else:
            print(timestamped)

    def _handle_error(self, error_message: str):
        self._log(f"CRITICAL FAULT: {error_message}")
        if self.on_fault:
            self.on_fault(str(error_message))

    def get_health_report(self) -> dict:
        manifest = self._load_manifest()
        return {
            "active": self._engine_active,
            "project": self.project_id,
            "display_name": self.display_name,
            "version": self.VERSION,
            "app_version": self.app_version,
            "shards_count": len(manifest.get("chunks", {})),
            "checkpoints_count": len(list(self.checkpoint_path.glob("*.zip"))),
            "pending_syncs": len(self._staged_data),
            "forensics_count": len(list(self.forensics_path.glob("FAULT_*"))),
            "wal_exists": self.wal_file.exists(),
            "session_dirty": self._session_dirty,
            "manifest_signed": self.sig_file.exists(),
        }

    # --------------------------------------------------------------------------
    # PHASE 2 — .EBAK PRESERVATION
    # --------------------------------------------------------------------------

    def create_ebak(self, reason: str = "manual") -> str | None:
        """
        Creates a raw .ebak ZIP of the entire project folder as-is.
        Stored in backups/ — never auto-deleted.
        Includes everything: objects, manifests, forensics, WAL, version.json.
        """
        self.backup_path.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        clean_reason = re.sub(r"[^\w\-_]", "_", reason)[:30]
        ebak_name = f"backup_{clean_reason}_{timestamp}.ebak"
        ebak_path = self.backup_path / ebak_name

        try:
            with zipfile.ZipFile(ebak_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in self.project_path.rglob("*"):
                    # Skip the backups folder itself to avoid recursion
                    if self.backup_path in f.parents:
                        continue
                    if f.is_file():
                        zf.write(f, arcname=f.relative_to(self.project_path))

                # Embed metadata about why this backup was created
                meta = {
                    "reason": reason,
                    "timestamp": timestamp,
                    "project_id": self.project_id,
                    "engine_ver": self.VERSION,
                    "app_ver": self.app_version,
                }
                zf.writestr("ebak_meta.json", json.dumps(meta, indent=4))

            self._log(f"EBAK created: {ebak_name} (reason: {reason})")
            return ebak_name
        except Exception as e:
            self._log(f"EBAK creation failed: {e}")
            return None

    def list_ebaks(self) -> list[dict]:
        """Lists all .ebak backup files with their metadata."""
        results = []
        for ebak in self.backup_path.glob("*.ebak"):
            try:
                with zipfile.ZipFile(ebak, "r") as zf:
                    meta = json.loads(zf.read("ebak_meta.json"))
                    results.append(
                        {
                            "filename": ebak.name,
                            "reason": meta.get("reason", ""),
                            "timestamp": meta.get("timestamp", ""),
                            "size_kb": round(ebak.stat().st_size / 1024, 1),
                        }
                    )
            except Exception:
                results.append(
                    {
                        "filename": ebak.name,
                        "reason": "unknown",
                        "timestamp": "",
                        "size_kb": round(ebak.stat().st_size / 1024, 1),
                    }
                )
        return sorted(results, key=lambda x: x["timestamp"], reverse=True)

    def restore_ebak(self, ebak_name: str) -> bool:
        """
        Restores the project from a .ebak file.
        Wipes current project folder contents (except backups/) and extracts.
        """
        ebak_path = self.backup_path / ebak_name
        if not ebak_path.exists():
            self._log(f"EBAK not found: {ebak_name}")
            return False

        staging_path = self.project_path / "_ebak_staging"
        try:
            if staging_path.exists():
                shutil.rmtree(staging_path)
            staging_path.mkdir()

            with zipfile.ZipFile(ebak_path, "r") as zf:
                zf.extractall(path=staging_path)

            # Wipe current project except backups/
            for item in self.project_path.iterdir():
                if item == self.backup_path:
                    continue
                if item == staging_path:
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

            # Move staging contents to project root
            for item in staging_path.iterdir():
                shutil.move(str(item), str(self.project_path / item.name))

            shutil.rmtree(staging_path, ignore_errors=True)
            self._log(f"EBAK restored: {ebak_name}")
            return True
        except Exception as e:
            shutil.rmtree(staging_path, ignore_errors=True)
            self._log(f"EBAK restore failed: {e}")
            return False

    # --------------------------------------------------------------------------
    # PHASE 2 — RECOVERY CHAIN
    # --------------------------------------------------------------------------

    def assess_health(self) -> dict:
        """
        Checks project health without modifying anything.
        Returns a report used to decide if recovery is needed.
        """
        report = {
            "needs_recovery": False,
            "wal_exists": self.wal_file.exists(),
            "manifest_ok": False,
            "manifest_signed": False,
            "objects_ok": False,
            "missing_chunks": [],
            "issues": [],
        }

        # Check manifest
        if not self.manifest_path.exists():
            report["issues"].append("manifest.json missing")
            report["needs_recovery"] = True
        else:
            try:
                manifest = json.loads(self.manifest_path.read_text())
                report["manifest_ok"] = True

                # Check HMAC
                if self.sig_file.exists():
                    if self._verify_manifest_signature(manifest):
                        report["manifest_signed"] = True
                    else:
                        report["issues"].append(
                            "manifest.sig mismatch — possible tampering"
                        )
                        report["needs_recovery"] = True

                # Check all referenced objects exist
                chunks = manifest.get("chunks", {})
                for chunk_name, content_hash in chunks.items():
                    obj_path = self.object_store / content_hash[:2] / content_hash
                    if not obj_path.exists():
                        report["missing_chunks"].append(chunk_name)

                if report["missing_chunks"]:
                    report["issues"].append(
                        f"Missing objects for chunks: {report['missing_chunks']}"
                    )
                    report["needs_recovery"] = True
                else:
                    report["objects_ok"] = True

            except Exception as e:
                report["issues"].append(f"manifest.json unreadable: {e}")
                report["needs_recovery"] = True

        return report

    def run_recovery_chain(self) -> dict:
        """
        Attempts to recover the project through the full recovery chain.
        Returns a result dict describing what happened.

        Chain:
          1. WAL replay
          2. Manifest ring buffer fallback
          3. Last auto_close checkpoint
          4. Last manual checkpoint
          5. Full object store rebuild
          6. Partial open (whatever survived)
          7. Unrecoverable
        """
        result = {
            "success": False,
            "level": None,
            "description": "",
            "data_loss": False,
            "missing_chunks": [],
        }

        self._log("RECOVERY: Starting recovery chain...")

        # ── Step 1: WAL replay ────────────────────────────────────────────────
        if self.wal_file.exists():
            replayed = self._wal_replay()
            if replayed:
                self._log(f"RECOVERY L1: WAL replayed {replayed} entries.")
                # Commit WAL data to disk immediately
                self._commit_to_disk()
                health = self.assess_health()
                if not health["needs_recovery"]:
                    result.update(
                        {
                            "success": True,
                            "level": 1,
                            "description": f"Recovered {replayed} unsaved changes from WAL.",
                        }
                    )
                    return result

        # ── Step 2: Manifest ring buffer ──────────────────────────────────────
        for i in range(1, self.MANIFEST_RING_SIZE + 1):
            ring_manifest = self.project_path / f"manifest_{i}.json"
            if ring_manifest.exists():
                try:
                    data = json.loads(ring_manifest.read_text())
                    # Verify all referenced objects still exist
                    missing = [
                        c
                        for c, h in data.get("chunks", {}).items()
                        if not (self.object_store / h[:2] / h).exists()
                    ]
                    if not missing:
                        shutil.copy2(ring_manifest, self.manifest_path)
                        self._sign_manifest(data)
                        self._log(
                            f"RECOVERY L2: Restored manifest from ring buffer #{i}."
                        )
                        result.update(
                            {
                                "success": True,
                                "level": 2,
                                "description": f"Manifest restored from ring buffer (backup #{i}).",
                            }
                        )
                        return result
                except Exception as e:
                    self._log(f"RECOVERY L2: Ring buffer #{i} failed: {e}")
                    continue

        # ── Step 3 + 4: Checkpoints ───────────────────────────────────────────
        checkpoints = sorted(
            self.checkpoint_path.glob("*.zip"), key=os.path.getmtime, reverse=True
        )

        # Prioritize auto_close checkpoints first
        ordered = [c for c in checkpoints if "auto_close" in c.name] + [
            c for c in checkpoints if "auto_close" not in c.name
        ]

        for cp in ordered:
            try:
                if not self.verify_checkpoint(cp.name):
                    self._log(
                        f"RECOVERY: Checkpoint {cp.name} failed verification, skipping."
                    )
                    continue

                is_auto = "auto_close" in cp.name
                level = 3 if is_auto else 4

                if self.restore_checkpoint(cp.name):
                    self._log(f"RECOVERY L{level}: Restored from checkpoint {cp.name}.")
                    result.update(
                        {
                            "success": True,
                            "level": level,
                            "description": f"Restored from {'auto-save' if is_auto else 'manual'} checkpoint: {cp.name}",
                            "data_loss": is_auto,  # auto checkpoints may not have latest
                        }
                    )
                    return result
            except Exception as e:
                self._log(f"RECOVERY: Checkpoint {cp.name} failed: {e}")
                continue

        # ── Step 5: Full object store rebuild ─────────────────────────────────
        try:
            self.rebuild_manifest_from_objects()
            health = self.assess_health()
            if not health["missing_chunks"]:
                self._log("RECOVERY L5: Full rebuild from object store succeeded.")
                result.update(
                    {
                        "success": True,
                        "level": 5,
                        "description": "Manifest rebuilt by scanning all stored objects.",
                        "data_loss": True,
                    }
                )
                return result
        except Exception as e:
            self._log(f"RECOVERY L5: Rebuild failed: {e}")

        # ── Step 6: Partial open ──────────────────────────────────────────────
        try:
            self.rebuild_manifest_from_objects()
            health = self.assess_health()
            if health["manifest_ok"]:
                self._log(
                    f"RECOVERY L6: Partial open. "
                    f"Missing: {health['missing_chunks']}"
                )
                result.update(
                    {
                        "success": True,
                        "level": 6,
                        "description": "Project partially recovered. Some data could not be restored.",
                        "data_loss": True,
                        "missing_chunks": health["missing_chunks"],
                    }
                )
                return result
        except Exception as e:
            self._log(f"RECOVERY L6: Partial open failed: {e}")

        # ── Step 7: Unrecoverable ─────────────────────────────────────────────
        self._log("RECOVERY L7: All recovery attempts failed.")
        result.update(
            {
                "success": False,
                "level": 7,
                "description": "Project could not be recovered. Data may be permanently lost.",
                "data_loss": True,
            }
        )
        return result
