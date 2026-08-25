# Plugins AD5X - transient common-mode Z anchor for the active bed mesh.
# Never persists the shifted copy and never writes the user gcode Z offset.
import math

RUNTIME_PROFILE = "adz_runtime_anchor"
COMMAND_APPLY = "ADZ_MESH_ANCHOR"
COMMAND_RESET = "ADZ_MESH_ANCHOR_RESET"

class AD5XZMeshAnchor:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.max_abs_shift = config.getfloat("max_abs_shift", 0.5, above=0.0)
        self.gcode = self.printer.lookup_object("gcode")
        self.gcode.register_command(COMMAND_APPLY, self.cmd_APPLY)
        self.gcode.register_command(COMMAND_RESET, self.cmd_RESET)
        self._clear_state()
        self.printer.register_event_handler("klippy:disconnect", self._disconnect)
        self.printer.register_event_handler("klippy:shutdown", self._disconnect)

    def _clear_state(self):
        self.base_mesh = None
        self.runtime_mesh = None
        self.shift = 0.0
        self.base_profile = ""
        self.point_count = 0

    def _disconnect(self, *args):
        self._clear_state()

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
        if abs(value) > self.max_abs_shift:
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
        }

def load_config(config):
    return AD5XZMeshAnchor(config)
