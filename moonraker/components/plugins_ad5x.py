# Plugins AD5X - optional Moonraker foundation component

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple

from ..common import RequestType, TransportType

try:
    from .plugins_ad5x_ifs_model import (
        IFS_SCHEMA_VERSION,
        normalize_appearance,
        normalize_module,
        normalize_spool_metadata,
    )
except ImportError:
    # Minimal test/source-tree compatibility. Production installer deploys the
    # helper beside this managed component and the normal relative import wins.
    _model_path = Path(__file__).with_name("plugins_ad5x_ifs_model.py")
    _model_spec = importlib.util.spec_from_file_location(
        "moonraker.components.plugins_ad5x_ifs_model",
        _model_path,
    )
    if _model_spec is None or _model_spec.loader is None:
        raise
    _model_module = importlib.util.module_from_spec(_model_spec)
    _model_spec.loader.exec_module(_model_module)
    IFS_SCHEMA_VERSION = _model_module.IFS_SCHEMA_VERSION
    normalize_appearance = _model_module.normalize_appearance
    normalize_module = _model_module.normalize_module
    normalize_spool_metadata = _model_module.normalize_spool_metadata

API_VERSION = "1.0"
BACKEND_VERSION = "0.1.6"

SNAPSHOT_ENDPOINT = "/server/plugins_ad5x/snapshot"
IFS_ACTION_ENDPOINT = "/server/plugins_ad5x/ifs/action"
IFS_METADATA_ENDPOINT = "/server/plugins_ad5x/ifs/metadata"
IFS_JOB_PREVIEW_ENDPOINT = "/server/plugins_ad5x/ifs/job/preview"
SNAPSHOT_CHANGED_EVENT = "plugins_ad5x:snapshot_changed"
SNAPSHOT_CHANGED_NOTIFY_NAME = "plugins_ad5x_snapshot_changed"
IFS_OBJECT = "ad5x_ifs"
PRINT_STATS_OBJECT = "print_stats"
HEAD_SENSOR_OBJECT = "filament_switch_sensor head_switch_sensor"

FFCONFIG_PATH = "/usr/prog/config/Adventurer5M.json"
FILE_MAPPING_PATH = "/usr/data/config/mod_data/file.json"
IFS_METADATA_STORE_PATH = "/opt/config/mod_data/ad5x_custom/ifs_metadata.json"
IFS_METADATA_STORE_MAX_BYTES = 64 * 1024

SAFE_FILAMENT_OP_PRINT_STATES = {"standby", "complete", "cancelled", "error"}
SAFE_JOB_PREVIEW_PRINT_STATES = {"standby", "complete", "cancelled", "error"}
IFS_JOB_PREVIEW_COMMAND = "AD5X_IFS_JOB_PREVIEW"
IFS_ACTION_COMMANDS = {
    "select_slot": "SET_EXTRUDER_SLOT SLOT={slot}",
    "load_slot": "INSERT_PRUTOK_IFS PRUTOK={slot}",
    # Z-Mod's stock toolhead-unload wrapper: it owns heat/cut/trash/cooldown semantics.
    "unload_slot": "_IFS_REMOVE_CURRENT_PRUTOK",
}


