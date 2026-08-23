from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
MODEL = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"
INTEROP = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_interop.py"
SPOOLMAN = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_spoolman.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IFSManagerModelInstallerLifecycleTests(unittest.TestCase):
    maxDiff = None

    def run_shell(self, body: str, tmp: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        moon = tmp / "moonraker"
        components = moon / "components"
        components.mkdir(parents=True, exist_ok=True)
        (moon / ".git" / "info").mkdir(parents=True, exist_ok=True)
        state = tmp / "state-root"
        (state / "state").mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "AD5X_INSTALLER_FUNCTIONS_ONLY": "1",
                "AD5X_PLUGIN_DIR": str(ROOT),
                "AD5X_STATE_DIR": str(state),
                "AD5X_BACKEND_DEST": str(components / "plugins_ad5x.py"),
                "AD5X_BACKEND_MODEL_DEST": str(components / "plugins_ad5x_ifs_model.py"),
                "AD5X_BACKEND_INTEROP_DEST": str(components / "plugins_ad5x_ifs_interop.py"),
                "AD5X_BACKEND_SPOOLMAN_DEST": str(components / "plugins_ad5x_ifs_spoolman.py"),
                "AD5X_MOONRAKER_COMPONENTS_DIR": str(components),
                "AD5X_MOONRAKER_REPO_ROOT": str(moon),
                "AD5X_MOONRAKER_INCLUDES": str(tmp / "plugins.moonraker.conf"),
                "AD5X_USER_MOONRAKER": str(tmp / "user.moonraker.conf"),
                "AD5X_KLIPPER_INCLUDES": str(tmp / "plugins.cfg"),
                "AD5X_POWER_ON": str(tmp / "power_on.sh"),
                "AD5X_PYTHON_BIN": os.sys.executable,
            }
        )
        command = f'. "{INSTALLER}"\n{body}\n'
        return subprocess.run(["sh", "-c", command], text=True, capture_output=True, env=env, check=check)

    def test_default_helper_destinations_are_next_to_backend(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('BACKEND_MODEL_DEST="${AD5X_BACKEND_MODEL_DEST:-$MOONRAKER_COMPONENTS_DIR/plugins_ad5x_ifs_model.py}"', text)
        self.assertIn('BACKEND_INTEROP_DEST="${AD5X_BACKEND_INTEROP_DEST:-$MOONRAKER_COMPONENTS_DIR/plugins_ad5x_ifs_interop.py}"', text)
        self.assertIn('BACKEND_SPOOLMAN_DEST="${AD5X_BACKEND_SPOOLMAN_DEST:-$MOONRAKER_COMPONENTS_DIR/plugins_ad5x_ifs_spoolman.py}"', text)

    def test_source_validation_requires_model_interop_and_spoolman_helpers(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        body = text[text.index("backend_source_valid(){"):text.index("validate_backend_source(){")]
        for name in ("BACKEND_MODEL_SOURCE", "BACKEND_INTEROP_SOURCE", "BACKEND_SPOOLMAN_SOURCE"):
            self.assertIn(f'[ -s "${name}" ] || return 1', body)
            self.assertIn(f'python_source_valid "${name}" || return 1', body)

    def test_deploy_links_all_backend_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_shell("deploy_backend_plugin_links", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            components = tmp / "moonraker" / "components"
            expected = {
                "plugins_ad5x_ifs_model.py": MODEL,
                "plugins_ad5x_ifs_interop.py": INTEROP,
                "plugins_ad5x_ifs_spoolman.py": SPOOLMAN,
            }
            for name, source in expected.items():
                dest = components / name
                self.assertTrue(dest.is_symlink())
                self.assertEqual(os.readlink(dest), str(source))

    def test_snapshot_and_restore_preserve_symlink_identity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            components = tmp / "moonraker" / "components"
            components.mkdir(parents=True, exist_ok=True)
            dest = components / "plugins_ad5x_ifs_model.py"
            dest.symlink_to(MODEL)
            result = self.run_shell(
                'B="$AD5X_STATE_DIR/backup"; mkdir -p "$B"; '
                'snapshot "$BACKEND_MODEL_DEST" model.py; '
                'rm -f "$BACKEND_MODEL_DEST"; '
                'restore_snapshot "$BACKEND_MODEL_DEST" model.py; '
                'test -L "$BACKEND_MODEL_DEST"; '
                'test "$(readlink "$BACKEND_MODEL_DEST")" = "$BACKEND_MODEL_SOURCE"',
                tmp,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_foreign_model_destination_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("foreign-model\n", encoding="utf-8")
            result = self.run_shell("validate_backend_destination_ownership", tmp, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(dest.read_text(), "foreign-model\n")

    def test_legacy_managed_model_is_migrated_to_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(MODEL.read_bytes())
            marker = tmp / "state-root" / "state" / "backend-ifs-model-runtime.sha256"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(sha256(dest) + "\n", encoding="utf-8")
            result = self.run_shell("deploy_backend_plugin_links", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(dest.is_symlink())
            self.assertEqual(os.readlink(dest), str(MODEL))
            self.assertFalse(marker.exists())

    def test_runtime_match_requires_exact_link_targets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_shell("deploy_backend_plugin_links; backend_runtime_matches_source", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            model_dest = tmp / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"
            model_dest.unlink()
            model_dest.symlink_to(tmp / "wrong.py")
            result = self.run_shell("backend_runtime_matches_source", tmp, check=False)
            self.assertNotEqual(result.returncode, 0)

    def test_disable_removes_all_owned_backend_helper_links(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            deploy = self.run_shell("deploy_backend_plugin_links", tmp, check=False)
            self.assertEqual(deploy.returncode, 0, deploy.stderr)
            components = tmp / "moonraker" / "components"
            pycache = components / "__pycache__"
            pycache.mkdir(exist_ok=True)
            (pycache / "plugins_ad5x_ifs_model.cpython-312.pyc").write_bytes(b"x")
            result = self.run_shell("backend_disable_transition", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in (
                "plugins_ad5x.py",
                "plugins_ad5x_ifs_model.py",
                "plugins_ad5x_ifs_interop.py",
                "plugins_ad5x_ifs_spoolman.py",
            ):
                self.assertFalse((components / name).exists())
            self.assertFalse(any(pycache.glob("plugins_ad5x*.pyc")))


if __name__ == "__main__":
    unittest.main()
