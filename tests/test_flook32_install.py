import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
INSTALL = ROOT / 'integrations/flook32/install.sh'

class FlookInstallerTests(unittest.TestCase):
    def test_installer_has_no_second_host_python_dependency(self):
        text = INSTALL.read_text(encoding='utf-8')
        self.assertNotIn('HOST_PYTHON=', text)
        self.assertNotIn('AD5X_HOST_PYTHON', text)
        self.assertIn('RUNTIME_PY', text)
        self.assertIn('MIGRATE_CFG', text)
        self.assertIn('/usr/prog/Python-3.8.2/lib', text)
        self.assertIn('/usr/prog/openssl-1.0.2d/lib', text)
        self.assertIn('/usr/prog/libffi-3.4.4/lib', text)

    def test_install_preserves_existing_user_include_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            target = t / 'flook32'
            extras = t / 'klipper/klippy/extras'
            gitinfo = t / 'klipper/.git/info'
            extras.mkdir(parents=True)
            gitinfo.mkdir(parents=True)
            target.mkdir()
            original_cfg = '[flook32]\n\n[temperature_sensor chamber]\nsensor_type: flook32\ncustom_marker: keep-me\n'
            (target / 'flook32.cfg').write_text(original_cfg, encoding='utf-8')
            power = t / 'power_on.sh'
            power.write_text('#!/bin/sh\necho existing\n', encoding='utf-8')
            user = t / 'user.cfg'
            include = '[include plugins/flook32/flook32.cfg]'
            user.write_text(include + '\n', encoding='utf-8')
            plugins = t / 'plugins.cfg'
            plugins.write_text(include + '\n', encoding='utf-8')
            env = os.environ.copy()
            env.update({
                'AD5X_FLOOK_DIR': str(target),
                'AD5X_POWER_ON': str(power),
                'AD5X_FLOOK_BACKUPS': str(t / 'backups'),
                'AD5X_KLIPPER_REPO_ROOT': str(t / 'klipper'),
                'AD5X_KLIPPER_EXTRAS_DIR': str(extras),
                'AD5X_FLOOK_KLIPPER_DEST': str(extras / 'flook32.py'),
                'AD5X_KLIPPER_INCLUDES': str(plugins),
                'AD5X_USER_CFG': str(user),
                'AD5X_KLIPPER_PYTHON': sys.executable,
            })
            for _ in range(2):
                subprocess.run([str(INSTALL)], cwd=ROOT, env=env,
                               check=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
            self.assertEqual(user.read_text(encoding='utf-8'), include + '\n')
            migrated_cfg = (target / 'flook32.cfg').read_text(encoding='utf-8')
            self.assertIn('[temperature_sensor _flook32_chamber]\n', migrated_cfg)
            self.assertNotIn('[temperature_sensor chamber]\n', migrated_cfg)
            self.assertIn('custom_marker: keep-me\n', migrated_cfg)
            self.assertNotIn(include, plugins.read_text(encoding='utf-8'))
            self.assertEqual(plugins.read_text(encoding='utf-8').count(include), 0)
            self.assertEqual(power.read_text(encoding='utf-8').count('FLOOK32_BOOT_ENSURE >>>'), 1)
            self.assertIn('ensure.sh --boot', power.read_text(encoding='utf-8'))
            self.assertEqual((extras / 'flook32.py').resolve(), (target / 'flook32.py').resolve())
            self.assertIn('/klippy/extras/flook32.py', (gitinfo / 'exclude').read_text(encoding='utf-8'))

    def test_ensure_uses_plugins_cfg_when_user_include_is_absent(self):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            target = t / 'flook32'
            extras = t / 'klipper/klippy/extras'
            gitinfo = t / 'klipper/.git/info'
            extras.mkdir(parents=True); gitinfo.mkdir(parents=True); target.mkdir()
            for src, name in ((ROOT/'integrations/flook32/klipper/flook32.py','flook32.py'),
                              (ROOT/'integrations/flook32/klipper/flook32.cfg','flook32.cfg'),
                              (ROOT/'integrations/flook32/scripts/ensure.sh','ensure.sh')):
                (target/name).write_bytes(src.read_bytes())
            (target/'ensure.sh').chmod(0o755)
            plugins = t/'plugins.cfg'; user=t/'user.cfg'; user.write_text('', encoding='utf-8')
            env=os.environ.copy(); env.update({
                'AD5X_FLOOK_DIR': str(target),
                'AD5X_KLIPPER_REPO_ROOT': str(t/'klipper'),
                'AD5X_KLIPPER_EXTRAS_DIR': str(extras),
                'AD5X_FLOOK_KLIPPER_DEST': str(extras/'flook32.py'),
                'AD5X_KLIPPER_INCLUDES': str(plugins),
                'AD5X_USER_CFG': str(user),
                'AD5X_KLIPPER_PYTHON': '/bin/true',
            })
            subprocess.run([str(target/'ensure.sh'), '--boot'], env=env, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            include='[include plugins/flook32/flook32.cfg]'
            self.assertEqual(plugins.read_text(encoding='utf-8').count(include), 1)

if __name__ == '__main__': unittest.main()
