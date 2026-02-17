import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'mbank-cli.py'


class TestCliBlackBox(unittest.TestCase):
    def run_cli(self, *args, input_text=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_help(self):
        proc = self.run_cli('--help')
        self.assertEqual(proc.returncode, 0)
        self.assertIn('List accounts', proc.stdout)
        self.assertIn('register-device', proc.stdout)

    def test_version(self):
        proc = self.run_cli('--version')
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), 'mbank-cli python-port')

    def test_invalid_command(self):
        proc = self.run_cli('future')
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid choice: 'future'", proc.stderr)

    def test_missing_config_returns_user_error(self):
        proc = self.run_cli('--config', '/tmp/definitely-missing-config', 'list')
        self.assertEqual(proc.returncode, 1)
        self.assertIn('missing configuration file', proc.stderr)

    def test_debug_writes_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            debug_dir = Path(tmp) / 'dbg'
            missing_cfg = Path(tmp) / 'missing-config'

            proc = self.run_cli('--debug', str(debug_dir), '--config', str(missing_cfg), 'list')

            self.assertEqual(proc.returncode, 1)
            log_path = debug_dir / 'log'
            self.assertTrue(log_path.exists())
            content = log_path.read_text(encoding='utf-8')
            self.assertIn('missing configuration file', content)


if __name__ == '__main__':
    unittest.main()
