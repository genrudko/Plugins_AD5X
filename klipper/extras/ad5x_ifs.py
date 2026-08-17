# Plugins AD5X - read-only bridge from Z-Mod IFS/job state to Klipper status API.
#
# Z-Mod remains the sole owner of the IFS serial protocol and slicer color
# matching semantics. This adapter snapshots the in-memory state already owned
# by Z-Mod and offers a read-only job-preview command. It never opens the IFS
# serial device, writes file.json, changes FFMInfo, or starts a print.

FFS_STATE_NAMES = {
    3: "polling",
    5: "ready",
    7: "clamped",
    11: "loading",
    12: "releasing",
    15: "unloading",
    127: "driver_error",
}

JOB_PREVIEW_COMMAND = "AD5X_IFS_JOB_PREVIEW"

# Source-verified Z-Mod zmod_color flags. _zmod_flag() prefers the values from
# the live method globals and uses these only as compatibility defaults.
AUTO_ASSIGN_ANY_SUCCESS = 1 << 0
AUTO_ASSIGN_MATERIAL_FAILURE = 1 << 1
AUTO_ASSIGN_COLOR_FAILURE = 1 << 2
AUTO_ASSIGN_COLOR_WEAK = 1 << 3
AUTO_ASSIGN_DUPLICATE = 1 << 4


class _PreviewGcmd:
    """Minimal gcmd facade accepted by zmod_color's read-only helpers."""

    def __init__(self, filename):
        self.filename = filename
        self.messages = []

    def get(self, name, default=None):
        if name == "FILENAME":
            return self.filename
        return default

    def get_int(self, name, default=None):
        value = self.get(name, default)
        if value is None:
            return None
        return int(value)

    def respond_raw(self, message):
        self.messages.append(str(message))

    def error(self, message):
        return RuntimeError(str(message))


