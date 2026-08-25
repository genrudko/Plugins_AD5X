from __future__ import annotations
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
    def __init__(self): self.commands = {}
    def register_command(self, name, cb): self.commands[name] = cb
    def error(self, msg): return RuntimeError(msg)

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
        self.gcode = FakeGcode()
        self.objects = {"gcode": self.gcode, "bed_mesh": bed_mesh}
        self.handlers = {}
    def lookup_object(self, name, default=None): return self.objects.get(name, default)
    def register_event_handler(self, name, cb): self.handlers[name] = cb

class FakeConfig:
    def __init__(self, printer, limit=0.5): self.printer, self.limit = printer, limit
    def get_printer(self): return self.printer
    def getfloat(self, name, default, above=None): return self.limit

class FakeGcmd:
    def __init__(self, **params): self.params, self.messages = params, []
    def get(self, name, default=None): return self.params.get(name, default)
    def error(self, msg): return RuntimeError(msg)
    def respond_info(self, msg): self.messages.append(str(msg))

class MeshAnchorTests(unittest.TestCase):
    def make(self, *, fade=True, mesh=True, limit=0.5):
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

    def test_missing_mesh_is_rejected(self):
        anchor, _, _ = self.make(mesh=False)
        with self.assertRaisesRegex(RuntimeError, "no active mesh"):
            anchor.cmd_APPLY(FakeGcmd(SHIFT="0.1"))

    def test_source_has_no_persistence_or_user_offset_write(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertNotIn("save_profile", source)
        self.assertNotIn("BED_MESH_PROFILE", source)
        self.assertNotIn("SAVE_CONFIG", source)
        self.assertNotIn("SET_GCODE_OFFSET", source)

if __name__ == "__main__":
    unittest.main()
