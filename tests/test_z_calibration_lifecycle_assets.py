from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
HELPER = ROOT / "installer" / "z_calibration_runtime.sh"
BACKEND = ROOT / "moonraker" / "components" / "plugins_ad5x.py"
CORE = ROOT / "moonraker" / "components" / "plugins_ad5x_zcalibration.py"
HOOK = ROOT / "z_calibration.cfg"
CUSTOM = ROOT / "ad5x_custom.cfg"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ZCalibrationRuntimeAssetTests(unittest.TestCase):
    def run_helper(self, body: str, tmp: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        components = tmp / "moonraker" / "components"
        state = tmp / "state"
        components.mkdir(parents=True, exist_ok=True)
        state.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "PLUGIN_DIR": str(ROOT),
                "STATE": str(state),
                "MOONRAKER_COMPONENTS_DIR": str(components),
                "AD5X_ZCAL_CORE_DEST": str(components / "plugins_ad5x_zcalibration.py"),
            }
        )
        shell = f'''
set -eu
python_bin(){{ command -v python3; }}
sha256_file(){{ sha256sum "$1" | awk '{{print $1}}'; }}
fail(){{ echo "$*" >&2; return 1; }}
. "{HELPER}"
{body}
'''
        return subprocess.run(
            ["sh", "-c", shell],
            text=True,
            capture_output=True,
            env=env,
            check=check,
        )

    def run_main(self, body: str, tmp: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        components = tmp / "moonraker" / "components"
        state_root = tmp / "state-root"
        components.mkdir(parents=True, exist_ok=True)
        (state_root / "state").mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "AD5X_INSTALLER_FUNCTIONS_ONLY": "1",
                "AD5X_PLUGIN_DIR": str(ROOT),
                "AD5X_STATE_DIR": str(state_root),
                "AD5X_BACKEND_DEST": str(components / "plugins_ad5x.py"),
                "AD5X_ZCAL_CORE_DEST": str(components / "plugins_ad5x_zcalibration.py"),
                "AD5X_MOONRAKER_COMPONENTS_DIR": str(components),
                "AD5X_MOONRAKER_INCLUDES": str(tmp / "plugins.moonraker.conf"),
                "AD5X_USER_MOONRAKER": str(tmp / "user.moonraker.conf"),
                "AD5X_KLIPPER_INCLUDES": str(tmp / "plugins.cfg"),
                "AD5X_POWER_ON": str(tmp / "power_on.sh"),
                "AD5X_PYTHON_BIN": os.sys.executable,
            }
        )
        return subprocess.run(
            ["sh", "-c", f'. "{INSTALLER}"\n{body}\n'],
            text=True,
            capture_output=True,
            env=env,
            check=check,
        )

    def test_helper_has_valid_shell_syntax(self) -> None:
        result = subprocess.run(
            ["sh", "-n", str(HELPER)], text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_core_source_validation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_helper("zcal_core_source_valid", Path(td), check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_absent_destination_deploys_atomic_managed_copy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_helper(
                "zcal_core_deploy_managed_copy; zcal_core_runtime_matches_source",
                tmp,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            dest = tmp / "moonraker" / "components" / "plugins_ad5x_zcalibration.py"
            marker = tmp / "state" / "zcalibration-runtime.sha256"
            self.assertEqual(dest.read_bytes(), CORE.read_bytes())
            self.assertEqual(marker.read_text().strip(), sha256(CORE))

    def test_known_managed_destination_is_replaceable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "moonraker" / "components" / "plugins_ad5x_zcalibration.py"
            marker = tmp / "state" / "zcalibration-runtime.sha256"
            dest.parent.mkdir(parents=True, exist_ok=True)
            marker.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("old-managed\n", encoding="utf-8")
            marker.write_text(sha256(dest) + "\n", encoding="utf-8")
            result = self.run_helper("zcal_core_deploy_managed_copy", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(dest.read_bytes(), CORE.read_bytes())

    def test_foreign_destination_fails_closed_without_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "moonraker" / "components" / "plugins_ad5x_zcalibration.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("foreign\n", encoding="utf-8")
            result = self.run_helper("zcal_core_deploy_managed_copy", tmp, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(dest.read_text(encoding="utf-8"), "foreign\n")

    def test_uninstall_removes_only_owned_runtime_marker_and_bytecode(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            first = self.run_helper("zcal_core_deploy_managed_copy", tmp, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            pycache = tmp / "moonraker" / "components" / "__pycache__"
            pycache.mkdir(exist_ok=True)
            (pycache / "plugins_ad5x_zcalibration.cpython-312.pyc").write_bytes(b"x")
            second = self.run_helper("zcal_core_uninstall_managed_copy", tmp, check=False)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertFalse(
                (tmp / "moonraker" / "components" / "plugins_ad5x_zcalibration.py").exists()
            )
            self.assertFalse((tmp / "state" / "zcalibration-runtime.sha256").exists())
            self.assertFalse(any(pycache.glob("plugins_ad5x_zcalibration*.pyc")))

    def test_hook_mirrors_zmod_three_way_start_semantics(self) -> None:
        text = HOOK.read_text(encoding="utf-8")
        self.assertIn("printer[\"gcode_macro _SCREEN\"].screen", text)
        self.assertIn("save_variables.variables['load_zoffset']", text)
        self.assertIn('printer["gcode_macro _START_PRINT"].zzoffset', text)
        self.assertIn("load_zoffset == 1 and screen == False", text)
        self.assertIn('mode="global"', text)
        self.assertIn('mode="job"', text)
        self.assertIn('mode="none"', text)
        self.assertEqual(text.count('action_call_remote_method("plugins_ad5x_z_job_start"'), 3)
        self.assertNotIn("SET_GCODE_OFFSET", text)
        self.assertNotIn("PROBE", text)
        self.assertNotIn("G1 ", text)

    def test_hook_asset_does_not_modify_existing_custom_overlay(self) -> None:
        custom = CUSTOM.read_text(encoding="utf-8")
        self.assertNotIn("z_calibration.cfg", custom)

    def test_main_installer_activates_hook_only_after_idle_gate_and_snapshots(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        include = "append_line \"$KLIPPER_INCLUDES\" '[include plugins/ad5x_custom/z_calibration.cfg]'"
        self.assertEqual(text.count(include), 1)
        install_start = text.index('\ncheck_idle\nvalidate_backend_source') + 1
        install = text[install_start:]
        self.assertLess(install.index("check_idle"), install.index(include))
        self.assertLess(
            install.index('snapshot "$KLIPPER_INCLUDES" plugins.cfg'),
            install.index(include),
        )
        self.assertLess(
            install.index(include),
            install.index("run_moonraker_transition backend_install_transition"),
        )

    def test_main_installer_manages_both_moonraker_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_main(
                "deploy_backend_managed_copy; backend_runtime_matches_source",
                tmp,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            components = tmp / "moonraker" / "components"
            self.assertEqual((components / "plugins_ad5x.py").read_bytes(), BACKEND.read_bytes())
            self.assertEqual(
                (components / "plugins_ad5x_zcalibration.py").read_bytes(), CORE.read_bytes()
            )
            state = tmp / "state-root" / "state"
            self.assertEqual(
                (state / "backend-runtime.sha256").read_text().strip(), sha256(BACKEND)
            )
            self.assertEqual(
                (state / "zcalibration-runtime.sha256").read_text().strip(), sha256(CORE)
            )

    def test_foreign_zcal_runtime_blocks_combined_deploy_before_main_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            components = tmp / "moonraker" / "components"
            main_dest = components / "plugins_ad5x.py"
            zcal_dest = components / "plugins_ad5x_zcalibration.py"
            main_dest.write_text("old-main\n", encoding="utf-8")
            main_marker = tmp / "state-root" / "state" / "backend-runtime.sha256"
            main_marker.write_text(sha256(main_dest) + "\n", encoding="utf-8")
            zcal_dest.write_text("foreign-zcal\n", encoding="utf-8")
            result = self.run_main("deploy_backend_managed_copy", tmp, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(main_dest.read_text(encoding="utf-8"), "old-main\n")
            self.assertEqual(zcal_dest.read_text(encoding="utf-8"), "foreign-zcal\n")

    def test_combined_uninstall_removes_both_owned_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            deploy = self.run_main("deploy_backend_managed_copy", tmp, check=False)
            self.assertEqual(deploy.returncode, 0, deploy.stderr)
            uninstall = self.run_main("backend_uninstall_transition", tmp, check=False)
            self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
            components = tmp / "moonraker" / "components"
            self.assertFalse((components / "plugins_ad5x.py").exists())
            self.assertFalse((components / "plugins_ad5x_zcalibration.py").exists())
            state = tmp / "state-root" / "state"
            self.assertFalse((state / "backend-runtime.sha256").exists())
            self.assertFalse((state / "zcalibration-runtime.sha256").exists())

    def test_install_and_uninstall_rollback_cover_zcal_runtime_and_hash(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count('snapshot "$ZCAL_CORE_DEST" zcal-runtime.py'), 2)
        self.assertGreaterEqual(
            text.count('snapshot "$ZCAL_CORE_HASH_STATE" zcal-runtime.sha256'), 2
        )
        self.assertGreaterEqual(
            text.count('restore_snapshot "$ZCAL_CORE_DEST" zcal-runtime.py'), 2
        )
        self.assertGreaterEqual(
            text.count('restore_snapshot "$ZCAL_CORE_HASH_STATE" zcal-runtime.sha256'), 2
        )


if __name__ == "__main__":
    unittest.main()
