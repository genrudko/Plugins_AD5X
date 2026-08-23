from __future__ import annotations

import hashlib
import os
import shlex
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
BACKEND = ROOT / "moonraker" / "components" / "plugins_ad5x.py"
MODEL = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"
INTEROP = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_interop.py"
SPOOLMAN = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_spoolman.py"
CONFIG = ROOT / "plugins_ad5x.moonraker.conf"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BackendInstallerLifecycleTests(unittest.TestCase):
    maxDiff = None

    def run_shell(self, body: str, tmp: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        moon = tmp / "moonraker"
        klipper = tmp / "klipper"
        components = moon / "components"
        extras = klipper / "klippy" / "extras"
        components.mkdir(parents=True, exist_ok=True)
        extras.mkdir(parents=True, exist_ok=True)
        (moon / ".git" / "info").mkdir(parents=True, exist_ok=True)
        (klipper / ".git" / "info").mkdir(parents=True, exist_ok=True)
        (tmp / "state-root" / "state").mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "AD5X_INSTALLER_FUNCTIONS_ONLY": "1",
                "AD5X_PLUGIN_DIR": str(ROOT),
                "AD5X_STATE_DIR": str(tmp / "state-root"),
                "AD5X_BACKEND_DEST": str(components / "plugins_ad5x.py"),
                "AD5X_MOONRAKER_COMPONENTS_DIR": str(components),
                "AD5X_MOONRAKER_REPO_ROOT": str(moon),
                "AD5X_KLIPPER_BRIDGE_DEST": str(extras / "ad5x_ifs.py"),
                "AD5X_KLIPPER_EXTRAS_DIR": str(extras),
                "AD5X_KLIPPER_REPO_ROOT": str(klipper),
                "AD5X_MOONRAKER_INCLUDES": str(tmp / "plugins.moonraker.conf"),
                "AD5X_USER_MOONRAKER": str(tmp / "user.moonraker.conf"),
                "AD5X_KLIPPER_INCLUDES": str(tmp / "plugins.cfg"),
                "AD5X_POWER_ON": str(tmp / "power_on.sh"),
                "AD5X_PYTHON_BIN": os.sys.executable,
            }
        )
        command = f'. "{INSTALLER}"\n{body}\n'
        return subprocess.run(["sh", "-c", command], text=True, capture_output=True, env=env, check=check)

    def run_idle_check(self, tmp: Path, *, payload: str = "", wget_rc: int = 0) -> subprocess.CompletedProcess[str]:
        if wget_rc:
            body = f"wget(){{ return {wget_rc}; }}\ncheck_idle"
        else:
            body = f"wget(){{ printf '%s' {shlex.quote(payload)}; }}\ncheck_idle"
        return self.run_shell(body, tmp, check=False)

    @staticmethod
    def print_stats_payload(state: str) -> str:
        return '{"result":{"status":{"print_stats":{"state":"' + state + '"}}}}'

    def test_stable_zmod_root_precedes_process_root_fallback(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        body = text[text.index("find_root(){"):text.index("remove_lines(){")]
        self.assertLess(body.index("[ -d /usr/data/.mod/.zmod ]"), body.index("for P in /proc/[0-9]*"))

    def test_idle_gate_is_fail_closed_and_accepts_only_terminal_states(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            self.assertNotEqual(self.run_idle_check(tmp, wget_rc=7).returncode, 0)
            self.assertNotEqual(self.run_idle_check(tmp, payload="").returncode, 0)
            self.assertNotEqual(self.run_idle_check(tmp, payload="not-json").returncode, 0)
            for state in ("printing", "paused", "mystery"):
                with self.subTest(state=state):
                    self.assertNotEqual(self.run_idle_check(tmp, payload=self.print_stats_payload(state)).returncode, 0)
            for state in ("standby", "complete", "error", "cancelled"):
                with self.subTest(state=state):
                    result = self.run_idle_check(tmp, payload=self.print_stats_payload(state))
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_idle_gate_precedes_enable_disable_mutations(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        uninstall_start = text.index('if [ "$MODE" = --uninstall ] || [ "$MODE" = --disable-hook ]; then')
        install_start = text.index('\ncheck_idle\nvalidate_backend_source', uninstall_start) + 1
        uninstall = text[uninstall_start:install_start]
        self.assertLess(uninstall.index("check_idle"), uninstall.index('remove_lines "$KLIPPER_INCLUDES"'))
        self.assertLess(uninstall.index("check_idle"), uninstall.index("run_moonraker_transition"))
        install = text[install_start:]
        self.assertTrue(install.startswith("check_idle\n"))
        self.assertLess(install.index("check_idle"), install.index("deploy_klipper_bridge_plugin_link"))
        self.assertLess(install.index("check_idle"), install.index("run_moonraker_transition backend_install_transition"))

    def test_backend_source_validation_includes_all_runtime_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_shell("backend_source_valid", Path(td), check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
        text = INSTALLER.read_text(encoding="utf-8")
        body = text[text.index("backend_source_valid(){"):text.index("validate_backend_source(){")]
        for name in ("BACKEND_MODEL_SOURCE", "BACKEND_INTEROP_SOURCE", "BACKEND_SPOOLMAN_SOURCE"):
            self.assertIn(f'[ -s "${name}" ] || return 1', body)
            self.assertIn(f'python_source_valid "${name}" || return 1', body)

    def test_backend_deploy_uses_plugin_owned_links_and_git_exclude(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_shell("deploy_backend_plugin_links", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            components = tmp / "moonraker" / "components"
            expected = {
                "plugins_ad5x.py": BACKEND,
                "plugins_ad5x_ifs_model.py": MODEL,
                "plugins_ad5x_ifs_interop.py": INTEROP,
                "plugins_ad5x_ifs_spoolman.py": SPOOLMAN,
            }
            for name, source in expected.items():
                dest = components / name
                self.assertTrue(dest.is_symlink(), name)
                self.assertEqual(os.readlink(dest), str(source))
            exclude = (tmp / "moonraker" / ".git" / "info" / "exclude").read_text().splitlines()
            for name in expected:
                self.assertIn(f"/components/{name}", exclude)
            self.assertFalse((tmp / "state-root" / "state" / "backend-runtime.sha256").exists())
            self.assertFalse((tmp / "state-root" / "state" / "backend-ifs-model-runtime.sha256").exists())

    def test_legacy_managed_copy_migrates_to_link(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "moonraker" / "components" / "plugins_ad5x.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(BACKEND.read_bytes())
            marker = tmp / "state-root" / "state" / "backend-runtime.sha256"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(sha256(dest) + "\n", encoding="utf-8")
            result = self.run_shell("deploy_backend_plugin_links", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(dest.is_symlink())
            self.assertEqual(os.readlink(dest), str(BACKEND))
            self.assertFalse(marker.exists())

    def test_foreign_destination_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "moonraker" / "components" / "plugins_ad5x.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("foreign-file\n", encoding="utf-8")
            result = self.run_shell("validate_backend_destination_ownership", tmp, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(dest.read_text(), "foreign-file\n")

    def test_backend_config_activation_is_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            includes = tmp / "plugins.moonraker.conf"
            includes.write_text(
                "[include plugins/ad5x_custom/plugins_ad5x.moonraker.conf]\n"
                "[include plugins/ad5x_custom/plugins_ad5x.moonraker.conf]\n"
                "[include plugins/ad5x_custom/ad5x_custom.moonraker.conf]\n",
                encoding="utf-8",
            )
            result = self.run_shell("configure_moonraker_includes", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = includes.read_text().splitlines()
            self.assertEqual(lines.count("[include plugins/ad5x_custom/plugins_ad5x.moonraker.conf]"), 1)
            self.assertEqual(lines.count("[include plugins/ad5x_custom/ad5x_custom.moonraker.conf]"), 1)
            self.assertEqual(CONFIG.read_text(encoding="utf-8"), "[plugins_ad5x]\n")

    def test_disable_detaches_runtime_but_preserves_update_manager_registration(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            deploy = self.run_shell("deploy_backend_plugin_links", tmp, check=False)
            self.assertEqual(deploy.returncode, 0, deploy.stderr)
            user = tmp / "user.moonraker.conf"
            user.write_text("[update_manager ad5x_custom]\npath: keep-me\n", encoding="utf-8")
            result = self.run_shell("backend_disable_transition", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[update_manager ad5x_custom]", user.read_text())
            self.assertFalse((tmp / "moonraker" / "components" / "plugins_ad5x.py").exists())
            exclude = (tmp / "moonraker" / ".git" / "info" / "exclude").read_text()
            self.assertNotIn("plugins_ad5x", exclude)

    def test_full_uninstall_removes_update_manager_registration(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            self.run_shell("deploy_backend_plugin_links", tmp, check=False)
            user = tmp / "user.moonraker.conf"
            user.write_text("before=1\n[update_manager ad5x_custom]\npath: remove-me\n[next]\nkeep=1\n", encoding="utf-8")
            result = self.run_shell("backend_uninstall_transition", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = user.read_text()
            self.assertNotIn("update_manager ad5x_custom", data)
            self.assertIn("[next]", data)

    def test_stop_wait_transition_start_http_ready_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            log = tmp / "order.log"
            body = f'''
LOG={log}
moonraker_process_count(){{ echo 1; }}
stop_moonraker(){{ echo stop >>"$LOG"; }}
wait_moonraker_stopped(){{ echo wait-zero >>"$LOG"; }}
fake_transition(){{ echo transition >>"$LOG"; }}
start_moonraker(){{ echo start >>"$LOG"; }}
wait_moonraker_http(){{ echo http >>"$LOG"; }}
wait_klippy_ready(){{ echo ready >>"$LOG"; }}
fake_verify(){{ echo verify >>"$LOG"; }}
run_moonraker_transition fake_transition fake_verify
'''
            result = self.run_shell(body, tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(log.read_text().splitlines(), ["stop", "wait-zero", "transition", "start", "http", "ready", "verify"])

    def test_readiness_contract(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            not_ready = self.run_shell(
                "klippy_ready_from_json '{\"result\":{\"klippy_connected\":true,\"klippy_state\":\"startup\"}}'",
                tmp,
                check=False,
            )
            self.assertNotEqual(not_ready.returncode, 0)
            ready = self.run_shell(
                "klippy_ready_from_json '{\"result\":{\"klippy_connected\":true,\"klippy_state\":\"ready\"}}'",
                tmp,
                check=False,
            )
            self.assertEqual(ready.returncode, 0, ready.stderr)

    def test_update_hook_never_self_restarts_moonraker(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        start = text.index('if [ "$MODE" = --update-hook ]; then')
        end = text.index('if [ "$MODE" = --refresh-only ]; then', start)
        body = text[start:end]
        self.assertIn("deploy_backend_plugin_links", body)
        self.assertIn("deploy_klipper_bridge_plugin_link", body)
        self.assertNotIn("run_moonraker_transition", body)
        self.assertNotIn("stop_moonraker", body)
        self.assertNotIn("start_moonraker", body)

    def test_zmod_plugin_lifecycle_wrappers_exist_and_are_executable(self) -> None:
        update = ROOT / "update.sh"
        uninstall = ROOT / "uninstall.sh"
        self.assertIn("--update-hook", update.read_text(encoding="utf-8"))
        self.assertIn("--disable-hook", uninstall.read_text(encoding="utf-8"))
        self.assertTrue(update.stat().st_mode & stat.S_IXUSR)
        self.assertTrue(uninstall.stat().st_mode & stat.S_IXUSR)
        text = INSTALLER.read_text(encoding="utf-8")
        disable = text[text.index("backend_disable_transition(){"):text.index("backend_uninstall_transition(){")]
        self.assertNotIn("remove_update_manager_section", disable)
        full = text[text.index("backend_uninstall_transition(){"):text.index("run_moonraker_transition(){")]
        self.assertIn("remove_update_manager_section", full)

    def test_no_argument_existing_checkout_is_enable_hook_without_implicit_checkout(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        start = text.index("# A no-argument call from ENABLE_PLUGIN")
        end = text.index('[ -f "$PLUGIN_DIR/VERSION" ]', start)
        body = text[start:end]
        self.assertIn("MODE=--enable-hook", body)
        self.assertIn('if [ "$REF_EXPLICIT" -eq 1 ]; then', body)
        explicit = body[body.index('if [ "$REF_EXPLICIT" -eq 1 ]; then'):body.index("MODE=--enable-hook")]
        self.assertIn("checkout -B", explicit)

    def test_no_moonraker_restart_primitive(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn("S65moonraker restart", text)
        self.assertIn("S65moonraker stop", text)
        self.assertIn("S65moonraker start", text)


if __name__ == "__main__":
    unittest.main()
