from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZER_PATH = ROOT / "installer" / "z_calibration_productization.py"
POLICY_PATH = ROOT / "z_calibration_rc_policy.cfg"
RUNTIME_HELPER = ROOT / "installer" / "z_calibration_runtime.sh"
WRAPPER = ROOT / "z_calibration.cfg"

_spec = importlib.util.spec_from_file_location("zcal_productization", PRODUCTIZER_PATH)
assert _spec and _spec.loader
product = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(product)


def hook_text(commands: list[str]) -> str:
    return (
        "[gcode_macro _USER_START_PRINT]\n"
        "gcode:\n"
        + "".join(f"    {command}\n" for command in commands)
    )


def live_payload(commands: list[str], *, mesh_test: int = 2, cc_enabled: int | None = 1, policy: bool = False, clear: str | None = None, disable_priming: int = 0, prime_delegate: str | None = None) -> str:
    variables = {"mesh_test": mesh_test, "load_zoffset": 1, "print_leveling": 0, "disable_priming": disable_priming}
    if cc_enabled is not None: variables["cc_enabled"] = cc_enabled
    if clear is not None: variables["clear"] = clear
    if prime_delegate is not None: variables[product.PRIME_DELEGATE_VARIABLE] = prime_delegate
    settings = {"gcode_macro _user_start_print": {"gcode": "\n".join(commands)}}
    if policy:
        settings["gcode_macro _adz_prime_gate"] = {"variable_fresh_finalized": "0"}
        settings["gcode_macro _adz_measurement_policy"] = {"variable_policy_id": f'"{product.MEASUREMENT_POLICY_ID}"', "variable_mesh_probe_speed": "5.0", "variable_mesh_probe_samples": "3", "variable_mesh_probe_result": '"median"', "variable_final_probe_speed": "0.5", "variable_final_probe_samples": "3", "variable_final_probe_result": '"median"', "variable_final_probe_armed": "0", "variable_final_probe_completed": "0", "variable_fresh_mesh_built": "0", "variable_fresh_native_check_done": "0"}
        settings["gcode_macro load_cell_tare"] = {"variable_adz_reuse_armed": "0"}
        settings["gcode_macro _bed_mesh_calibrate"] = {"rename_existing": "_ADZ_BED_MESH_CALIBRATE_BASE"}
        settings["gcode_macro probe"] = {"rename_existing": "_ADZ_PROBE_BASE"}
        settings["gcode_macro _prepare_print"] = {"rename_existing": "_ADZ_PREPARE_PRINT_BASE"}
    status = {"configfile": {"settings": settings}, "save_variables": {"variables": variables}}
    if policy:
        status["gcode_macro _AD5X_Z_SAVED_CHECK_POLICY"] = {"policy_id": product.POLICY_ID, "max_auto_alignment": product.POLICY_MAX_AUTO}
        status["gcode_macro _ADZ_SAVED_CHECK_POLICY"] = {"policy_id": product.POLICY_ID, "max_auto_alignment": product.POLICY_MAX_AUTO, "anchor_policy_id": product.ANCHOR_POLICY_ID, "max_machine_anchor": product.MAX_MACHINE_ANCHOR, "machine_anchor_finalized": 0}
        status["gcode_macro _ADZ_MEASUREMENT_POLICY"] = {"policy_id": product.MEASUREMENT_POLICY_ID, "mesh_probe_speed": 5.0, "mesh_probe_samples": 3, "mesh_probe_result": "median", "final_probe_speed": 0.5, "final_probe_samples": 3, "final_probe_result": "median", "final_probe_armed": 0, "final_probe_completed": 0, "fresh_mesh_built": 0, "fresh_native_check_done": 0}
        status["gcode_macro LOAD_CELL_TARE"] = {"adz_reuse_armed": 0}
        status["ad5x_z_mesh_anchor"] = {"active": False, "shift": 0.0, "persistent": False, "max_abs_shift": product.MAX_MACHINE_ANCHOR}
    return json.dumps({"result": {"status": status}})


