# Plugins AD5X - transient common-mode Z anchor for the active bed mesh.
# Never persists the shifted copy and never writes the user gcode Z offset.
import math

RUNTIME_PROFILE = "adz_runtime_anchor"
COMMAND_APPLY = "ADZ_MESH_ANCHOR"
COMMAND_RESET = "ADZ_MESH_ANCHOR_RESET"
MESH_COMMAND = "_BED_MESH_CALIBRATE"
PROBE_COMMAND = "PROBE"
MEASUREMENT_OBJECT = "gcode_macro _ADZ_MEASUREMENT_POLICY"

class AD5XZMeshAnchor:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.max_abs_shift = config.getfloat("max_abs_shift", 0.31, above=0.0)
        self.gcode = self.printer.lookup_object("gcode")
        self.gcode.register_command(COMMAND_APPLY, self.cmd_APPLY)
        self.gcode.register_command(COMMAND_RESET, self.cmd_RESET)
        self._mesh_calibrate_base = None
        self._probe_base = None
        self.metrology_hooks_ready = False
        self._clear_state()
        self.printer.register_event_handler("klippy:disconnect", self._disconnect)
        self.printer.register_event_handler("klippy:shutdown", self._disconnect)
        # Install metrology interposers only after Z-Mod connect-time renames settle.
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        # Reset the transient mesh at the VirtualSD job boundary, before START_PRINT.
        self.printer.register_event_handler("virtual_sdcard:reset_file", self._reset_file)

    def _clear_state(self):
        self.base_mesh = None
        self.runtime_mesh = None
        self.shift = 0.0
        self.base_profile = ""
        self.point_count = 0

    def _disconnect(self, *args):
        self._clear_state()

    def _reset_file(self, *args):
        bed_mesh = self.printer.lookup_object("bed_mesh", None)
        if bed_mesh is None or not hasattr(bed_mesh, "get_mesh") or not hasattr(bed_mesh, "set_mesh"):
            self._clear_state()
            return
        self._reconcile_owner(bed_mesh)
        if self.runtime_mesh is not None:
            bed_mesh.set_mesh(self.base_mesh)
        self._clear_state()

    def _measurement_status(self, config_phase=False):
        obj = self.printer.lookup_object(MEASUREMENT_OBJECT, None)
        values = getattr(obj, "variables", None) if obj is not None else None
        if values is None and obj is not None and hasattr(obj, "get_status"):
            values = obj.get_status(None)
        error = getattr(self.printer, "config_error", self.gcode.error) if config_phase else self.gcode.error
        if not isinstance(values, dict):
            raise error("Plugins AD5X Z metrology: measurement policy runtime is unavailable")
        required = ("mesh_probe_speed", "mesh_probe_samples", "mesh_probe_result", "final_probe_speed", "final_probe_samples", "final_probe_result", "final_probe_armed", "final_probe_completed", "final_probe_x", "final_probe_y", "fresh_mesh_built", "fresh_native_check_done")
        missing = [name for name in required if name not in values]
        if missing:
            raise error("Plugins AD5X Z metrology: incomplete measurement policy: %s" % ", ".join(missing))
        return dict(values)

    def _handle_ready(self):
        if self.metrology_hooks_ready:
            return
        # The extra may remain installed while the v6 policy is intentionally
        # absent (legacy/rollback/uninstall baseline). In that state it owns no
        # metrology command hooks and must not prevent Klipper from becoming ready.
        if self.printer.lookup_object(MEASUREMENT_OBJECT, None) is None:
            return
        self._measurement_status(config_phase=True)
        mesh_base = self.gcode.register_command(MESH_COMMAND, None)
        if mesh_base is None:
            raise self.printer.config_error("Plugins AD5X Z metrology: Z-Mod _BED_MESH_CALIBRATE unavailable after connect")
        probe_base = self.gcode.register_command(PROBE_COMMAND, None)
        if probe_base is None:
            self.gcode.register_command(MESH_COMMAND, mesh_base)
            raise self.printer.config_error("Plugins AD5X Z metrology: Klipper PROBE unavailable")
        try:
            self.gcode.register_command(MESH_COMMAND, self._cmd_mesh_calibrate)
            self.gcode.register_command(PROBE_COMMAND, self._cmd_probe)
        except Exception:
            self.gcode.register_command(MESH_COMMAND, None); self.gcode.register_command(PROBE_COMMAND, None)
            self.gcode.register_command(MESH_COMMAND, mesh_base); self.gcode.register_command(PROBE_COMMAND, probe_base)
            raise
        self._mesh_calibrate_base = mesh_base
        self._probe_base = probe_base
        self.metrology_hooks_ready = True

    def _set_measurement(self, **values):
        script = "\n".join("SET_GCODE_VARIABLE MACRO=_ADZ_MEASUREMENT_POLICY VARIABLE=%s VALUE=%r" % item for item in values.items())
        self.gcode.run_script_from_command(script)

    def _print_state(self):
        obj = self.printer.lookup_object("print_stats", None)
        return str(obj.get_status(None).get("state", "unknown")) if obj is not None and hasattr(obj, "get_status") else "unknown"

    def _gcode_xy(self):
        obj = self.printer.lookup_object("gcode_move", None)
        status = obj.get_status(None) if obj is not None and hasattr(obj, "get_status") else {}
        pos = status.get("gcode_position")
        if pos is None or len(pos) < 2:
            raise self.gcode.error("Plugins AD5X Z metrology: gcode position unavailable")
        return float(pos[0]), float(pos[1])

    def _forward(self, command, base, gcmd, forced):
        raw = gcmd.get_raw_command_parameters().strip()
        tail = " ".join("%s=%s" % item for item in forced)
        params = " ".join(part for part in (raw, tail) if part)
        forwarded = self.gcode.create_gcode_command(command, command + ((" " + params) if params else ""), {})
        base(forwarded)

    def _cmd_mesh_calibrate(self, gcmd):
        if self._mesh_calibrate_base is None:
            raise gcmd.error("Plugins AD5X Z metrology: mesh hook not initialized")
        m = self._measurement_status()
        built_for_print = self._print_state() == "printing"
        self._set_measurement(fresh_mesh_built=0, fresh_native_check_done=0, final_probe_completed=0)
        self._forward(MESH_COMMAND, self._mesh_calibrate_base, gcmd, (("PROBE_SPEED", m["mesh_probe_speed"]), ("SAMPLES", m["mesh_probe_samples"]), ("SAMPLES_RESULT", m["mesh_probe_result"])))
        if built_for_print:
            self._set_measurement(fresh_mesh_built=1)

    def _cmd_probe(self, gcmd):
        if self._probe_base is None:
            raise gcmd.error("Plugins AD5X Z metrology: probe hook not initialized")
        m = self._measurement_status()
        x, y = self._gcode_xy()
        final_match = int(m["final_probe_armed"]) == 1 and self._print_state() == "printing" and abs(x - float(m["final_probe_x"])) <= 0.05 and abs(y - float(m["final_probe_y"])) <= 0.05
        self._set_measurement(final_probe_armed=0)
        if not final_match:
            self._probe_base(gcmd)
            return
        self._forward(PROBE_COMMAND, self._probe_base, gcmd, (("PROBE_SPEED", m["final_probe_speed"]), ("SAMPLES", m["final_probe_samples"]), ("SAMPLES_RESULT", m["final_probe_result"])))
        updates = {"final_probe_completed": 1}
        if int(m["fresh_mesh_built"]) == 1:
            updates["fresh_native_check_done"] = 1
        self._set_measurement(**updates)

    def _bed_mesh(self):
        obj = self.printer.lookup_object("bed_mesh", None)
        if obj is None or not hasattr(obj, "get_mesh") or not hasattr(obj, "set_mesh"):
            raise self.gcode.error("Plugins AD5X Z anchor: bed_mesh runtime is unavailable")
        return obj

    def _reconcile_owner(self, bed_mesh):
        if self.runtime_mesh is not None and bed_mesh.get_mesh() is not self.runtime_mesh:
            self._clear_state()

    def _require_no_fade(self, bed_mesh):
        sentinel = getattr(bed_mesh, "FADE_DISABLE", None)
        if sentinel is None or getattr(bed_mesh, "fade_end", None) != sentinel:
            raise self.gcode.error("Plugins AD5X Z anchor: bed_mesh fade must be disabled")

    def _parse_shift(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise self.gcode.error("Plugins AD5X Z anchor: SHIFT must be numeric")
        if not math.isfinite(value):
            raise self.gcode.error("Plugins AD5X Z anchor: SHIFT must be finite")
        if abs(value) >= self.max_abs_shift:
            raise self.gcode.error("Plugins AD5X Z anchor: SHIFT %.4f exceeds safety limit %.4f mm" % (value, self.max_abs_shift))
        return value

    def _clone(self, base, shift):
        required = ("get_probed_matrix", "get_mesh_params", "get_profile_name", "build_mesh")
        if not all(hasattr(base, name) for name in required):
            raise self.gcode.error("Plugins AD5X Z anchor: incompatible ZMesh API")
        points = base.get_probed_matrix()
        if not isinstance(points, list) or not points or not all(isinstance(row, list) and row for row in points):
            raise self.gcode.error("Plugins AD5X Z anchor: active mesh has no probed matrix")
        try:
            shifted = [[float(z) + shift for z in row] for row in points]
            runtime = type(base)(base.get_mesh_params().copy(), RUNTIME_PROFILE)
            runtime.build_mesh(shifted)
        except (TypeError, ValueError) as exc:
            raise self.gcode.error("Plugins AD5X Z anchor: invalid mesh data: %s" % exc)
        except Exception as exc:
            raise self.gcode.error("Plugins AD5X Z anchor: cannot construct runtime mesh: %s" % exc)
        return runtime, sum(len(row) for row in shifted)

    def cmd_APPLY(self, gcmd):
        shift = self._parse_shift(gcmd.get("SHIFT", None))
        bed_mesh = self._bed_mesh()
        self._reconcile_owner(bed_mesh)
        self._require_no_fade(bed_mesh)
        if self.runtime_mesh is not None:
            raise gcmd.error("Plugins AD5X Z anchor: runtime mesh already anchored; reset or replace the mesh first")
        base = bed_mesh.get_mesh()
        if base is None:
            raise gcmd.error("Plugins AD5X Z anchor: no active mesh to anchor")
        profile = base.get_profile_name() if hasattr(base, "get_profile_name") else ""
        if profile == RUNTIME_PROFILE:
            raise gcmd.error("Plugins AD5X Z anchor: refusing to anchor a runtime anchor mesh")
        runtime, count = self._clone(base, shift)
        bed_mesh.set_mesh(runtime)
        self.base_mesh = base
        self.runtime_mesh = runtime
        self.shift = shift
        self.base_profile = str(profile or "")
        self.point_count = count
        gcmd.respond_info("Plugins AD5X Z anchor applied: base=%s shift=%.4f mm points=%d transient=1" % (self.base_profile or "unnamed", shift, count))

    def cmd_RESET(self, gcmd):
        bed_mesh = self._bed_mesh()
        self._reconcile_owner(bed_mesh)
        if self.runtime_mesh is None:
            gcmd.respond_info("Plugins AD5X Z anchor reset: no active transient anchor")
            return
        bed_mesh.set_mesh(self.base_mesh)
        self._clear_state()
        gcmd.respond_info("Plugins AD5X Z anchor reset: pristine runtime mesh restored")

    def get_status(self, eventtime):
        bed_mesh = self.printer.lookup_object("bed_mesh", None)
        if bed_mesh is not None and hasattr(bed_mesh, "get_mesh"):
            self._reconcile_owner(bed_mesh)
        active = self.runtime_mesh is not None
        return {
            "active": active,
            "shift": self.shift if active else 0.0,
            "base_profile": self.base_profile,
            "runtime_profile": RUNTIME_PROFILE if active else "",
            "point_count": self.point_count,
            "persistent": False,
            "max_abs_shift": self.max_abs_shift,
            "metrology_hooks_ready": self.metrology_hooks_ready,
            "mesh_calibrate_hook": MESH_COMMAND if self.metrology_hooks_ready else "",
            "probe_hook": PROBE_COMMAND if self.metrology_hooks_ready else "",
        }

def load_config(config):
    return AD5XZMeshAnchor(config)