class PluginsAD5X:
    def __init__(self, config: Any) -> None:
        self.server = config.get_server()
        self._revision = 1
        self._ifs_raw: Dict[str, Any] = {}
        self._ifs_metadata: Dict[str, Any] = {}
        self._ifs_module = None
        self._print_state = "unknown"
        self._head_filament = None
        self._operation_state = "idle"
        self._operation_action = ""
        self._operation_slot = 0
        self._operation_error = ""
        self._metadata_store_status = self._store_status("missing")
        self._metadata_write_lock = asyncio.Lock()

        self.server.register_endpoint(
            SNAPSHOT_ENDPOINT,
            RequestType.GET,
            self._handle_snapshot,
            transports=TransportType.HTTP | TransportType.WEBSOCKET,
            auth_required=True,
        )
        self.server.register_endpoint(
            IFS_ACTION_ENDPOINT,
            RequestType.POST,
            self._handle_ifs_action,
            transports=TransportType.HTTP | TransportType.WEBSOCKET,
            auth_required=True,
        )
        self.server.register_endpoint(
            IFS_METADATA_ENDPOINT,
            RequestType.POST,
            self._handle_ifs_metadata,
            transports=TransportType.HTTP | TransportType.WEBSOCKET,
            auth_required=True,
        )
        self.server.register_endpoint(
            IFS_JOB_PREVIEW_ENDPOINT,
            RequestType.POST,
            self._handle_ifs_job_preview,
            transports=TransportType.HTTP | TransportType.WEBSOCKET,
            auth_required=True,
        )
        self.server.register_notification(
            SNAPSHOT_CHANGED_EVENT,
            SNAPSHOT_CHANGED_NOTIFY_NAME,
        )

        # Keep the foundation component importable/testable without Klipper.
        # Real Moonraker provides event handlers; hardware discovery happens only
        # after Klippy reports ready and never blocks component construction.
        if hasattr(self.server, "register_event_handler"):
            self.server.register_event_handler("server:klippy_ready", self._on_klippy_ready)
            self.server.register_event_handler(
                "server:klippy_disconnect", self._on_klippy_disconnect
            )

    @staticmethod
    def _store_status(status: str, error: str = "") -> Dict[str, Any]:
        return {
            "status": status,
            "schema_version": IFS_SCHEMA_VERSION,
            "error": error,
        }

    @staticmethod
    def _empty_manual_store() -> Dict[str, Any]:
        return {
            "schema_version": IFS_SCHEMA_VERSION,
            "slots": {},
        }

    def _unavailable_ifs(self, reason: str) -> Dict[str, Any]:
        raw = {
            "available": False,
            "reason": reason,
            "state": "unavailable",
            "state_code": 0,
            "active_slot": 0,
            "slots": [],
            "silk_mask": 0,
            "raw_channel": 0,
            "insert_slot": 0,
            "need_insert": False,
            "stall": False,
            "stall_mask": 0,
        }
        module = normalize_module(
            raw,
            self._ifs_metadata,
            self._print_state,
            self._head_filament,
            {
                "state": self._operation_state,
                "action": self._operation_action,
                "slot": self._operation_slot,
                "error": self._operation_error,
            },
        )
        module["metadata_store"] = dict(self._metadata_store_status)
        return module

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "api_version": API_VERSION,
            "backend_version": BACKEND_VERSION,
            "revision": self._revision,
            "backend": {
                "health": "ok",
            },
            "modules": (
                {} if self._ifs_module is None else {"ifs": dict(self._ifs_module)}
            ),
        }

    async def _handle_snapshot(self, _web_request: Any) -> Dict[str, Any]:
        # Persistent metadata sources are tiny but live outside Moonraker
        # ownership. Refresh them on demand instead of adding a polling loop.
        await self._refresh_ifs_metadata()
        return self.get_snapshot()

    def invalidate_snapshot(self) -> int:
        self._revision += 1
        self.server.send_event(
            SNAPSHOT_CHANGED_EVENT,
            {"revision": self._revision},
        )
        return self._revision

    def _set_ifs_module(self, module: Dict[str, Any]) -> bool:
        normalized = dict(module)
        if self._ifs_module is not None and normalized == self._ifs_module:
            return False
        self._ifs_module = normalized
        self.invalidate_snapshot()
        return True

    def _compose_ifs_module(self) -> Dict[str, Any]:
        module = normalize_module(
            self._ifs_raw,
            self._ifs_metadata,
            self._print_state,
            self._head_filament,
            {
                "state": self._operation_state,
                "action": self._operation_action,
                "slot": self._operation_slot,
                "error": self._operation_error,
            },
        )
        module["metadata_store"] = dict(self._metadata_store_status)
        return module

    def _apply_ifs_status(self, payload: Dict[str, Any]) -> bool:
        # Klipper subscriptions may deliver partial object updates. Merge into
        # the last complete state before publishing the canonical module.
        self._ifs_raw.update(payload)
        return self._set_ifs_module(self._compose_ifs_module())

    def _apply_aux_status(self, status: Dict[str, Any]) -> bool:
        changed = False
        print_stats = status.get(PRINT_STATS_OBJECT)
        if isinstance(print_stats, dict):
            state = print_stats.get("state")
            if isinstance(state, str) and state and state != self._print_state:
                self._print_state = state
                changed = True

        head = status.get(HEAD_SENSOR_OBJECT)
        if isinstance(head, dict):
            enabled = head.get("enabled", True)
            detected = head.get("filament_detected")
            normalized = bool(detected) if enabled and isinstance(detected, bool) else None
            if normalized != self._head_filament:
                self._head_filament = normalized
                changed = True
        return changed

    @staticmethod
    def _read_json(path: str) -> Any:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def _manual_record_has_metadata(record: Dict[str, Any]) -> bool:
        spool = record.get("spool") if isinstance(record.get("spool"), dict) else {}
        appearance = (
            record.get("appearance")
            if isinstance(record.get("appearance"), dict)
            else {}
        )
        return bool(
            spool.get("brand")
            or spool.get("series")
            or spool.get("name")
            or spool.get("material")
            or spool.get("variant")
            or spool.get("spoolman_id")
            or spool.get("remaining_g") is not None
            or appearance.get("colors")
            or appearance.get("finish") not in (None, "", "standard")
        )

    @staticmethod
    def _normalize_manual_record(
        spool: Dict[str, Any], appearance: Dict[str, Any]
    ) -> Dict[str, Any]:
        normalized_spool = normalize_spool_metadata(spool)
        normalized_spool["source"] = "manual"
        normalized_appearance = normalize_appearance(None, appearance)
        return {
            "spool": normalized_spool,
            "appearance": normalized_appearance,
        }

    def _read_manual_metadata_store_sync(
        self,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        path = Path(IFS_METADATA_STORE_PATH)
        if not path.exists():
            return self._empty_manual_store(), self._store_status("missing")
        if not path.is_file() or path.is_symlink():
            return self._empty_manual_store(), self._store_status("invalid", "not_regular_file")
        try:
            if path.stat().st_size > IFS_METADATA_STORE_MAX_BYTES:
                return self._empty_manual_store(), self._store_status("invalid", "too_large")
            payload = self._read_json(str(path))
        except json.JSONDecodeError:
            return self._empty_manual_store(), self._store_status("invalid", "invalid_json")
        except OSError:
            return self._empty_manual_store(), self._store_status("invalid", "read_error")

        if not isinstance(payload, dict):
            return self._empty_manual_store(), self._store_status("invalid", "invalid_root")
        if payload.get("schema_version") != IFS_SCHEMA_VERSION:
            return self._empty_manual_store(), self._store_status("invalid", "unsupported_schema")
        raw_slots = payload.get("slots", {})
        if not isinstance(raw_slots, dict):
            return self._empty_manual_store(), self._store_status("invalid", "invalid_slots")

        slots: Dict[str, Dict[str, Any]] = {}
        for raw_slot, raw_record in raw_slots.items():
            try:
                slot = int(raw_slot)
            except (TypeError, ValueError):
                return self._empty_manual_store(), self._store_status("invalid", "invalid_slot_key")
            if slot < 1 or slot > 4 or not isinstance(raw_record, dict):
                return self._empty_manual_store(), self._store_status("invalid", "invalid_slot_record")
            spool = raw_record.get("spool", {})
            appearance = raw_record.get("appearance", {})
            if not isinstance(spool, dict) or not isinstance(appearance, dict):
                return self._empty_manual_store(), self._store_status("invalid", "invalid_slot_record")
            normalized_spool = normalize_spool_metadata(spool)
            if normalized_spool.get("source") == "unknown":
                normalized_spool["source"] = "manual"
            slots[str(slot)] = {
                "spool": normalized_spool,
                "appearance": normalize_appearance(None, appearance),
            }

        return {
            "schema_version": IFS_SCHEMA_VERSION,
            "slots": slots,
        }, self._store_status("ok")

    def _write_manual_metadata_store_sync(self, store: Dict[str, Any]) -> None:
        path = Path(IFS_METADATA_STORE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            store,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        encoded = payload.encode("utf-8")
        if len(encoded) > IFS_METADATA_STORE_MAX_BYTES:
            raise ValueError("metadata store exceeds size limit")

        tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
            try:
                directory_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
            except OSError:
                directory_fd = -1
            if directory_fd >= 0:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _overlay_manual_metadata(
        metadata: Dict[str, Any], manual_store: Dict[str, Any]
    ) -> None:
        raw_slots = manual_store.get("slots", {})
        if not isinstance(raw_slots, dict) or not raw_slots:
            return
        slots = metadata.setdefault("slots", {})
        if not isinstance(slots, dict):
            slots = {}
            metadata["slots"] = slots

        for raw_slot, record in raw_slots.items():
            if not isinstance(record, dict):
                continue
            try:
                slot = int(raw_slot)
            except (TypeError, ValueError):
                continue
            current = dict(slots.get(slot, {})) if isinstance(slots.get(slot), dict) else {}
            spool = record.get("spool") if isinstance(record.get("spool"), dict) else {}
            appearance = (
                record.get("appearance")
                if isinstance(record.get("appearance"), dict)
                else {}
            )
            current["spool"] = dict(spool)
            current["appearance"] = dict(appearance)
            material = spool.get("material")
            if isinstance(material, str) and material:
                # Keep old frontend flat fields aligned with the effective manual overlay.
                current["material"] = material
            colors = appearance.get("colors")
            if isinstance(colors, list) and colors:
                current["color"] = colors[0]
            slots[slot] = current

    def _read_ifs_metadata_sync(
        self,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        metadata: Dict[str, Any] = {}

        try:
            ffconfig = self._read_json(FFCONFIG_PATH)
            ffm_info = ffconfig.get("FFMInfo", {}) if isinstance(ffconfig, dict) else {}
            if isinstance(ffm_info, dict):
                active_slot = int(ffm_info.get("channel", 0) or 0)
                if 1 <= active_slot <= 4:
                    metadata["active_slot"] = active_slot

                slots: Dict[int, Dict[str, Any]] = {}
                for slot in range(1, 5):
                    slot_data: Dict[str, Any] = {}
                    material = ffm_info.get(f"ffmType{slot}")
                    color = ffm_info.get(f"ffmColor{slot}")
                    if isinstance(material, str) and material:
                        slot_data["material"] = material
                    if isinstance(color, str) and color:
                        slot_data["color"] = color
                    zmod_compat: Dict[str, Any] = {}
                    if isinstance(material, str) and material:
                        zmod_compat["material"] = material
                    if isinstance(color, str) and color:
                        zmod_compat["color"] = color
                    if zmod_compat:
                        slot_data["zmod_compat"] = zmod_compat
                    if slot_data:
                        slots[slot] = slot_data
                if slots:
                    metadata["slots"] = slots
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # Slot presence/state remains available from the Klipper bridge even
            # when persistent FlashForge metadata cannot be read.
            pass

        try:
            mapping = self._read_json(FILE_MAPPING_PATH)
            if (
                isinstance(mapping, list)
                and mapping
                and all(
                    isinstance(slot, int)
                    and not isinstance(slot, bool)
                    and 1 <= slot <= 4
                    for slot in mapping
                )
            ):
                metadata["tool_mapping"] = list(mapping)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

        manual_store, store_status = self._read_manual_metadata_store_sync()
        if store_status.get("status") != "invalid":
            self._overlay_manual_metadata(metadata, manual_store)
        return metadata, store_status

    async def _run_io(self, callback: Any, *args: Any) -> Any:
        try:
            event_loop = self.server.get_event_loop()
        except (AttributeError, TypeError):
            event_loop = None
        if event_loop is not None and hasattr(event_loop, "run_in_thread"):
            return await event_loop.run_in_thread(callback, *args)
        return callback(*args)

    async def _refresh_ifs_metadata(self) -> bool:
        metadata, store_status = await self._run_io(self._read_ifs_metadata_sync)
        metadata_changed = metadata != self._ifs_metadata
        status_changed = store_status != self._metadata_store_status
        if not metadata_changed and not status_changed:
            return False
        self._ifs_metadata = metadata
        self._metadata_store_status = store_status
        if self._ifs_raw:
            return self._set_ifs_module(self._compose_ifs_module())
        return False

    def _operation_begin(self, action: str, slot: int) -> None:
        self._operation_state = "running"
        self._operation_action = action
        self._operation_slot = slot
        self._operation_error = ""
        if self._ifs_raw:
            self._set_ifs_module(self._compose_ifs_module())

    def _operation_end(self, error: str = "") -> None:
        self._operation_state = "idle"
        self._operation_action = ""
        self._operation_slot = 0
        self._operation_error = error
        if self._ifs_raw:
            self._set_ifs_module(self._compose_ifs_module())

    def _action_rejection(self, action: str, slot: int, error: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "action": action,
            "slot": slot,
            "error": error,
            "snapshot": self.get_snapshot(),
        }

    def _metadata_rejection(self, slot: int, error: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "slot": slot,
            "error": error,
            "snapshot": self.get_snapshot(),
        }

    def _validate_ifs_action(self, action: str, slot: int) -> str:
        if action not in IFS_ACTION_COMMANDS:
            return f"Unsupported IFS action: {action}"
        if slot < 1 or slot > 4:
            return f"Invalid IFS slot: {slot}"
        if self._ifs_module is None or not self._ifs_module.get("available", False):
            return "IFS is not available"
        if self._ifs_module.get("state") != "ready":
            return f"IFS is not ready: {self._ifs_module.get('state', 'unknown')}"
        if self._operation_state != "idle":
            return "Another IFS operation is already running"
        # Helix hardware research proved Z-Mod filament macros may self-home and
        # move the toolhead. Refuse writes not only while printing but also while
        # PAUSED; unknown/non-idle job states fail closed as well.
        if self._print_state not in SAFE_FILAMENT_OP_PRINT_STATES:
            return f"IFS operations are blocked while print state is {self._print_state}"

        slots = self._ifs_module.get("slots") or []
        slot_data = next(
            (
                item
                for item in slots
                if isinstance(item, dict) and item.get("slot") == slot
            ),
            {},
        )
        present = bool(slot_data.get("present", False))
        active_slot = int(self._ifs_module.get("active_slot") or 0)

        if action in ("select_slot", "load_slot") and not present:
            return f"IFS slot {slot} is empty"
        if action == "load_slot" and active_slot == slot and self._head_filament is True:
            return f"IFS slot {slot} is already loaded at the toolhead"
        if action == "unload_slot":
            if active_slot != slot:
                return "First normal implementation only unloads the active toolhead slot"
            if self._head_filament is not True:
                return "Toolhead filament presence is not confirmed; use Manage/recovery instead"
        return ""

    async def _handle_ifs_metadata(self, web_request: Any) -> Dict[str, Any]:
        try:
            slot = web_request.get_int("slot")
            if slot < 1 or slot > 4:
                raise ValueError(f"Invalid IFS slot: {slot}")
            if hasattr(web_request, "get_boolean"):
                clear = web_request.get_boolean("clear", False)
            else:
                clear = bool(web_request.get("clear", False))
        except Exception as exc:
            return self._metadata_rejection(0, f"Invalid IFS metadata request: {exc}")

        record = None
        if not clear:
            try:
                spool = web_request.get("spool", {})
                appearance = web_request.get("appearance", {})
            except Exception as exc:
                return self._metadata_rejection(slot, f"Invalid IFS metadata request: {exc}")
            if not isinstance(spool, dict) or not isinstance(appearance, dict):
                return self._metadata_rejection(
                    slot, "spool and appearance must be JSON objects"
                )
            record = self._normalize_manual_record(spool, appearance)
            if not self._manual_record_has_metadata(record):
                return self._metadata_rejection(
                    slot, "manual metadata is empty; use clear=true to remove an assignment"
                )

        async with self._metadata_write_lock:
            store, status = await self._run_io(self._read_manual_metadata_store_sync)
            if status.get("status") == "invalid":
                return self._metadata_rejection(
                    slot,
                    f"manual metadata store is invalid: {status.get('error', 'unknown')}",
                )
            slots = store.setdefault("slots", {})
            slot_key = str(slot)
            if clear:
                if slot_key not in slots:
                    await self._refresh_ifs_metadata()
                    return {
                        "ok": True,
                        "slot": slot,
                        "result": "already_clear",
                        "snapshot": self.get_snapshot(),
                    }
                slots.pop(slot_key, None)
                result = "cleared"
            else:
                slots[slot_key] = record
                result = "updated"
            try:
                await self._run_io(self._write_manual_metadata_store_sync, store)
            except Exception as exc:
                return self._metadata_rejection(
                    slot, f"failed to persist manual metadata: {exc}"
                )

        await self._refresh_ifs_metadata()
        return {
            "ok": True,
            "slot": slot,
            "result": result,
            "snapshot": self.get_snapshot(),
        }

    @staticmethod
    def _job_preview_rejection(filename: str, error: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "filename": filename,
            "error": error,
        }

    @staticmethod
    def _job_preview_filename_valid(filename: str) -> bool:
        if not isinstance(filename, str):
            return False
        filename = filename.strip()
        if (
            not filename
            or filename.startswith("/")
            or "\x00" in filename
            or '"' in filename
            or "\n" in filename
            or "\r" in filename
        ):
            return False
        parts = filename.replace("\\", "/").split("/")
        return all(part not in ("", "..") for part in parts)

    async def _handle_ifs_job_preview(self, web_request: Any) -> Dict[str, Any]:
        try:
            filename = web_request.get_str("filename").strip()
        except Exception as exc:
            return self._job_preview_rejection(
                "", f"Invalid IFS job preview request: {exc}"
            )

        if not self._job_preview_filename_valid(filename):
            return self._job_preview_rejection(filename, "Invalid IFS job preview filename")
        if self._ifs_module is None or not self._ifs_module.get("available", False):
            return self._job_preview_rejection(filename, "IFS bridge is not available")
        if self._operation_state != "idle":
            return self._job_preview_rejection(
                filename, "IFS operation is already running"
            )
        if self._print_state not in SAFE_JOB_PREVIEW_PRINT_STATES:
            return self._job_preview_rejection(
                filename,
                f"IFS job preview is blocked while print state is {self._print_state}",
            )

        command = f'{IFS_JOB_PREVIEW_COMMAND} FILENAME="{filename}"'
        try:
            klippy_apis = self.server.lookup_component("klippy_apis")
            await klippy_apis.run_gcode(command)
            status = await klippy_apis.query_objects({IFS_OBJECT: None}, default={})
        except Exception as exc:
            return self._job_preview_rejection(
                filename, str(exc) or exc.__class__.__name__
            )

        payload = status.get(IFS_OBJECT) if isinstance(status, dict) else None
        if isinstance(payload, dict):
            self._ifs_raw.update(payload)
            self._set_ifs_module(self._compose_ifs_module())

        module = self._ifs_module if isinstance(self._ifs_module, dict) else {}
        preview = module.get("job_preview")
        if not isinstance(preview, dict) or not preview.get("available", False):
            error = (
                preview.get("error")
                if isinstance(preview, dict)
                else "job_preview_not_published"
            )
            return self._job_preview_rejection(
                filename, f"Z-Mod job preview unavailable: {error or 'unknown'}"
            )

        return {
            "ok": True,
            "filename": filename,
            "job_preview": dict(preview),
            "snapshot": self.get_snapshot(),
        }

    async def _refresh_live_after_action(self, klippy_apis: Any) -> None:
        objects: Dict[str, Any] = {
            IFS_OBJECT: None,
            PRINT_STATS_OBJECT: ["state"],
            HEAD_SENSOR_OBJECT: ["enabled", "filament_detected"],
        }
        try:
            status = await klippy_apis.query_objects(objects, default={})
        except Exception:
            status = {}
        if isinstance(status, dict):
            payload = status.get(IFS_OBJECT)
            if isinstance(payload, dict):
                self._ifs_raw.update(payload)
            self._apply_aux_status(status)
        await self._refresh_ifs_metadata()
        if self._ifs_raw:
            self._set_ifs_module(self._compose_ifs_module())

    async def _handle_ifs_action(self, web_request: Any) -> Dict[str, Any]:
        try:
            action = web_request.get_str("action")
            slot = web_request.get_int("slot")
        except Exception as exc:
            return self._action_rejection("", 0, f"Invalid IFS action request: {exc}")

        await self._refresh_ifs_metadata()
        rejection = self._validate_ifs_action(action, slot)
        if rejection:
            return self._action_rejection(action, slot, rejection)

        # Selecting the already active lane is a safe no-op and avoids sending a
        # redundant firmware write.
        if action == "select_slot" and int(self._ifs_module.get("active_slot") or 0) == slot:
            return {
                "ok": True,
                "action": action,
                "slot": slot,
                "result": "already_selected",
                "snapshot": self.get_snapshot(),
            }

        command = IFS_ACTION_COMMANDS[action].format(slot=slot)
        self._operation_begin(action, slot)
        try:
            klippy_apis = self.server.lookup_component("klippy_apis")
            result = await klippy_apis.run_gcode(command)
            self._operation_end()
            await self._refresh_live_after_action(klippy_apis)
            return {
                "ok": True,
                "action": action,
                "slot": slot,
                "result": result,
                "snapshot": self.get_snapshot(),
            }
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            self._operation_end(error)
            return self._action_rejection(action, slot, error)

    async def _on_klippy_ready(self) -> None:
        try:
            klippy_apis = self.server.lookup_component("klippy_apis")
            objects = await klippy_apis.get_object_list(default=[])
        except Exception:
            self._ifs_raw.clear()
            self._set_ifs_module(self._unavailable_ifs("klippy_api_error"))
            return

        if IFS_OBJECT not in objects:
            self._ifs_raw.clear()
            self._set_ifs_module(self._unavailable_ifs("bridge_not_loaded"))
            return

        subscription: Dict[str, Any] = {
            IFS_OBJECT: None,
            PRINT_STATS_OBJECT: ["state"],
        }
        if HEAD_SENSOR_OBJECT in objects:
            subscription[HEAD_SENSOR_OBJECT] = ["enabled", "filament_detected"]

        try:
            initial = await klippy_apis.subscribe_objects(
                subscription,
                callback=self._on_status_update,
                default={},
            )
        except Exception:
            self._ifs_raw.clear()
            self._set_ifs_module(self._unavailable_ifs("bridge_subscribe_error"))
            return

        payload = initial.get(IFS_OBJECT, {}) if isinstance(initial, dict) else {}
        if not isinstance(payload, dict):
            payload = {}
        self._ifs_raw = dict(payload)
        if isinstance(initial, dict):
            self._apply_aux_status(initial)
        await self._refresh_ifs_metadata()
        if self._ifs_raw:
            self._apply_ifs_status({})
        else:
            self._set_ifs_module(self._unavailable_ifs("bridge_empty"))

    async def _on_status_update(
        self, status: Dict[str, Dict[str, Any]], _eventtime: float
    ) -> None:
        changed = False
        payload = status.get(IFS_OBJECT)
        if isinstance(payload, dict):
            self._ifs_raw.update(payload)
            changed = True
        if self._apply_aux_status(status):
            changed = True
        if changed and self._ifs_raw:
            self._set_ifs_module(self._compose_ifs_module())

    async def _on_klippy_disconnect(self) -> None:
        self._ifs_raw.clear()
        self._print_state = "unknown"
        self._head_filament = None
        self._operation_state = "idle"
        self._operation_action = ""
        self._operation_slot = 0
        self._operation_error = ""
        self._set_ifs_module(self._unavailable_ifs("klippy_disconnected"))


def load_component(config: Any) -> PluginsAD5X:
    return PluginsAD5X(config)
