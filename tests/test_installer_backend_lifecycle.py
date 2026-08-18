from __future__ import annotations

import hashlib
import os
import shlex
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
BACKEND = ROOT / "moonraker" / "components" / "plugins_ad5x.py"
CONFIG = ROOT / "plugins_ad5x.moonraker.conf"
RUNTIME_HELPER = ROOT / "installer" / "z_calibration_runtime.sh"
RC_LIFECYCLE = ROOT / "installer" / "z_calibration_rc_lifecycle.sh"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BackendInstallerLifecycleTests(unittest.TestCase):
    maxDiff = None

    def run_shell(self, body: str, tmp: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "AD5X_INSTALLER_FUNCTIONS_ONLY": "1",
                "AD5X_PLUGIN_DIR": str(ROOT),
                "AD5X_STATE_DIR": str(tmp / "state-root"),
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
        (tmp / "state-root" / "state").mkdir(parents=True, exist_ok=True)
        command = f'. "{INSTALLER}"\n{body}\n'
        return subprocess.run(
            ["sh", "-c", command],
            text=True,
            capture_output=True,
            env=env,
            check=check,
        )

    def run_idle_check(self, tmp: Path, *, payload: str = "", curl_rc: int = 0) -> subprocess.CompletedProcess[str]:
        if curl_rc:
            body = f"curl(){{ return {curl_rc}; }}\ncheck_idle"
        else:
            body = f"curl(){{ printf '%s' {shlex.quote(payload)}; }}\ncheck_idle"
        return self.run_shell(body, tmp, check=False)

    @staticmethod
    def print_stats_payload(state: str) -> str:
        return '{"result":{"status":{"print_stats":{"state":"' + state + '"}}}}'

    def test_target_shell_http_contract_is_zmod_curl_not_wget(self) -> None:
        production_shell = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (INSTALLER, RUNTIME_HELPER, RC_LIFECYCLE)
        )
        self.assertNotIn("wget", production_shell.lower())
        self.assertIn("/usr/bin/curl", production_shell)
        self.assertIn("/usr/prog/curl-7.55.1-https/bin/curl", production_shell)
        self.assertIn("ad5x_http_get", production_shell)

    def test_idle_http_unavailable_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_idle_check(Path(td), curl_rc=7)
            self.assertNotEqual(result.returncode, 0)

    def test_idle_empty_response_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_idle_check(Path(td), payload="")
            self.assertNotEqual(result.returncode, 0)

    def test_idle_invalid_json_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_idle_check(Path(td), payload="not-json")
            self.assertNotEqual(result.returncode, 0)

    def test_idle_missing_print_stats_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            payload = '{"result":{"status":{"print_stats":{}}}}'
            result = self.run_idle_check(Path(td), payload=payload)
            self.assertNotEqual(result.returncode, 0)

    def test_idle_printing_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_idle_check(Path(td), payload=self.print_stats_payload("printing"))
            self.assertNotEqual(result.returncode, 0)

    def test_idle_paused_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_idle_check(Path(td), payload=self.print_stats_payload("paused"))
            self.assertNotEqual(result.returncode, 0)

    def test_idle_standby_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_idle_check(Path(td), payload=self.print_stats_payload("standby"))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_idle_confirmed_terminal_states_pass(self) -> None:
        for state in ("complete", "error", "cancelled"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as td:
                result = self.run_idle_check(Path(td), payload=self.print_stats_payload(state))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_idle_unknown_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_idle_check(Path(td), payload=self.print_stats_payload("mystery"))
            self.assertNotEqual(result.returncode, 0)

    def test_idle_gate_precedes_mutations_and_service_transition(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")

        uninstall_start = text.index('if [ "$MODE" = --uninstall ]; then')
        install_start = text.index('\ncheck_idle\nvalidate_backend_source', uninstall_start) + 1
        uninstall = text[uninstall_start:install_start]
        self.assertLess(uninstall.index("check_idle"), uninstall.index('remove_lines "$KLIPPER_INCLUDES"'))
        self.assertLess(
            uninstall.index("check_idle"),
            uninstall.index("run_moonraker_transition backend_uninstall_transition"),
        )

        install = text[install_start:]
        self.assertTrue(install.startswith("check_idle\n"))
        self.assertLess(install.index("check_idle"), install.index('remove_lines "$KLIPPER_INCLUDES"'))
        self.assertLess(install.index("check_idle"), install.index("install_power_on_hook"))
        self.assertLess(
            install.index("check_idle"),
            install.index("run_moonraker_transition backend_install_transition"),
        )

    def test_backend_source_validation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_shell("backend_source_valid", Path(td), check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_managed_copy_destination_and_atomic_path(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('/opt/config/base/moonraker/components/plugins_ad5x.py', text)
        self.assertIn('TMP="$MOONRAKER_COMPONENTS_DIR/.plugins_ad5x.py.tmp.$$"', text)
        self.assertIn('chmod 0644 "$TMP"', text)
        self.assertIn('mv -f "$TMP" "$BACKEND_DEST"', text)
        self.assertLess(text.index('chmod 0644 "$TMP"'), text.index('mv -f "$TMP" "$BACKEND_DEST"'))

    def test_absent_destination_snapshot_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_shell(
                'B="$AD5X_STATE_DIR/backup"; mkdir -p "$B"; '
                'snapshot "$BACKEND_DEST" backend-runtime.py; '
                'test -f "$B/.absent-backend-runtime.py"; '
                'printf x >"$BACKEND_DEST"; '
                'restore_snapshot "$BACKEND_DEST" backend-runtime.py; '
                'test ! -e "$BACKEND_DEST"',
                tmp,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_previous_destination_snapshot_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "moonraker" / "components" / "plugins_ad5x.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("old-runtime\n", encoding="utf-8")
            result = self.run_shell(
                'B="$AD5X_STATE_DIR/backup"; mkdir -p "$B"; '
                'snapshot "$BACKEND_DEST" backend-runtime.py; '
                'printf new >"$BACKEND_DEST"; '
                'restore_snapshot "$BACKEND_DEST" backend-runtime.py; '
                'grep -Fqx old-runtime "$BACKEND_DEST"',
                tmp,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_managed_destination_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "moonraker" / "components" / "plugins_ad5x.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("managed-old\n", encoding="utf-8")
            marker = tmp / "state-root" / "state" / "backend-runtime.sha256"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(sha256(dest) + "\n", encoding="utf-8")
            result = self.run_shell("deploy_backend_managed_copy", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(dest.read_bytes(), BACKEND.read_bytes())
            self.assertEqual(marker.read_text().strip(), sha256(BACKEND))

    def test_unexpected_destination_fails_safe(self) -> None:
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

    def test_uninstall_removes_backend_activation_runtime_and_bytecode(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "moonraker" / "components" / "plugins_ad5x.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(BACKEND.read_bytes())
            marker = tmp / "state-root" / "state" / "backend-runtime.sha256"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(sha256(dest) + "\n", encoding="utf-8")
            pycache = dest.parent / "__pycache__"
            pycache.mkdir()
            (pycache / "plugins_ad5x.cpython-312.pyc").write_bytes(b"x")
            (tmp / "plugins.moonraker.conf").write_text(
                "[include plugins/ad5x_custom/ad5x_custom.moonraker.conf]\n"
                "[include plugins/ad5x_custom/plugins_ad5x.moonraker.conf]\n",
                encoding="utf-8",
            )
            result = self.run_shell("backend_uninstall_transition", tmp, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(dest.exists())
            self.assertFalse(marker.exists())
            self.assertFalse(any(pycache.glob("plugins_ad5x*.pyc")))
            self.assertNotIn("plugins/ad5x_custom/", (tmp / "plugins.moonraker.conf").read_text())

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
            self.assertEqual(
                log.read_text().splitlines(),
                ["stop", "wait-zero", "transition", "start", "http", "ready", "verify"],
            )

    def test_http_availability_is_not_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_shell(
                "klippy_ready_from_json '{\"result\":{\"klippy_connected\":false,\"klippy_state\":\"disconnected\"}}'",
                tmp,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_startup_is_not_final_ready(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_shell(
                "klippy_ready_from_json '{\"result\":{\"klippy_connected\":true,\"klippy_state\":\"startup\"}}'",
                Path(td),
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_ready_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_shell(
                "klippy_ready_from_json '{\"result\":{\"klippy_state\":\"ready\",\"klippy_connected\":true}}'",
                Path(td),
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_readiness_timeout_fails_safely(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            body = '''
moonraker_server_info(){ printf '%s' '{"result":{"klippy_connected":true,"klippy_state":"startup"}}'; }
sleep(){ :; }
wait_klippy_ready 2
'''
            result = self.run_shell(body, Path(td), check=False)
            self.assertNotEqual(result.returncode, 0)

    def test_no_moonraker_restart_primitive(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn("S65moonraker restart", text)
        self.assertIn("S65moonraker stop", text)
        self.assertIn("S65moonraker start", text)

    def test_status_distinguishes_service_unavailable(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("[UNAVAILABLE] Moonraker component presence (runtime service unavailable)", text)
        self.assertIn("[UNAVAILABLE] backend snapshot (runtime service unavailable)", text)

    def test_apply_only_is_explicit_runtime_apply_path(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('exec "$PLUGIN_DIR/install.sh" --apply-only', text)
        self.assertIn('run_moonraker_transition backend_install_transition verify_backend_runtime', text)
        refresh = text[text.index('if [ "$MODE" = --refresh-only ]'):text.index('if [ "$MODE" = --status ]')]
        self.assertNotIn("deploy_backend_managed_copy", refresh)


if __name__ == "__main__":
    unittest.main()
