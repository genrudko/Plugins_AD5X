from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
BACKEND = ROOT / "moonraker" / "components" / "plugins_ad5x.py"
MODEL = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IFSManagerModelInstallerLifecycleTests(unittest.TestCase):
    maxDiff = None

    def run_shell(
        self,
        body: str,
        tmp: Path,
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        components = tmp / "moonraker" / "components"
        components.mkdir(parents=True, exist_ok=True)
        state = tmp / "state-root"
        (state / "state").mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env.update(
            {
                "AD5X_INSTALLER_FUNCTIONS_ONLY": "1",
                "AD5X_PLUGIN_DIR": str(ROOT),
                "AD5X_STATE_DIR": str(state),
                "AD5X_BACKEND_DEST": str(components / "plugins_ad5x.py"),
                "AD5X_BACKEND_MODEL_DEST": str(
                    components / "plugins_ad5x_ifs_model.py"
                ),
                "AD5X_MOONRAKER_COMPONENTS_DIR": str(components),
                "AD5X_MOONRAKER_INCLUDES": str(tmp / "plugins.moonraker.conf"),
                "AD5X_USER_MOONRAKER": str(tmp / "user.moonraker.conf"),
                "AD5X_KLIPPER_INCLUDES": str(tmp / "plugins.cfg"),
                "AD5X_POWER_ON": str(tmp / "power_on.sh"),
                "AD5X_PYTHON_BIN": os.sys.executable,
            }
        )
        command = f'. "{INSTALLER}"\n{body}\n'
        return subprocess.run(
            ["sh", "-c", command],
            text=True,
            capture_output=True,
            env=env,
            check=check,
        )

    def test_default_model_destination_is_next_to_backend(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn(
            'BACKEND_MODEL_DEST="${AD5X_BACKEND_MODEL_DEST:-$MOONRAKER_COMPONENTS_DIR/plugins_ad5x_ifs_model.py}"',
            text,
        )
        self.assertNotIn("/usr/prog/", text[text.index("BACKEND_MODEL_SOURCE"):text.index("KLIPPER_BRIDGE_SOURCE")])

    def test_source_validation_requires_model(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        start = text.index("backend_source_valid(){")
        end = text.index("validate_backend_source(){", start)
        body = text[start:end]
        self.assertIn('[ -s "$BACKEND_MODEL_SOURCE" ] || return 1', body)
        self.assertIn('python_source_valid "$BACKEND_MODEL_SOURCE" || return 1', body)

    def test_deploy_installs_backend_and_model_with_hash_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_shell("deploy_backend_managed_copy", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

            components = tmp / "moonraker" / "components"
            backend_dest = components / "plugins_ad5x.py"
            model_dest = components / "plugins_ad5x_ifs_model.py"
            self.assertEqual(backend_dest.read_bytes(), BACKEND.read_bytes())
            self.assertEqual(model_dest.read_bytes(), MODEL.read_bytes())

            state = tmp / "state-root" / "state"
            self.assertEqual(
                (state / "backend-runtime.sha256").read_text().strip(),
                sha256(BACKEND),
            )
            self.assertEqual(
                (state / "backend-ifs-model-runtime.sha256").read_text().strip(),
                sha256(MODEL),
            )

    def test_both_temp_files_are_verified_before_first_runtime_move(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        start = text.index("deploy_backend_managed_copy(){")
        end = text.index("backend_runtime_matches_source(){", start)
        body = text[start:end]

        verify_backend = body.index('[ "$(sha256_file "$TMP")" = "$SOURCE_HASH" ]')
        verify_model = body.index(
            '[ "$(sha256_file "$MODEL_TMP")" = "$MODEL_SOURCE_HASH" ]'
        )
        first_move = min(
            body.index('mv -f "$MODEL_TMP" "$BACKEND_MODEL_DEST"'),
            body.index('mv -f "$TMP" "$BACKEND_DEST"'),
        )
        self.assertLess(verify_backend, first_move)
        self.assertLess(verify_model, first_move)

    def test_foreign_model_destination_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            components = tmp / "moonraker" / "components"
            components.mkdir(parents=True, exist_ok=True)
            model_dest = components / "plugins_ad5x_ifs_model.py"
            model_dest.write_text("foreign-model\n", encoding="utf-8")

            result = self.run_shell(
                "validate_backend_destination_ownership",
                tmp,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(model_dest.read_text(), "foreign-model\n")

    def test_existing_managed_model_is_replaceable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            components = tmp / "moonraker" / "components"
            components.mkdir(parents=True, exist_ok=True)
            model_dest = components / "plugins_ad5x_ifs_model.py"
            model_dest.write_text("managed-old-model\n", encoding="utf-8")
            state = tmp / "state-root" / "state"
            state.mkdir(parents=True, exist_ok=True)
            (state / "backend-ifs-model-runtime.sha256").write_text(
                sha256(model_dest) + "\n",
                encoding="utf-8",
            )

            result = self.run_shell("deploy_backend_managed_copy", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(model_dest.read_bytes(), MODEL.read_bytes())

    def test_runtime_match_requires_model_hash_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_shell(
                "deploy_backend_managed_copy; backend_runtime_matches_source",
                tmp,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            model_dest = tmp / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"
            model_dest.write_text("tampered\n", encoding="utf-8")
            result = self.run_shell(
                "backend_runtime_matches_source",
                tmp,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_install_and_uninstall_backup_model_state(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertGreaterEqual(
            text.count('snapshot "$BACKEND_MODEL_DEST" backend-ifs-model-runtime.py'),
            2,
        )
        self.assertGreaterEqual(
            text.count(
                'snapshot "$BACKEND_MODEL_HASH_STATE" backend-ifs-model-runtime.sha256'
            ),
            2,
        )
        self.assertGreaterEqual(
            text.count('restore_snapshot "$BACKEND_MODEL_DEST" backend-ifs-model-runtime.py'),
            2,
        )
        self.assertGreaterEqual(
            text.count(
                'restore_snapshot "$BACKEND_MODEL_HASH_STATE" backend-ifs-model-runtime.sha256'
            ),
            2,
        )

    def test_uninstall_removes_owned_model_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            deploy = self.run_shell("deploy_backend_managed_copy", tmp, check=False)
            self.assertEqual(deploy.returncode, 0, deploy.stderr)

            components = tmp / "moonraker" / "components"
            model_dest = components / "plugins_ad5x_ifs_model.py"
            pycache = components / "__pycache__"
            pycache.mkdir(exist_ok=True)
            (pycache / "plugins_ad5x_ifs_model.cpython-312.pyc").write_bytes(b"x")

            result = self.run_shell("backend_uninstall_transition", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(model_dest.exists())
            self.assertFalse(
                (tmp / "state-root" / "state" / "backend-ifs-model-runtime.sha256").exists()
            )
            self.assertFalse(any(pycache.glob("plugins_ad5x_ifs_model*.pyc")))


if __name__ == "__main__":
    unittest.main()
