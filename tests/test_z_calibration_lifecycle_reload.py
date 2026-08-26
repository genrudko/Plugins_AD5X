from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "installer" / "z_calibration_runtime.sh"
INSTALLER = ROOT / "install.sh"


class ZCalibrationReloadShellContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helper = HELPER.read_text(encoding="utf-8")
        self.installer = INSTALLER.read_text(encoding="utf-8")

    def test_product_lifecycle_uses_full_klippy_host_restart_for_python_extras(self) -> None:
        self.assertIn("zcal_rc_klippy_host_restart || return 1", self.helper)
        self.assertIn("/opt/config/mod/.shell/zremote.sh", self.helper)
        self.assertIn("/usr/data/config/mod/.shell/klipper13.sh", self.helper)
        self.assertIn("wait_klippy_ready", self.helper)
        self.assertNotIn("S65moonraker restart", self.helper)

    def test_firmware_restart_rejects_stale_pre_restart_ready_sample(self) -> None:
        start = self.helper.index("zcal_rc_firmware_restart(){")
        end = self.helper.index("run_moonraker_transition(){", start)
        body = self.helper[start:end]
        post = body.index("/printer/firmware_restart")
        settle = body.index("sleep 2", post)
        wait = body.index("wait_klippy_ready || return 1", settle)
        confirm_delay = body.index("sleep 1", wait)
        confirm = body.index("klippy_ready_from_json", confirm_delay)
        self.assertEqual([post, settle, wait, confirm_delay, confirm], sorted([post, settle, wait, confirm_delay, confirm]))

    def test_generic_moonraker_transition_is_overridden_with_klipper_reload(self) -> None:
        start = self.helper.index("run_moonraker_transition(){")
        end = self.helper.index("restore_moonraker_after_rollback(){", start)
        body = self.helper[start:end]
        order = [
            body.index("wait_moonraker_stopped"),
            body.index('"$TRANSITION_FN"'),
            body.index("start_moonraker"),
            body.index("wait_moonraker_http"),
            body.index("zcal_rc_klippy_host_restart"),
            body.index('"$VERIFY_FN"'),
        ]
        self.assertEqual(order, sorted(order))

    def test_rollback_reloads_restored_klipper_state(self) -> None:
        start = self.helper.index("restore_moonraker_after_rollback(){")
        end = self.helper.index("verify_backend_absent(){", start)
        body = self.helper[start:end]
        self.assertIn("start_moonraker", body)
        self.assertIn("zcal_rc_klippy_host_restart", body)
        self.assertIn("wait_klippy_ready", body)

    def test_uninstall_verifies_effective_baseline_before_dropping_manifest(self) -> None:
        start = self.helper.index("verify_backend_absent(){")
        end = self.helper.index("zcal_core_deploy_managed_copy(){", start)
        body = self.helper[start:end]
        self.assertLess(
            body.index("zcal_rc_live_verify_uninstalled"),
            body.index("zcal_rc_finalize_uninstall"),
        )
        self.assertIn("--keep-state", self.helper)
        self.assertIn("verify-uninstalled", self.helper)
        self.assertIn("finalize-uninstall", self.helper)

    def test_host_restart_clears_python_module_cache_and_live_verify_checks_loaded_source(self) -> None:
        start = self.helper.index("zcal_rc_klippy_host_restart(){")
        end = self.helper.index("run_moonraker_transition(){", start)
        body = self.helper[start:end]
        self.assertIn("/run/klipper.pid", body)
        self.assertIn("kill \"$PID\"", body)
        self.assertIn("/usr/data/config/mod/.shell/klipper13.sh", body)
        self.assertIn("loaded_source_sha256", self.helper)
        self.assertIn("EXPECTED_ANCHOR_HASH", self.helper)

    def test_no_fixed_sleep_restart_primitive_is_reintroduced(self) -> None:
        self.assertNotIn("/etc/init.d/S65moonraker restart", self.helper)
        self.assertNotIn("S65moonraker restart", self.helper)
        self.assertIn("stop_moonraker", self.helper)
        self.assertIn("start_moonraker", self.helper)

    def test_reload_logic_does_not_mutate_git_worktrees(self) -> None:
        self.assertNotIn("git checkout", self.helper)
        self.assertNotIn("git reset", self.helper)


if __name__ == "__main__":
    unittest.main()
