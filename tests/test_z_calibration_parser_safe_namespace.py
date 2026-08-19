from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZER = ROOT / "installer" / "z_calibration_productization.py"
POLICY = ROOT / "z_calibration_rc_policy.cfg"

_spec = importlib.util.spec_from_file_location("zcal_productization_adz", PRODUCTIZER)
assert _spec and _spec.loader
product = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(product)


def hook(commands: list[str]) -> str:
    return (
        "[gcode_macro _USER_START_PRINT]\n"
        "gcode:\n"
        + "".join(f"    {command}\n" for command in commands)
    )


def payload(commands: list[str]) -> str:
    return json.dumps(
        {
            "result": {
                "status": {
                    "configfile": {
                        "settings": {
                            "gcode_macro _user_start_print": {
                                "gcode": "\n".join(commands)
                            }
                        }
                    },
                    "save_variables": {
                        "variables": {
                            "mesh_test": 3,
                            "cc_enabled": 0,
                            "load_zoffset": 1,
                            "print_leveling": 0,
                        }
                    },
                }
            }
        }
    )


class ParserSafeNamespaceMigrationTests(unittest.TestCase):
    def test_owned_legacy_guard_is_migrated_to_adz_without_losing_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            printer = root / "printer.cfg"
            owner = root / "user.cfg"
            variables = root / "variables.cfg"
            policy_dest = root / "generated" / "zcal_owner_rc.cfg"
            state = root / "state" / "zcal-rc-productization"
            backups = root / "backups"
            backups.mkdir()

            printer.write_text("[include user.cfg]\n", encoding="utf-8")
            owner.write_text(hook([product.CC]), encoding="utf-8")
            variables.write_text(
                "[Variables]\nmesh_test = 3\ncc_enabled = 0\n",
                encoding="utf-8",
            )

            first = product.build_preflight_plan(
                printer,
                POLICY,
                policy_dest,
                variables,
                state,
                backups,
                payload([product.CC]),
            )
            product.apply_plan(first, POLICY)
            self.assertEqual(
                product.hook_commands(owner),
                [product.CC, product.GUARD],
            )

            # Recreate the exact already-owned legacy hook seen on the real
            # printer before the parser-safe namespace repair.  The ownership
            # manifest remains in place, so the next update must migrate it
            # rather than classifying it as foreign state.
            owner.write_text(
                hook([product.CC, product.LEGACY_GUARD]),
                encoding="utf-8",
            )

            migration = product.build_preflight_plan(
                printer,
                POLICY,
                policy_dest,
                variables,
                state,
                backups,
                payload([product.CC, product.LEGACY_GUARD]),
            )
            self.assertEqual(migration["baseline_source"], "manifest")
            product.apply_plan(migration, POLICY)
            self.assertEqual(
                product.hook_commands(owner),
                [product.CC, product.GUARD],
            )
            self.assertNotIn(product.LEGACY_GUARD, product.hook_commands(owner))

    def test_parser_safe_namespace_is_distinct_from_product_name(self) -> None:
        self.assertEqual(product.GUARD, "_ADZ_SAVED_CHECK_POLICY")
        self.assertEqual(product.LEGACY_GUARD, "_AD5X_Z_SAVED_CHECK_POLICY")
        self.assertNotIn("5", product.GUARD)


if __name__ == "__main__":
    unittest.main()