class Fixture:
    def __init__(self, root: Path, *, stock: list[str] | None = None, user: list[str] | None = None) -> None:
        self.root = root
        self.printer = root / "printer.cfg"
        self.stock = root / "stock.cfg"
        self.user = root / "user.cfg"
        includes: list[str] = []
        if stock is not None:
            self.stock.write_text(hook_text(stock), encoding="utf-8")
            includes.append("[include stock.cfg]")
        if user is not None:
            self.user.write_text(hook_text(user), encoding="utf-8")
            includes.append("[include user.cfg]")
        self.printer.write_text("\n".join(includes) + "\n", encoding="utf-8")
        self.policy = root / "canonical-policy.cfg"
        self.policy.write_bytes(POLICY_PATH.read_bytes())
        self.policy_dest = root / "generated" / "zcal_owner_rc.cfg"
        self.variables = root / "variables.cfg"
        self.variables.write_text(
            "[Variables]\n"
            "mesh_test = 2\n"
            "cc_enabled = 1\n"
            "clear = '_CLEAR2'\n"
            "disable_priming = 0\n"
            "unrelated = 77\n",
            encoding="utf-8",
        )
        self.state = root / "state" / "zcal-rc-productization"
        self.backups = root / "backups"
        self.backups.mkdir()

    def plan(self, commands: list[str], *, mesh_test: int = 2, cc_enabled: int | None = 1):
        values = {}
        for line in self.variables.read_text(encoding="utf-8").splitlines():
            if "=" not in line: continue
            k, raw = (x.strip() for x in line.split("=", 1))
            try: values[k] = ast.literal_eval(raw)
            except (ValueError, SyntaxError): pass
        return product.build_preflight_plan(
            self.printer, self.policy, self.policy_dest, self.variables, self.state, self.backups,
            live_payload(commands, mesh_test=mesh_test, cc_enabled=cc_enabled, clear=values.get("clear"), disable_priming=int(values.get("disable_priming", 0)), prime_delegate=values.get(product.PRIME_DELEGATE_VARIABLE)),
        )


