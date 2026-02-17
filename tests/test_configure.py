import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._load_mbank_cli import load_module


class TestConfigure(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_cmd_configure_creates_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = f'{tmp}/config'
            cookie_path = f'{tmp}/cookies/session.cookies'

            with mock.patch.object(self.m, 'get_tz_country_guess', return_value='pl'), mock.patch(
                'builtins.input', side_effect=['', 'john', cookie_path]
            ), mock.patch.object(self.m.getpass, 'getpass', return_value='secret'):
                self.m.cmd_configure(cfg_path, None)

            content = Path(cfg_path).read_text(encoding='utf-8')
            self.assertIn('CookieJar ', content)
            self.assertIn('Country PL\n', content)
            self.assertIn('Login john\n', content)
            self.assertIn('Password secret\n', content)

    def test_cmd_configure_cancel_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = f'{tmp}/config'
            Path(cfg_path).write_text('x', encoding='utf-8')

            with mock.patch('builtins.input', side_effect=['n']):
                with self.assertRaises(SystemExit) as exc:
                    self.m.cmd_configure(cfg_path, None)

            self.assertEqual(exc.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