class AD5XIFS:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.zmod_ifs = None
        self.zmod_color = None
        self.job_preview = self._empty_job_preview("not_scanned")
        self.gcode = self.printer.lookup_object("gcode", None)
        if self.gcode is not None and hasattr(self.gcode, "register_command"):
            self.gcode.register_command(JOB_PREVIEW_COMMAND, self.cmd_JOB_PREVIEW)
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler("klippy:disconnect", self._handle_disconnect)
        self.printer.register_event_handler("klippy:shutdown", self._handle_disconnect)

    @staticmethod
    def _empty_job_preview(error=""):
        return {
            "available": False,
            "source": "zmod",
            "filename": "",
            "requirements": [],
            "assignments": [],
            "allowed_tool_count": 0,
            "resolved_tool_map": [],
            "auto_assign": {
                "flags": 0,
                "any_success": False,
                "material_failure": False,
                "color_failure": False,
                "weak_color": False,
                "duplicate_slot": False,
            },
            "messages": [],
            "error": error,
        }

    def _handle_ready(self):
        candidate = self.printer.lookup_object("zmod_ifs", None)
        if candidate is None or not hasattr(candidate, "ifs_data"):
            self.zmod_ifs = None
        else:
            self.zmod_ifs = candidate

        candidate = self.printer.lookup_object("zmod_color", None)
        required = (
            "get_used_colors",
            "get_printer_data_detail",
            "parse_printer_response",
            "get_auto_tool_assignments",
        )
        if candidate is None or not all(hasattr(candidate, name) for name in required):
            self.zmod_color = None
        else:
            self.zmod_color = candidate

    def _handle_disconnect(self):
        self.zmod_ifs = None
        self.zmod_color = None
        self.job_preview = self._empty_job_preview("klippy_disconnected")

    def _unavailable(self):
        return {
            "available": False,
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
            "job_preview": dict(self.job_preview),
        }

    @staticmethod
    def _safe_filename(filename):
        if not isinstance(filename, str):
            return False
        filename = filename.strip()
        if not filename or filename.startswith("/") or "\x00" in filename:
            return False
        parts = filename.replace("\\", "/").split("/")
        return all(part not in ("", "..") for part in parts)

    @staticmethod
    def _normalize_requirement(entry):
        tool, color, material = entry
        try:
            tool = int(tool)
        except (TypeError, ValueError):
            tool = -1
        color = color.strip().upper() if isinstance(color, str) else ""
        material = material.strip().upper() if isinstance(material, str) else ""
        return {
            "tool": tool,
            "color": color,
            "material": material,
        }

    def _zmod_flag(self, name, default):
        zmod_color = self.zmod_color
        method = getattr(zmod_color, "get_auto_tool_assignments", None)
        function = getattr(method, "__func__", method)
        globals_dict = getattr(function, "__globals__", {})
        value = globals_dict.get(name, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _auto_assign_state(self, flags):
        any_success = self._zmod_flag("AUTO_ASSIGN_ANY_SUCCESS", AUTO_ASSIGN_ANY_SUCCESS)
        material_failure = self._zmod_flag(
            "AUTO_ASSIGN_MATERIAL_FAILURE", AUTO_ASSIGN_MATERIAL_FAILURE
        )
        color_failure = self._zmod_flag(
            "AUTO_ASSIGN_COLOR_FAILURE", AUTO_ASSIGN_COLOR_FAILURE
        )
        weak_color = self._zmod_flag("AUTO_ASSIGN_COLOR_WEAK", AUTO_ASSIGN_COLOR_WEAK)
        duplicate = self._zmod_flag("AUTO_ASSIGN_DUPLICATE", AUTO_ASSIGN_DUPLICATE)
        return {
            "flags": int(flags),
            "any_success": bool(flags & any_success),
            "material_failure": bool(flags & material_failure),
            "color_failure": bool(flags & color_failure),
            "weak_color": bool(flags & weak_color),
            "duplicate_slot": bool(flags & duplicate),
        }

    def cmd_JOB_PREVIEW(self, gcmd):
        filename = gcmd.get("FILENAME", "")
        if not self._safe_filename(filename):
            raise gcmd.error("Invalid FILENAME for AD5X IFS job preview")
        filename = filename.strip()

        zmod_color = self.zmod_color
        if zmod_color is None:
            self.job_preview = self._empty_job_preview("zmod_color_unavailable")
            raise gcmd.error("zmod_color is unavailable")

        adapter = _PreviewGcmd(filename)
        old_file_colors_present = hasattr(zmod_color, "file_colors")
        old_file_colors = getattr(zmod_color, "file_colors", None)
        try:
            file_colors = list(zmod_color.get_used_colors(adapter) or [])
            status_code, response_data = zmod_color.get_printer_data_detail()
            if not status_code:
                raise RuntimeError("zmod_color printer detail unavailable")
            raw_slots = list(zmod_color.parse_printer_response(response_data) or [])

            requirements = [self._normalize_requirement(item) for item in file_colors]
            valid_tools = [item["tool"] for item in requirements if item["tool"] >= 0]
            tool_count = (max(valid_tools) + 1) if valid_tools else 0
            tools = [1] * tool_count
            output_text = []

            zmod_color.file_colors = file_colors
            flags = 0
            if tool_count:
                flags = int(
                    zmod_color.get_auto_tool_assignments(
                        adapter,
                        tools,
                        raw_slots,
                        output_text,
                        False,
                    )
                    or 0
                )

            requirement_tools = set(valid_tools)
            assignments = [
                {"tool": tool, "slot": int(slot)}
                for tool, slot in enumerate(tools)
                if tool in requirement_tools and int(slot) > 0
            ]
            messages = (adapter.messages + [str(item) for item in output_text])[-32:]
            self.job_preview = {
                "available": True,
                "source": "zmod",
                "filename": filename,
                "requirements": requirements,
                "assignments": assignments,
                "allowed_tool_count": tool_count,
                "resolved_tool_map": [int(slot) for slot in tools],
                "auto_assign": self._auto_assign_state(flags),
                "messages": messages,
                "error": "",
            }
        except Exception as exc:
            self.job_preview = self._empty_job_preview(str(exc))
            self.job_preview["filename"] = filename
            raise gcmd.error("AD5X IFS job preview failed: %s" % exc)
        finally:
            if old_file_colors_present:
                zmod_color.file_colors = old_file_colors
            else:
                try:
                    delattr(zmod_color, "file_colors")
                except AttributeError:
                    pass

        gcmd.respond_raw("AD5X_IFS_JOB_PREVIEW_OK")

    def get_status(self, eventtime):
        zmod_ifs = self.zmod_ifs
        if zmod_ifs is None:
            return self._unavailable()

        ifs_data = getattr(zmod_ifs, "ifs_data", None)
        if ifs_data is None or not hasattr(ifs_data, "get_values"):
            return self._unavailable()

        values = ifs_data.get_values()
        ports = list(values.get("Ports") or [])
        state_code = int(values.get("State") or 0)
        silk_mask = int(values.get("Silk") or 0)
        raw_channel = int(values.get("Chan") or 0)
        insert_slot = int(values.get("Insert") or 0)
        stall_mask = int(values.get("stall_state") or 0)

        # cur_port is the Z-Mod runtime selection populated from FFMInfo.channel.
        # It is intentionally distinct from the raw F13 `chan` diagnostic field.
        active_slot = int(getattr(ifs_data, "cur_port", 0) or 0)
        if active_slot < 0 or active_slot > len(ports):
            active_slot = 0

        slots = []
        for index, present in enumerate(ports, start=1):
            slots.append({
                "slot": index,
                "present": bool(present),
                "stall": bool(stall_mask & (1 << (index - 1))),
            })

        available = bool(getattr(zmod_ifs, "get_ifs_status", lambda: True)())
        return {
            "available": available,
            "state": FFS_STATE_NAMES.get(state_code, "unknown"),
            "state_code": state_code,
            "active_slot": active_slot,
            "slots": slots,
            "silk_mask": silk_mask,
            "raw_channel": raw_channel,
            "insert_slot": insert_slot,
            "need_insert": bool(values.get("NeedInsert", False)),
            "stall": bool(values.get("Stall", False)),
            "stall_mask": stall_mask,
            "job_preview": dict(self.job_preview),
        }


def load_config(config):
    return AD5XIFS(config)