class ZCalibrationProductizationTests(unittest.TestCase):
    def test_stock_empty_extension_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=None)
            plan = fx.plan([])
            self.assertEqual(Path(plan["owner_path"]), fx.stock.resolve())
            product.apply_plan(plan, fx.policy)
            self.assertEqual(product.hook_commands(fx.stock), [product.GUARD])

    def test_cc_only_winning_owner_is_resolved_despite_stock_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC])
            plan = fx.plan([product.CC])
            self.assertEqual(Path(plan["owner_path"]), fx.user.resolve())
            product.apply_plan(plan, fx.policy)
            self.assertEqual(product.hook_commands(fx.user), [product.CC, product.GUARD])
            self.assertEqual(product.hook_commands(fx.stock), [])

    def test_already_patched_owned_chain_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC])
            first = fx.plan([product.CC])
            product.apply_plan(first, fx.policy)
            owner_before = fx.user.read_bytes()
            variables_before = fx.variables.read_bytes()
            second = fx.plan([product.CC, product.GUARD], mesh_test=3, cc_enabled=0)
            product.apply_plan(second, fx.policy)
            self.assertEqual(fx.user.read_bytes(), owner_before)
            self.assertEqual(fx.variables.read_bytes(), variables_before)

    def test_foreign_hook_body_fails_closed_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=None, user=["M117 foreign"])
            before = fx.user.read_bytes()
            with self.assertRaises(product.ProductizationError):
                fx.plan(["M117 foreign"])
            self.assertEqual(fx.user.read_bytes(), before)
            self.assertFalse(fx.state.exists())
            self.assertFalse(fx.policy_dest.exists())

    def test_duplicate_guard_without_manifest_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=None, user=[product.CC, product.GUARD, product.GUARD])
            with self.assertRaisesRegex(product.ProductizationError, "duplicate guard"):
                fx.plan([product.CC, product.GUARD, product.GUARD])

    def test_owned_duplicate_guard_repairs_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=None, user=[product.CC])
            product.apply_plan(fx.plan([product.CC]), fx.policy)
            expected = fx.user.read_bytes()
            text = fx.user.read_text(encoding="utf-8")
            fx.user.write_text(
                text.replace(
                    f"    {product.GUARD}\n",
                    f"    {product.GUARD}\n    {product.GUARD}\n",
                ),
                encoding="utf-8",
            )
            plan = fx.plan([product.CC, product.GUARD, product.GUARD], mesh_test=3, cc_enabled=0)
            product.apply_plan(plan, fx.policy)
            self.assertEqual(fx.user.read_bytes(), expected)
            self.assertEqual(product.hook_commands(fx.user).count(product.GUARD), 1)

    def test_missing_physical_owner_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=None, user=None)
            with self.assertRaisesRegex(product.ProductizationError, "owner not found"):
                fx.plan([product.CC])

    def test_duplicate_physical_definitions_can_be_proven_by_effective_body(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC])
            resolved = product.resolve_owner(fx.printer, [product.CC])
            self.assertEqual(Path(resolved["owner_path"]), fx.user.resolve())

    def test_duplicate_identical_physical_definitions_are_ambiguous_without_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[product.CC], user=[product.CC])
            with self.assertRaisesRegex(product.ProductizationError, "ambiguous"):
                fx.plan([product.CC])

    def test_update_adopts_pre_prime_ownership_from_old_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC])
            product.apply_plan(fx.plan([product.CC]), fx.policy)
            manifest_path = fx.state / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for key in ("original_clear", "original_disable_priming", "original_prime_delegate"):
                manifest.pop(key, None)
            manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            fx.variables.write_text("[Variables]\nmesh_test = 3\ncc_enabled = 0\nclear = '_CLEAR2'\ndisable_priming = 0\nunrelated = 77\n", encoding="utf-8")
            plan = fx.plan([product.CC, product.GUARD], mesh_test=3, cc_enabled=0)
            self.assertEqual(plan["original_clear"]["value"], "_CLEAR2")
            product.apply_plan(plan, fx.policy)
            variables = fx.variables.read_text(encoding="utf-8")
            self.assertIn("clear = '_ADZ_PRIME_GATE'", variables)
            self.assertIn("adz_prime_delegate = '_CLEAR2'", variables)
            migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(migrated["original_clear"]["value"], "_CLEAR2")

    def test_install_and_update_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC])
            product.apply_plan(fx.plan([product.CC]), fx.policy)
            first_hook = fx.user.read_bytes()
            first_policy = fx.policy_dest.read_bytes()

            fx.policy.write_bytes(first_policy + b"\n# compatible update\n")
            product.apply_plan(
                fx.plan([product.CC, product.GUARD], mesh_test=3, cc_enabled=0),
                fx.policy,
            )
            updated_hook = fx.user.read_bytes()
            updated_policy = fx.policy_dest.read_bytes()
            self.assertEqual(updated_hook, first_hook)
            self.assertNotEqual(updated_policy, first_policy)

            product.apply_plan(
                fx.plan([product.CC, product.GUARD], mesh_test=3, cc_enabled=0),
                fx.policy,
            )
            self.assertEqual(fx.user.read_bytes(), updated_hook)
            self.assertEqual(fx.policy_dest.read_bytes(), updated_policy)

    def test_update_preserves_user_selected_prime_delegate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC])
            product.apply_plan(fx.plan([product.CC]), fx.policy)
            variables = fx.variables.read_text(encoding="utf-8")
            variables = variables.replace("adz_prime_delegate = '_CLEAR2'", "adz_prime_delegate = '_CLEAR4'")
            fx.variables.write_text(variables, encoding="utf-8")

            plan = fx.plan([product.CC, product.GUARD], mesh_test=3, cc_enabled=0)
            self.assertEqual(plan["desired_prime_delegate"], "_CLEAR4")
            product.apply_plan(plan, fx.policy)

            updated = fx.variables.read_text(encoding="utf-8")
            self.assertIn("adz_prime_delegate = '_CLEAR4'", updated)
            self.assertIn("clear = '_ADZ_PRIME_GATE'", updated)

    def test_successful_update_snapshot_can_restore_previous_owned_version(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fx = Fixture(root, stock=[], user=[product.CC])
            product.apply_plan(fx.plan([product.CC]), fx.policy)
            previous_policy = fx.policy_dest.read_bytes()
            previous_variables = fx.variables.read_bytes()
            previous_manifest = (fx.state / "manifest.json").read_bytes()

            fx.policy.write_bytes(previous_policy + b"\n# next-version-marker\n")
            plan = fx.plan([product.CC, product.GUARD], mesh_test=3, cc_enabled=0)
            backup = root / "successful-update-previous"
            product.transaction_snapshot(plan, backup)
            product.apply_plan(plan, fx.policy)
            self.assertNotEqual(fx.policy_dest.read_bytes(), previous_policy)

            product.transaction_restore(plan, backup)
            self.assertEqual(fx.policy_dest.read_bytes(), previous_policy)
            self.assertEqual(fx.variables.read_bytes(), previous_variables)
            self.assertEqual((fx.state / "manifest.json").read_bytes(), previous_manifest)

    def test_parked_refresh_snapshot_preserves_stale_generated_policy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fx = Fixture(root, stock=[], user=[product.CC])
            pristine_hook = fx.user.read_bytes()
            product.apply_plan(fx.plan([product.CC]), fx.policy)

            fx.user.write_bytes(pristine_hook)
            stale_policy = b"# parked-stale-generated-policy\n"
            fx.policy_dest.write_bytes(stale_policy)
            plan = fx.plan([product.CC], mesh_test=3, cc_enabled=0)
            self.assertEqual(plan["baseline_source"], "manifest")

            backup = root / "parked-pre-update"
            product.transaction_snapshot(plan, backup)
            fx.policy_dest.unlink()
            product.apply_plan(plan, fx.policy)
            self.assertEqual(fx.policy_dest.read_bytes(), fx.policy.read_bytes())

            product.transaction_restore(plan, backup)
            self.assertEqual(fx.user.read_bytes(), pristine_hook)
            self.assertEqual(fx.policy_dest.read_bytes(), stale_policy)

    def test_repair_recovers_partial_owned_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC])
            original_hook = fx.user.read_bytes()
            product.apply_plan(fx.plan([product.CC]), fx.policy)
            expected_hook = fx.user.read_bytes()

            fx.policy_dest.unlink()
            fx.user.write_bytes(original_hook)
            fx.variables.write_text(
                "[Variables]\nmesh_test = 2\ncc_enabled = 1\nunrelated = 77\n",
                encoding="utf-8",
            )
            plan = fx.plan([product.CC, product.GUARD], mesh_test=3, cc_enabled=0)
            product.apply_plan(plan, fx.policy)
            self.assertEqual(fx.user.read_bytes(), expected_hook)
            self.assertEqual(fx.policy_dest.read_bytes(), fx.policy.read_bytes())
            variables = fx.variables.read_text(encoding="utf-8")
            self.assertIn("mesh_test = 3", variables)
            self.assertIn("cc_enabled = 0", variables)
            self.assertIn("unrelated = 77", variables)

    def test_transaction_restore_covers_each_mutation_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fx = Fixture(root, stock=[], user=[product.CC])
            plan = fx.plan([product.CC])
            original_hook = fx.user.read_bytes()
            original_vars = fx.variables.read_bytes()

            for boundary in ("hook", "policy", "variables", "state"):
                backup = root / f"txn-{boundary}"
                product.transaction_snapshot(plan, backup)
                fx.user.write_text(hook_text([product.CC, product.GUARD]), encoding="utf-8")
                if boundary in {"policy", "variables", "state"}:
                    fx.policy_dest.parent.mkdir(parents=True, exist_ok=True)
                    fx.policy_dest.write_text("partial", encoding="utf-8")
                if boundary in {"variables", "state"}:
                    fx.variables.write_text("[Variables]\nmesh_test = 3\n", encoding="utf-8")
                if boundary == "state":
                    fx.state.mkdir(parents=True, exist_ok=True)
                    (fx.state / "partial").write_text("x", encoding="utf-8")

                product.transaction_restore(plan, backup)
                self.assertEqual(fx.user.read_bytes(), original_hook, boundary)
                self.assertEqual(fx.variables.read_bytes(), original_vars, boundary)
                self.assertFalse(fx.policy_dest.exists(), boundary)
                self.assertFalse(fx.state.exists(), boundary)

    def test_uninstall_restores_hook_byte_for_byte_and_prior_settings(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC])
            original_hook = fx.user.read_bytes()
            original_vars = fx.variables.read_bytes()
            product.apply_plan(fx.plan([product.CC]), fx.policy)
            product.uninstall(fx.state, fx.variables)
            self.assertEqual(fx.user.read_bytes(), original_hook)
            self.assertEqual(fx.variables.read_bytes(), original_vars)
            self.assertFalse(fx.policy_dest.exists())
            self.assertFalse(fx.state.exists())

    def test_uninstall_refuses_foreign_post_install_hook(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC])
            product.apply_plan(fx.plan([product.CC]), fx.policy)
            fx.user.write_text(hook_text([product.CC, product.GUARD, "M117 owner edit"]), encoding="utf-8")
            with self.assertRaisesRegex(product.ProductizationError, "foreign hook"):
                product.uninstall(fx.state, fx.variables)
            self.assertTrue(fx.state.exists())

    def test_legacy_manual_rc_is_adopted_only_with_compatible_backup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fx = Fixture(root, stock=[], user=[product.CC])
            pristine = fx.user.read_bytes()
            patched = product._patch_baseline(pristine)
            fx.user.write_bytes(patched)
            fx.variables.write_text(
                "[Variables]\nmesh_test = 3\ncc_enabled = 0\nunrelated = 77\n",
                encoding="utf-8",
            )
            fx.policy_dest.parent.mkdir(parents=True, exist_ok=True)
            fx.policy_dest.write_bytes(fx.policy.read_bytes())

            legacy = fx.backups / "zcal-rc-20260818-003457"
            legacy.mkdir()
            (legacy / "user.cfg").write_bytes(pristine)
            (legacy / "old_mesh_test").write_text("2\n", encoding="ascii")
            (legacy / "old_cc_enabled").write_text("1\n", encoding="ascii")

            plan = fx.plan([product.CC, product.GUARD], mesh_test=3, cc_enabled=0)
            self.assertEqual(plan["baseline_source"], "legacy_backup")
            product.apply_plan(plan, fx.policy)
            product.uninstall(fx.state, fx.variables)
            self.assertEqual(fx.user.read_bytes(), pristine)
            variables = fx.variables.read_text(encoding="utf-8")
            self.assertIn("mesh_test = 2", variables)
            self.assertIn("cc_enabled = 1", variables)
            self.assertIn("unrelated = 77", variables)
            self.assertFalse(fx.policy_dest.exists())

    def test_unowned_already_patched_state_without_provenance_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC, product.GUARD])
            fx.variables.write_text("[Variables]\nmesh_test = 3\ncc_enabled = 0\n", encoding="utf-8")
            fx.policy_dest.parent.mkdir(parents=True, exist_ok=True)
            fx.policy_dest.write_bytes(fx.policy.read_bytes())
            with self.assertRaisesRegex(product.ProductizationError, "legacy RC backup"):
                fx.plan([product.CC, product.GUARD], mesh_test=3, cc_enabled=0)

    def test_foreign_generated_policy_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC])
            fx.policy_dest.parent.mkdir(parents=True, exist_ok=True)
            fx.policy_dest.write_text("foreign", encoding="utf-8")
            with self.assertRaisesRegex(product.ProductizationError, "foreign"):
                fx.plan([product.CC])
            self.assertEqual(fx.policy_dest.read_text(encoding="utf-8"), "foreign")

    def test_unrelated_ifs_runtime_file_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fx = Fixture(root, stock=[], user=[product.CC])
            unrelated = root / "ifs-runtime.db"
            unrelated.write_bytes(b"IFS-STATE")
            before = hashlib.sha256(unrelated.read_bytes()).hexdigest()
            product.apply_plan(fx.plan([product.CC]), fx.policy)
            product.uninstall(fx.state, fx.variables)
            after = hashlib.sha256(unrelated.read_bytes()).hexdigest()
            self.assertEqual(after, before)

    def test_productization_path_contains_no_motion_or_worktree_mutation(self) -> None:
        policy = POLICY_PATH.read_text(encoding="utf-8")
        wrapper = WRAPPER.read_text(encoding="utf-8")
        helper = RUNTIME_HELPER.read_text(encoding="utf-8")
        productizer = PRODUCTIZER_PATH.read_text(encoding="utf-8")

        command_lines = [
            line.strip()
            for line in policy.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertFalse(any(line.startswith(("PROBE", "G0 ", "G1 ", "SET_GCODE_OFFSET")) for line in command_lines))
        self.assertNotIn("[gcode_macro _USER_START_PRINT]", wrapper)
        self.assertNotIn("git checkout", helper + productizer)
        self.assertNotIn("git reset", helper + productizer)

    def test_live_verify_requires_exact_chain_and_rc_settings(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(Path(td), stock=[], user=[product.CC])
            product.apply_plan(fx.plan([product.CC]), fx.policy)
            product.verify_live(
                live_payload([product.CC, product.GUARD], mesh_test=3, cc_enabled=0, policy=True, clear=product.PRIME_GATE, prime_delegate="_CLEAR2"),
                fx.state,
            )
            with self.assertRaises(product.ProductizationError):
                product.verify_live(
                    live_payload([product.CC], mesh_test=3, cc_enabled=0, policy=True, clear=product.PRIME_GATE, prime_delegate="_CLEAR2"),
                    fx.state,
                )


if __name__ == "__main__":
    unittest.main()
