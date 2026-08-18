from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
LIFECYCLE = ROOT / "installer" / "z_calibration_backend_lifecycle.sh"
SHARED = ROOT / "moonraker" / "components" / "plugins_ad5x.py"
OBSERVER = ROOT / "moonraker" / "components" / "plugins_ad5x_zcal.py"
CONFIG = ROOT / "plugins_ad5x_zcal.moonraker.conf"


class ZCalibrationBackendLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.script = LIFECYCLE.read_text(encoding="utf-8")

    def test_standalone_assets_exist(self) -> None:
        self.assertTrue(OBSERVER.is_file())
        self.assertEqual(CONFIG.read_text(encoding="utf-8"), "[plugins_ad5x_zcal]\n")

    def test_lifecycle_never_deploys_shared_backend_host(self) -> None:
        assignments = "\n".join(
            line for line in self.script.splitlines() if "_DEST=" in line or "_SOURCE=" in line
        )
        self.assertNotIn("/plugins_ad5x.py", assignments)
        self.assertIn("plugins_ad5x_zcal.py", assignments)
        self.assertIn("plugins_ad5x_zcalibration.py", assignments)
        self.assertIn("zcal_backend.moonraker.conf", assignments)

    def test_shared_host_remains_feature_neutral(self) -> None:
        source = SHARED.read_text(encoding="utf-8")
        self.assertNotIn("Z_RECONCILE_ENDPOINT", source)
        self.assertNotIn("Z_DIAGNOSTICS_ENDPOINT", source)
        self.assertNotIn("plugins_ad5x_zcalibration", source)

    def test_target_runtime_contract_is_curl_only_and_git_free(self) -> None:
        executable_lines = [
            line.strip()
            for line in self.script.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertFalse(any(re.match(r"^wget(?:\s|$)", line) for line in executable_lines))
        self.assertNotIn("git checkout", self.script)
        self.assertNotIn("git reset", self.script)
        self.assertNotIn("git clean", self.script)
        self.assertNotIn("git fetch", self.script)
        self.assertIn("/usr/prog/curl-7.55.1-https/bin/curl", self.script)

    def test_backend_transition_does_not_reload_klipper_or_move_z(self) -> None:
        self.assertNotIn("FIRMWARE_RESTART", self.script)
        self.assertNotIn("SET_GCODE_OFFSET", self.script)
        self.assertNotIn("PROBE ", self.script)
        self.assertNotIn(" G0 ", self.script)
        self.assertNotIn(" G1 ", self.script)

    def test_shared_backend_is_transaction_invariant_not_owned_state(self) -> None:
        self.assertIn('SHARED_BEFORE="$(shared_signature', self.script)
        self.assertIn('[ "$SHARED_AFTER" = "$SHARED_BEFORE" ]', self.script)
        self.assertIn("shared_signature_at_adoption", self.script)
        self.assertNotIn("manifest_value shared_signature", self.script)

    def test_live_verifier_covers_all_standalone_endpoints(self) -> None:
        self.assertIn("/server/plugins_ad5x/z_calibration/snapshot", self.script)
        self.assertIn("/server/plugins_ad5x/z_calibration/reconcile", self.script)
        self.assertIn("/server/plugins_ad5x/z_calibration/diagnostics", self.script)
        self.assertIn('c.get("motion_owner") != "zmod"', self.script)
        self.assertIn('c.get("motion_actions_enabled") is not False', self.script)
        self.assertIn('c.get("offset_write_enabled") is not False', self.script)

    def test_lifecycle_is_transactional_and_restorable(self) -> None:
        self.assertIn("snapshot_file", self.script)
        self.assertIn("restore_file", self.script)
        self.assertIn("Rollback backup:", self.script)
        self.assertIn("ownership-state-restored", self.script)
        self.assertIn("install|update|repair|uninstall|status", self.script)

    def test_moonraker_stop_has_bounded_process_zero_gate(self) -> None:
        self.assertIn('MOONRAKER_STOP_TIMEOUT="${AD5X_MOONRAKER_STOP_TIMEOUT:-30}"', self.script)
        self.assertIn("moonraker_process_count(){", self.script)
        self.assertIn("wait_moonraker_stopped(){", self.script)
        self.assertIn('[ "$(moonraker_process_count)" -eq 0 ] && return 0', self.script)

    def test_install_waits_for_moonraker_exit_before_first_mutation(self) -> None:
        start = self.script.index('    install|update|repair)')
        end = self.script.index('    uninstall)', start)
        block = self.script[start:end]
        stop = block.index("stop_moonraker || fail 'Moonraker stop failed'")
        wait = block.index("wait_moonraker_stopped || fail 'Moonraker stop timeout'")
        mutate = block.index('copy_atomic "$OBSERVER_SOURCE" "$OBSERVER_DEST" 0644')
        self.assertLess(stop, wait)
        self.assertLess(wait, mutate)

    def test_uninstall_waits_for_moonraker_exit_before_restore(self) -> None:
        start = self.script.index('    uninstall)')
        end = self.script.index('\n        ;;\nesac', start)
        block = self.script[start:end]
        stop = block.index("stop_moonraker || fail 'Moonraker stop failed'")
        wait = block.index("wait_moonraker_stopped || fail 'Moonraker stop timeout'")
        restore = block.index('restore_file "$OBSERVER_DEST" observer.py "$ORIGINAL"')
        self.assertLess(stop, wait)
        self.assertLess(wait, restore)

    def test_rollback_waits_for_moonraker_exit_before_restore(self) -> None:
        start = self.script.index("rollback(){")
        end = self.script.index("\ntrap rollback", start)
        block = self.script[start:end]
        stop = block.index("stop_moonraker")
        wait = block.index("wait_moonraker_stopped")
        restore = block.index('restore_file "$OBSERVER_DEST" observer.py "$B"')
        self.assertLess(stop, wait)
        self.assertLess(wait, restore)


if __name__ == "__main__":
    unittest.main()
