from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
RUNTIME_HELPER = ROOT / "installer" / "z_calibration_runtime.sh"
PRODUCTIZER = ROOT / "installer" / "z_calibration_productization.py"
CORE_SOURCE = ROOT / "moonraker" / "components" / "plugins_ad5x_zcalibration.py"
WRAPPER = ROOT / "z_calibration.cfg"
POLICY = ROOT / "z_calibration_rc_policy.cfg"


class ZCalibrationLifecycleAssetTests(unittest.TestCase):
    def run_shell(self, script: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            ["sh", "-c", script],
            cwd=ROOT,
            env=merged,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_runtime_helper_shell_syntax(self) -> None:
        result = subprocess.run(
            ["sh", "-n", str(RUNTIME_HELPER)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_productizer_compiles(self) -> None:
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(PRODUCTIZER)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_compatibility_wrapper_no_longer_owns_user_start_print(self) -> None:
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertNotIn("[gcode_macro _USER_START_PRINT]", wrapper)
        self.assertNotIn("plugins_ad5x_z_job_start", wrapper)

    def test_canonical_policy_is_separate_runtime_asset(self) -> None:
        policy = POLICY.read_text(encoding="utf-8")
        self.assertIn("[gcode_macro _AD5X_Z_SAVED_CHECK_POLICY]", policy)
        self.assertNotIn("[gcode_macro _USER_START_PRINT]", policy)

    def test_install_sh_still_has_single_compatibility_include_seam(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        include = "[include plugins/ad5x_custom/z_calibration.cfg]"
        self.assertIn(f"append_line \"$KLIPPER_INCLUDES\" '{include}'", text)
        self.assertIn("zcal_hook_include_ok", text)

    def test_helper_adds_generated_policy_include(self) -> None:
        text = RUNTIME_HELPER.read_text(encoding="utf-8")
        self.assertIn("[include ad5x_custom/generated/zcal_owner_rc.cfg]", text)
        self.assertIn("append_line \"$KLIPPER_INCLUDES\" \"$INC\"", text)

    def test_helper_extends_generic_transaction_snapshot_and_restore(self) -> None:
        text = RUNTIME_HELPER.read_text(encoding="utf-8")
        self.assertIn("zcal_rc_transaction_snapshot", text)
        self.assertIn("zcal_rc_transaction_restore", text)
        self.assertIn('if [ "$KEY" = plugins.cfg ]', text)

    def test_helper_integrates_apply_verify_uninstall_with_managed_copy(self) -> None:
        text = RUNTIME_HELPER.read_text(encoding="utf-8")
        self.assertIn("zcal_rc_apply", text)
        self.assertIn("zcal_rc_live_verify", text)
        self.assertIn("zcal_rc_uninstall", text)
        self.assertLess(
            text.index("zcal_rc_uninstall || return 1"),
            text.index('rm -f "$ZCAL_CORE_DEST"'),
        )

    def test_functions_only_core_deploy_remains_managed_copy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plugin = root / "plugin"
            components = root / "components"
            state = root / "state"
            generated = root / "generated"
            plugin.mkdir()
            components.mkdir()
            state.mkdir()
            generated.mkdir()
            shutil.copytree(ROOT / "installer", plugin / "installer")
            shutil.copytree(ROOT / "moonraker", plugin / "moonraker")
            shutil.copy2(POLICY, plugin / "z_calibration_rc_policy.cfg")
            shutil.copy2(WRAPPER, plugin / "z_calibration.cfg")

            dest = components / "plugins_ad5x_zcalibration.py"
            script = f"""
set -eu
PLUGIN_DIR='{plugin}'
STATE='{state}'
GENERATED='{generated}'
MOONRAKER_COMPONENTS_DIR='{components}'
AD5X_INSTALLER_FUNCTIONS_ONLY=1
python_bin() {{ command -v python3; }}
sha256_file() {{ sha256sum "$1" | awk '{{print $1}}'; }}
fail() {{ echo "$*" >&2; return 1; }}
. '{plugin / "installer" / "z_calibration_runtime.sh"}'
zcal_core_init_paths
zcal_core_source_valid
validate_zcal_core_destination_ownership
zcal_core_deploy_managed_copy
zcal_core_runtime_matches_source
"""
            result = self.run_shell(script)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(dest.is_file())
            self.assertFalse(dest.is_symlink())
            self.assertEqual(
                hashlib.sha256(dest.read_bytes()).hexdigest(),
                hashlib.sha256(CORE_SOURCE.read_bytes()).hexdigest(),
            )
            self.assertTrue((state / "zcalibration-runtime.sha256").is_file())

    def test_unknown_core_destination_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plugin = root / "plugin"
            components = root / "components"
            state = root / "state"
            generated = root / "generated"
            plugin.mkdir()
            components.mkdir()
            state.mkdir()
            generated.mkdir()
            shutil.copytree(ROOT / "installer", plugin / "installer")
            shutil.copytree(ROOT / "moonraker", plugin / "moonraker")
            shutil.copy2(POLICY, plugin / "z_calibration_rc_policy.cfg")
            shutil.copy2(WRAPPER, plugin / "z_calibration.cfg")
            (components / "plugins_ad5x_zcalibration.py").write_text("FOREIGN\n", encoding="utf-8")

            script = f"""
set -eu
PLUGIN_DIR='{plugin}'
STATE='{state}'
GENERATED='{generated}'
MOONRAKER_COMPONENTS_DIR='{components}'
AD5X_INSTALLER_FUNCTIONS_ONLY=1
python_bin() {{ command -v python3; }}
sha256_file() {{ sha256sum "$1" | awk '{{print $1}}'; }}
fail() {{ echo "$*" >&2; return 1; }}
. '{plugin / "installer" / "z_calibration_runtime.sh"}'
zcal_core_init_paths
zcal_core_destination_owned
"""
            result = self.run_shell(script)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(
                (components / "plugins_ad5x_zcalibration.py").read_text(encoding="utf-8"),
                "FOREIGN\n",
            )

    def test_functions_only_uninstall_removes_only_owned_core_copy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plugin = root / "plugin"
            components = root / "components"
            state = root / "state"
            generated = root / "generated"
            plugin.mkdir()
            components.mkdir()
            state.mkdir()
            generated.mkdir()
            shutil.copytree(ROOT / "installer", plugin / "installer")
            shutil.copytree(ROOT / "moonraker", plugin / "moonraker")
            shutil.copy2(POLICY, plugin / "z_calibration_rc_policy.cfg")
            shutil.copy2(WRAPPER, plugin / "z_calibration.cfg")

            script = f"""
set -eu
PLUGIN_DIR='{plugin}'
STATE='{state}'
GENERATED='{generated}'
MOONRAKER_COMPONENTS_DIR='{components}'
AD5X_INSTALLER_FUNCTIONS_ONLY=1
python_bin() {{ command -v python3; }}
sha256_file() {{ sha256sum "$1" | awk '{{print $1}}'; }}
fail() {{ echo "$*" >&2; return 1; }}
. '{plugin / "installer" / "z_calibration_runtime.sh"}'
zcal_core_init_paths
zcal_core_deploy_managed_copy
zcal_core_uninstall_managed_copy
[ ! -e "$ZCAL_CORE_DEST" ]
[ ! -e "$ZCAL_CORE_HASH_STATE" ]
"""
            result = self.run_shell(script)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_productization_helpers_do_not_mutate_git_worktree(self) -> None:
        text = RUNTIME_HELPER.read_text(encoding="utf-8") + PRODUCTIZER.read_text(encoding="utf-8")
        self.assertNotIn("git checkout", text)
        self.assertNotIn("git reset", text)
        self.assertNotIn("reset --hard", text)


if __name__ == "__main__":
    unittest.main()
