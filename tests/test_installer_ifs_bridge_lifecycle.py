from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
BRIDGE = ROOT / "klipper" / "extras" / "ad5x_ifs.py"
KLIPPER_CONFIG = ROOT / "ad5x_custom.cfg"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IFSBridgeInstallerLifecycleTests(unittest.TestCase):
    def run_shell(
        self, body: str, tmp: Path, *, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        extras = tmp / "klipper" / "klippy" / "extras"
        extras.mkdir(parents=True, exist_ok=True)
        state = tmp / "state-root" / "state"
        state.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "AD5X_INSTALLER_FUNCTIONS_ONLY": "1",
                "AD5X_PLUGIN_DIR": str(ROOT),
                "AD5X_STATE_DIR": str(tmp / "state-root"),
                "AD5X_KLIPPER_BRIDGE_DEST": str(extras / "ad5x_ifs.py"),
                "AD5X_KLIPPER_EXTRAS_DIR": str(extras),
                "AD5X_BACKEND_DEST": str(tmp / "moonraker" / "components" / "plugins_ad5x.py"),
                "AD5X_MOONRAKER_COMPONENTS_DIR": str(tmp / "moonraker" / "components"),
                "AD5X_MOONRAKER_INCLUDES": str(tmp / "plugins.moonraker.conf"),
                "AD5X_USER_MOONRAKER": str(tmp / "user.moonraker.conf"),
                "AD5X_KLIPPER_INCLUDES": str(tmp / "plugins.cfg"),
                "AD5X_POWER_ON": str(tmp / "power_on.sh"),
                "AD5X_PYTHON_BIN": os.sys.executable,
            }
        )
        (tmp / "moonraker" / "components").mkdir(parents=True, exist_ok=True)
        command = f'. "{INSTALLER}"\n{body}\n'
        return subprocess.run(
            ["sh", "-c", command],
            text=True,
            capture_output=True,
            env=env,
            check=check,
        )

    def test_source_validation_and_stock_ad5x_destination(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("/opt/config/base/klipper/klippy/extras/ad5x_ifs.py", text)
        with tempfile.TemporaryDirectory() as td:
            result = self.run_shell("klipper_bridge_source_valid", Path(td), check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_destination_matches_ad5x_stock_klipper_runtime(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn(
            'KLIPPER_BRIDGE_DEST="${AD5X_KLIPPER_BRIDGE_DEST:-/opt/config/base/klipper/klippy/extras/ad5x_ifs.py}"',
            text,
        )

    def test_default_destination_does_not_use_non_live_ad5x_trees(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn(
            'KLIPPER_BRIDGE_DEST="${AD5X_KLIPPER_BRIDGE_DEST:-/usr/prog/klipper/klippy/extras/ad5x_ifs.py}"',
            text,
        )
        self.assertNotIn(
            'KLIPPER_BRIDGE_DEST="${AD5X_KLIPPER_BRIDGE_DEST:-/root/klipper-env/klippy/extras/ad5x_ifs.py}"',
            text,
        )

    def test_managed_copy_is_atomic_and_records_hash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_shell("deploy_klipper_bridge_managed_copy", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            dest = tmp / "klipper" / "klippy" / "extras" / "ad5x_ifs.py"
            marker = tmp / "state-root" / "state" / "klipper-ifs-bridge.sha256"
            self.assertEqual(dest.read_bytes(), BRIDGE.read_bytes())
            self.assertEqual(marker.read_text().strip(), sha256(BRIDGE))

    def test_existing_managed_copy_is_replaceable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "klipper" / "klippy" / "extras" / "ad5x_ifs.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("old-managed\n", encoding="utf-8")
            marker = tmp / "state-root" / "state" / "klipper-ifs-bridge.sha256"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(sha256(dest) + "\n", encoding="utf-8")
            result = self.run_shell("deploy_klipper_bridge_managed_copy", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(dest.read_bytes(), BRIDGE.read_bytes())

    def test_foreign_destination_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "klipper" / "klippy" / "extras" / "ad5x_ifs.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("foreign\n", encoding="utf-8")
            result = self.run_shell(
                "validate_klipper_bridge_destination_ownership", tmp, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(dest.read_text(), "foreign\n")

    def test_uninstall_removes_only_owned_runtime_and_bytecode(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            first = self.run_shell("deploy_klipper_bridge_managed_copy", tmp, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            extras = tmp / "klipper" / "klippy" / "extras"
            pycache = extras / "__pycache__"
            pycache.mkdir(exist_ok=True)
            (pycache / "ad5x_ifs.cpython-312.pyc").write_bytes(b"x")
            result = self.run_shell("remove_klipper_bridge_managed_copy", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((extras / "ad5x_ifs.py").exists())
            self.assertFalse(any(pycache.glob("ad5x_ifs*.pyc")))
            self.assertFalse(
                (tmp / "state-root" / "state" / "klipper-ifs-bridge.sha256").exists()
            )

    def test_config_activation_exists_and_deploy_precedes_future_restart(self) -> None:
        config = KLIPPER_CONFIG.read_text(encoding="utf-8")
        self.assertEqual(config.count("[ad5x_ifs]"), 1)
        text = INSTALLER.read_text(encoding="utf-8")
        install = text[text.index("\ncheck_idle\nvalidate_backend_source") + 1 :]
        self.assertLess(
            install.index("deploy_klipper_bridge_managed_copy"),
            install.index("run_moonraker_transition backend_install_transition"),
        )
        self.assertIn('snapshot "$KLIPPER_BRIDGE_DEST" klipper-ifs-bridge.py', text)
        self.assertIn('restore_snapshot "$KLIPPER_BRIDGE_DEST" klipper-ifs-bridge.py', text)


if __name__ == "__main__":
    unittest.main()
