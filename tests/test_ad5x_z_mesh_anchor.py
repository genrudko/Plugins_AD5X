from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "klipper" / "extras" / "ad5x_z_mesh_anchor.py"
spec = importlib.util.spec_from_file_location("ad5x_z_mesh_anchor", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

class FakeGcode:
    def __init__(self, printer=None): self.commands, self.printer = {}, printer
    def register_command(self, name, cb):
        if cb is None: return self.commands.pop(name, None)
        self.commands[name] = cb
    def error(self, msg): return RuntimeError(msg)
    def create_gcode_command(self, command, commandline, params): return FakeForwardGcmd(commandline)
    def run_script_from_command(self, script):
        target = self.printer.objects[mod.MEASUREMENT_OBJECT].variables
        for line in script.splitlines():
            fields = dict(token.split('=', 1) for token in line.split()[1:])
            target[fields['VARIABLE']] = ast.literal_eval(fields['VALUE'])

class FakeForwardGcmd:
    def __init__(self, line): self.line = line
    def get_raw_command_parameters(self): return self.line.split(' ', 1)[1] if ' ' in self.line else ''
    def error(self, msg): return RuntimeError(msg)

class FakeMeasurement:
    def __init__(self):
        self.variables = {'mesh_probe_speed':5.0,'mesh_probe_samples':3,'mesh_probe_result':'median','final_probe_speed':0.5,'final_probe_samples':3,'final_probe_result':'median','final_probe_armed':0,'final_probe_completed':0,'final_probe_x':0.0,'final_probe_y':0.0,'fresh_mesh_built':0,'fresh_native_check_done':0}

class FakeStatus:
    def __init__(self, require_eventtime=False, **status):
        self.status = status
        self.require_eventtime = require_eventtime
        self.eventtimes = []
    def get_status(self, eventtime):
        self.eventtimes.append(eventtime)
        if self.require_eventtime and eventtime is None:
            raise TypeError("status provider requires reactor eventtime")
        return self.status

class FakePrintStats:
    def __init__(self, state):
        self.state = state
        self.get_status_calls = 0
    def get_status(self, eventtime):
        self.get_status_calls += 1
        raise AssertionError("_print_state must not query PrintStats.get_status")

class FakeReactor:
    def __init__(self): self.now = 123.456
    def monotonic(self): return self.now

class FakeMesh:
    def __init__(self, params=None, name="auto"):
        self.params = dict(params or {"x_count": 2, "y_count": 2})
        self.name = name
        self.matrix = [[-2.00, -1.98], [-2.02, -2.01]]
    def get_probed_matrix(self): return [row[:] for row in self.matrix]
    def get_mesh_params(self): return dict(self.params)
    def get_profile_name(self): return self.name
    def build_mesh(self, matrix): self.matrix = [row[:] for row in matrix]

class FakeBedMesh:
    FADE_DISABLE = 0x7FFFFFFF
    def __init__(self, mesh=None, fade=True):
        self.mesh = mesh
        self.fade_end = self.FADE_DISABLE if fade else 10.0
        self.set_history = []
    def get_mesh(self): return self.mesh
    def set_mesh(self, mesh):
        self.mesh = mesh
        self.set_history.append(mesh)

class FakePrinter:
    def __init__(self, bed_mesh):
        self.gcode = FakeGcode(self)
        self.reactor = FakeReactor()
        self.objects = {"gcode": self.gcode, "bed_mesh": bed_mesh}
        self.handlers = {}
    def lookup_object(self, name, default=None): return self.objects.get(name, default)
    def get_reactor(self): return self.reactor
    def register_event_handler(self, name, cb): self.handlers[name] = cb
    def config_error(self, msg): return RuntimeError(msg)

class FakeConfig:
    def __init__(self, printer, limit=0.31): self.printer, self.limit = printer, limit
    def get_printer(self): return self.printer
    def getfloat(self, name, default, above=None): return self.limit

class FakeGcmd:
    def __init__(self, **params): self.params, self.messages = params, []
    def get(self, name, default=None): return self.params.get(name, default)
    def error(self, msg): return RuntimeError(msg)
    def respond_info(self, msg): self.messages.append(str(msg))

class MeshAnchorTests(unittest.TestCase):
    def make(self, *, fade=True, mesh=True, limit=0.31):
        base = FakeMesh() if mesh else None
        bed = FakeBedMesh(base, fade=fade)
        printer = FakePrinter(bed)
        anchor = mod.AD5XZMeshAnchor(FakeConfig(printer, limit))
        return anchor, bed, base

    def test_apply_shifts_runtime_copy_without_mutating_base(self):
        anchor, bed, base = self.make()
        original = base.get_probed_matrix()
        cmd = FakeGcmd(SHIFT="0.1700")
        anchor.cmd_APPLY(cmd)
        self.assertIsNot(bed.get_mesh(), base)
        self.assertEqual(base.get_probed_matrix(), original)
        self.assertEqual(bed.get_mesh().get_profile_name(), mod.RUNTIME_PROFILE)
        expected = [[z + 0.17 for z in row] for row in original]
        self.assertEqual(bed.get_mesh().get_probed_matrix(), expected)
        state = anchor.get_status(None)
        self.assertTrue(state["active"])
        self.assertAlmostEqual(state["shift"], 0.17)
        self.assertEqual(state["base_profile"], "auto")
        self.assertFalse(state["persistent"])

    def test_reset_restores_original_mesh_identity(self):
        anchor, bed, base = self.make()
        anchor.cmd_APPLY(FakeGcmd(SHIFT="0.1375"))
        anchor.cmd_RESET(FakeGcmd())
        self.assertIs(bed.get_mesh(), base)
        self.assertFalse(anchor.get_status(None)["active"])

    def test_virtual_sdcard_reset_restores_pristine_mesh_before_next_job(self):
        anchor, bed, base = self.make()
        self.assertIn("virtual_sdcard:reset_file", anchor.printer.handlers)
        anchor.cmd_APPLY(FakeGcmd(SHIFT="0.1375"))
        anchor.printer.handlers["virtual_sdcard:reset_file"]()
        self.assertIs(bed.get_mesh(), base)
        self.assertFalse(anchor.get_status(None)["active"])

    def test_virtual_sdcard_reset_does_not_resurrect_superseded_mesh(self):
        anchor, bed, _ = self.make()
        anchor.cmd_APPLY(FakeGcmd(SHIFT="0.1375"))
        newer = FakeMesh(name="fresh")
        bed.set_mesh(newer)
        anchor.printer.handlers["virtual_sdcard:reset_file"]()
        self.assertIs(bed.get_mesh(), newer)
        self.assertFalse(anchor.get_status(None)["active"])

    def test_double_apply_is_rejected_without_accumulation(self):
        anchor, bed, _ = self.make()
        anchor.cmd_APPLY(FakeGcmd(SHIFT="0.1700"))
        first = bed.get_mesh().get_probed_matrix()
        with self.assertRaisesRegex(RuntimeError, "already anchored"):
            anchor.cmd_APPLY(FakeGcmd(SHIFT="0.0100"))
        self.assertEqual(bed.get_mesh().get_probed_matrix(), first)

    def test_external_mesh_replacement_supersedes_anchor(self):
        anchor, bed, _ = self.make()
        anchor.cmd_APPLY(FakeGcmd(SHIFT="0.1700"))
        newer = FakeMesh(name="fresh")
        bed.set_mesh(newer)
        self.assertFalse(anchor.get_status(None)["active"])
        anchor.cmd_RESET(FakeGcmd())
        self.assertIs(bed.get_mesh(), newer)

    def test_fade_enabled_is_rejected(self):
        anchor, _, _ = self.make(fade=False)
        with self.assertRaisesRegex(RuntimeError, "fade must be disabled"):
            anchor.cmd_APPLY(FakeGcmd(SHIFT="0.1700"))

    def test_shift_safety_limit_is_enforced(self):
        anchor, _, _ = self.make(limit=0.2)
        with self.assertRaisesRegex(RuntimeError, "exceeds safety limit"):
            anchor.cmd_APPLY(FakeGcmd(SHIFT="0.201"))

    def test_shift_safety_boundary_is_exclusive(self):
        anchor, _, _ = self.make(limit=0.31)
        with self.assertRaisesRegex(RuntimeError, "exceeds safety limit"):
            anchor.cmd_APPLY(FakeGcmd(SHIFT="0.3100"))

    def test_missing_mesh_is_rejected(self):
        anchor, _, _ = self.make(mesh=False)
        with self.assertRaisesRegex(RuntimeError, "no active mesh"):
            anchor.cmd_APPLY(FakeGcmd(SHIFT="0.1"))

    def prepare_metrology_runtime(self, state="printing"):
        anchor, _, _ = self.make()
        printer = anchor.printer
        measurement = FakeMeasurement()
        printer.objects[mod.MEASUREMENT_OBJECT] = measurement
        printer.objects["print_stats"] = FakePrintStats(state)
        printer.objects["gcode_move"] = FakeStatus(require_eventtime=True, gcode_position=[100.0, 100.0, 5.0, 0.0])
        seen = {"mesh": [], "probe": []}
        printer.gcode.commands[mod.MESH_COMMAND] = lambda g: seen["mesh"].append(g.get_raw_command_parameters())
        printer.gcode.commands[mod.PROBE_COMMAND] = lambda g: seen["probe"].append(g.get_raw_command_parameters())
        printer.handlers["klippy:ready"]()
        return anchor, measurement, seen

    def test_print_state_uses_direct_runtime_state_without_status_side_effects(self):
        anchor, _, _ = self.prepare_metrology_runtime()
        print_stats = anchor.printer.objects["print_stats"]
        self.assertEqual(anchor._print_state(), "printing")
        self.assertEqual(print_stats.get_status_calls, 0)

    def test_gcode_position_query_uses_reactor_eventtime(self):
        anchor, _, _ = self.prepare_metrology_runtime()
        gcode_move = anchor.printer.objects["gcode_move"]
        self.assertEqual(anchor._gcode_xy(), (100.0, 100.0))
        self.assertEqual(gcode_move.eventtimes[-1], anchor.printer.reactor.now)
        self.assertNotIn(None, gcode_move.eventtimes)

    def test_ready_interposes_only_after_base_commands_exist(self):
        anchor, measurement, seen = self.prepare_metrology_runtime()
        state = anchor.get_status(None)
        self.assertTrue(state["metrology_hooks_ready"])
        self.assertEqual(state["mesh_calibrate_hook"], "_BED_MESH_CALIBRATE")
        self.assertEqual(state["probe_hook"], "PROBE")
        anchor.printer.gcode.commands[mod.MESH_COMMAND](FakeForwardGcmd("_BED_MESH_CALIBRATE ADAPTIVE=1 PROBE_SPEED=9"))
        self.assertEqual(seen["mesh"], ["ADAPTIVE=1 PROBE_SPEED=9 PROBE_SPEED=5.0 SAMPLES=3 SAMPLES_RESULT=median"])
        self.assertEqual(measurement.variables["fresh_mesh_built"], 1)

    def test_idle_zmod_mesh_is_exact_passthrough(self):
        anchor, measurement, seen = self.prepare_metrology_runtime(state="standby")
        anchor.printer.gcode.commands[mod.MESH_COMMAND](FakeForwardGcmd("_BED_MESH_CALIBRATE PROFILE=auto PROBE_SPEED=9"))
        self.assertEqual(seen["mesh"], ["PROFILE=auto PROBE_SPEED=9"])
        self.assertEqual(measurement.variables["fresh_mesh_built"], 0)

    def test_explicit_adz_mesh_calibrate_forces_policy_while_idle(self):
        anchor, measurement, seen = self.prepare_metrology_runtime(state="standby")
        anchor.printer.gcode.commands[mod.COMMAND_CALIBRATE](FakeForwardGcmd("ADZ_MESH_CALIBRATE PROFILE=auto PROBE_SPEED=9"))
        self.assertEqual(seen["mesh"], ["PROFILE=auto PROBE_SPEED=9 PROBE_SPEED=5.0 SAMPLES=3 SAMPLES_RESULT=median"])
        self.assertEqual(measurement.variables["fresh_mesh_built"], 0)

    def test_explicit_adz_mesh_calibrate_is_rejected_while_printing(self):
        anchor, _, _ = self.prepare_metrology_runtime(state="printing")
        with self.assertRaisesRegex(RuntimeError, "requires an idle printer"):
            anchor.printer.gcode.commands[mod.COMMAND_CALIBRATE](FakeForwardGcmd("ADZ_MESH_CALIBRATE PROFILE=auto"))

    def test_final_probe_precision_is_one_shot_and_fresh_completion_is_recorded(self):
        anchor, measurement, seen = self.prepare_metrology_runtime()
        measurement.variables.update(final_probe_armed=1, final_probe_x=100.0, final_probe_y=100.0, fresh_mesh_built=1)
        anchor.printer.gcode.commands[mod.PROBE_COMMAND](FakeForwardGcmd("PROBE SAMPLES=1"))
        self.assertEqual(seen["probe"], ["SAMPLES=1 PROBE_SPEED=0.5 SAMPLES=3 SAMPLES_RESULT=median"])
        self.assertEqual(measurement.variables["final_probe_armed"], 0)
        self.assertEqual(measurement.variables["final_probe_completed"], 1)
        self.assertEqual(measurement.variables["fresh_native_check_done"], 1)
        anchor.printer.gcode.commands[mod.PROBE_COMMAND](FakeForwardGcmd("PROBE PROBE_SPEED=7"))
        self.assertEqual(seen["probe"][-1], "PROBE_SPEED=7")

    def test_ready_fails_closed_without_zmod_mesh_delegate(self):
        anchor, _, _ = self.make()
        anchor.printer.objects[mod.MEASUREMENT_OBJECT] = FakeMeasurement()
        anchor.printer.gcode.commands[mod.PROBE_COMMAND] = lambda g: None
        with self.assertRaisesRegex(RuntimeError, "_BED_MESH_CALIBRATE unavailable"):
            anchor.printer.handlers["klippy:ready"]()
        self.assertFalse(anchor.metrology_hooks_ready)

    def test_ready_without_v6_measurement_policy_leaves_commands_untouched(self):
        anchor, _, _ = self.make()
        mesh_base = lambda g: None
        probe_base = lambda g: None
        anchor.printer.gcode.commands[mod.MESH_COMMAND] = mesh_base
        anchor.printer.gcode.commands[mod.PROBE_COMMAND] = probe_base
        anchor.printer.handlers["klippy:ready"]()
        self.assertFalse(anchor.metrology_hooks_ready)
        self.assertIs(anchor.printer.gcode.commands[mod.MESH_COMMAND], mesh_base)
        self.assertIs(anchor.printer.gcode.commands[mod.PROBE_COMMAND], probe_base)

    def test_source_has_no_persistence_or_user_offset_write(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertNotIn("save_profile", source)
        self.assertNotIn("BED_MESH_PROFILE", source)
        self.assertNotIn("SAVE_CONFIG", source)
        self.assertNotIn("SET_GCODE_OFFSET", source)

    def test_runtime_status_exposes_loaded_python_source_identity(self):
        anchor, _, _ = self.make()
        loaded = anchor.get_status(None)["loaded_source_sha256"]
        self.assertEqual(len(loaded), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in loaded))

if __name__ == "__main__":
    unittest.main()
