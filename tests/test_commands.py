import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from tests._load_mbank_cli import load_module


class _CookieJarOK:
    def __init__(self, filename):
        self.filename = filename

    def save(self, **kwargs):
        _ = kwargs


class _CookieJarFail:
    def __init__(self, filename):
        self.filename = filename

    def save(self, **kwargs):
        _ = kwargs
        raise OSError('cannot write')


class _UA:
    def __init__(self, jar):
        self.cookie_jar = jar


class TestCommands(unittest.TestCase):
    def setUp(self):
        self.m = load_module()
        self.m.base_url = 'https://online.mbank.pl/pl'

    def test_parse_args_defaults_to_list(self):
        with mock.patch.object(self.m.sys, 'argv', ['mbank-cli']):
            args = self.m.parse_args()
        self.assertEqual(args.command, 'list')
        self.assertTrue(self.m.opt_config.endswith('/mbank-cli/config'))

    def test_parse_args_register_device_default_name(self):
        with mock.patch.object(self.m.sys, 'argv', ['mbank-cli', 'register-device']):
            args = self.m.parse_args()
        self.assertEqual(args.command, 'register-device')
        self.assertEqual(args.name, 'CLI')

    def test_parse_args_history_all(self):
        with mock.patch.object(self.m.sys, 'argv', ['mbank-cli', 'history', '--all', '--with-id']):
            args = self.m.parse_args()
        self.assertEqual(args.command, 'history')
        self.assertTrue(args.all)
        self.assertTrue(args.with_id)

    def test_parse_args_debug_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            debug_dir = f'{tmp}/dbg'
            with mock.patch.object(self.m.sys, 'argv', ['mbank-cli', '--debug', debug_dir, 'list']):
                args = self.m.parse_args()
            self.assertEqual(args.command, 'list')
            self.assertEqual(self.m.opt_debug_dir, debug_dir)
            self.assertTrue(self.m.os.path.isdir(debug_dir))

    def test_parse_args_rejects_suspicious_debug_dir(self):
        with mock.patch.object(self.m.sys, 'argv', ['mbank-cli', '--debug=-bad']):
            with self.assertRaises(SystemExit) as exc:
                self.m.parse_args()
        self.assertEqual(exc.exception.code, 1)

    def test_get_password_from_config_plain(self):
        self.m.global_config = {'password': 'sekret'}
        self.assertEqual(self.m.get_password_from_config(), 'sekret')

    def test_get_password_from_config_password_manager(self):
        self.m.global_config = {'passwordmanager': 'echo from-pm'}
        completed = SimpleNamespace(stdout='from-pm\nextra\n')
        with mock.patch.object(self.m.subprocess, 'run', return_value=completed):
            self.assertEqual(self.m.get_password_from_config(), 'from-pm')

    def test_get_password_from_config_password_manager_error(self):
        self.m.global_config = {'passwordmanager': 'boom'}
        with mock.patch.object(self.m.subprocess, 'run', side_effect=RuntimeError('x')):
            with self.assertRaises(SystemExit) as exc:
                self.m.get_password_from_config()
        self.assertEqual(exc.exception.code, 4)

    def test_get_password_from_config_tty(self):
        self.m.global_config = {}
        with mock.patch.object(self.m.sys.stdin, 'isatty', return_value=True), mock.patch.object(
            self.m.getpass, 'getpass', return_value='typed'
        ):
            self.assertEqual(self.m.get_password_from_config(), 'typed')

    def test_get_password_from_config_missing_non_tty(self):
        self.m.global_config = {}
        self.m.opt_config = '/tmp/config'
        with mock.patch.object(self.m.sys.stdin, 'isatty', return_value=False):
            with self.assertRaises(SystemExit) as exc:
                self.m.get_password_from_config()
        self.assertEqual(exc.exception.code, 1)

    def test_do_activate_profile_invalid_name(self):
        login = {'profiles': {'personal': ['T']}, 'headers': {}}
        with self.assertRaises(SystemExit) as exc:
            self.m.do_activate_profile(login, 'missing')
        self.assertEqual(exc.exception.code, 1)

    def test_do_activate_profile_ambiguous(self):
        login = {'profiles': {'biz': ['A', 'B']}, 'headers': {}}
        with self.assertRaises(SystemExit) as exc:
            self.m.do_activate_profile(login, 'biz')
        self.assertEqual(exc.exception.code, 3)

    def test_do_activate_profile_success(self):
        login = {'profiles': {'personal': ['T']}, 'headers': {'X-Tab-Id': '1'}}
        with mock.patch.object(self.m, 'download') as download, mock.patch.object(self.m, 'do_lazy_logout') as lazy:
            self.m.do_activate_profile(login, 'personal')

        req = download.call_args[0][0]
        self.assertEqual(req.get_method(), 'POST')
        self.assertIn(b'profileCode=I', req.data)
        lazy.assert_called_once_with(login)

    def test_do_lazy_logout_false(self):
        with mock.patch.object(self.m, 'download', return_value={'content': '{"lazy": false}'}):
            with self.assertRaises(SystemExit) as exc:
                self.m.do_lazy_logout({'headers': {}})
        self.assertEqual(exc.exception.code, 3)

    def test_do_logout_user_not_logged_in(self):
        with mock.patch.object(self.m, 'do_login', return_value=None), mock.patch.object(
            self.m, 'clear_temp_cookies'
        ) as clear:
            with self.assertRaises(SystemExit) as exc:
                self.m.do_logout(maybe=False)
        self.assertEqual(exc.exception.code, 1)
        clear.assert_called_once()

    def test_do_logout_maybe_true_when_not_logged_in(self):
        with mock.patch.object(self.m, 'do_login', return_value=None), mock.patch.object(
            self.m, 'clear_temp_cookies'
        ) as clear:
            self.m.do_logout(maybe=True)
        clear.assert_called_once()

    def test_do_logout_success(self):
        login = {'url': 'https://online.mbank.pl/pl', 'headers': {'X': '1'}}
        with mock.patch.object(self.m, 'do_login', return_value=login), mock.patch.object(
            self.m, 'do_lazy_logout'
        ) as lazy, mock.patch.object(self.m, 'download') as download, mock.patch.object(
            self.m, 'clear_temp_cookies'
        ) as clear:
            self.m.do_logout(maybe=False)

        lazy.assert_called_once_with(login)
        download.assert_called_once()
        clear.assert_called_once()

    def test_cookiejar_sanity_check_missing_ua(self):
        self.m.ua = None
        with self.assertRaises(SystemExit) as exc:
            self.m.cookiejar_sanity_check_for_register_device()
        self.assertEqual(exc.exception.code, 1)

    def test_cookiejar_sanity_check_dev_null(self):
        self.m.ua = _UA(_CookieJarOK('/dev/null'))
        with self.assertRaises(SystemExit) as exc:
            self.m.cookiejar_sanity_check_for_register_device()
        self.assertEqual(exc.exception.code, 1)

    def test_cookiejar_sanity_check_save_error(self):
        self.m.ua = _UA(_CookieJarFail('/tmp/cj'))
        with self.assertRaises(SystemExit) as exc:
            self.m.cookiejar_sanity_check_for_register_device()
        self.assertEqual(exc.exception.code, 4)

    def test_cookiejar_sanity_check_ok(self):
        self.m.ua = _UA(_CookieJarOK('/tmp/cj'))
        self.m.cookiejar_sanity_check_for_register_device()

    def test_main_dispatch_configure(self):
        self.m.opt_config = '/tmp/config'
        self.m.opt_cookie_jar = '/tmp/cookies'
        args = SimpleNamespace(command='configure')

        with mock.patch.object(self.m, 'parse_args', return_value=args), mock.patch.object(
            self.m, 'cmd_configure'
        ) as cfg, mock.patch.object(self.m, 'initialize') as init:
            self.m.main()

        cfg.assert_called_once_with('/tmp/config', '/tmp/cookies')
        init.assert_not_called()

    def test_main_dispatch_list(self):
        args = SimpleNamespace(command='list')
        with mock.patch.object(self.m, 'parse_args', return_value=args), mock.patch.object(
            self.m, 'initialize'
        ) as init, mock.patch.object(self.m, 'do_login', return_value={'headers': {}}) as login, mock.patch.object(
            self.m, 'do_list'
        ) as do_list:
            self.m.main()

        init.assert_called_once()
        login.assert_called_once_with()
        do_list.assert_called_once_with({'headers': {}})

    def test_main_dispatch_history_all(self):
        args = SimpleNamespace(command='history', start_date='2026-01-01', end_date='2026-02-01', with_id=True, all=True)
        with mock.patch.object(self.m, 'parse_args', return_value=args), mock.patch.object(
            self.m, 'initialize'
        ) as init, mock.patch.object(self.m, 'do_login', return_value={'headers': {}}) as login, mock.patch.object(
            self.m, 'do_history'
        ) as history:
            self.m.main()

        init.assert_called_once()
        login.assert_called_once_with()
        history.assert_called_once_with(
            {'headers': {}},
            start_date='2026-01-01',
            end_date='2026-02-01',
            with_id=True,
            include_all=True,
        )

    def test_main_dispatch_register_device(self):
        args = SimpleNamespace(command='register-device', name='Laptop')
        with mock.patch.object(self.m, 'parse_args', return_value=args), mock.patch.object(
            self.m, 'initialize'
        ) as init, mock.patch.object(self.m, 'cookiejar_sanity_check_for_register_device') as sanity, mock.patch.object(
            self.m, 'do_logout'
        ) as logout, mock.patch.object(self.m, 'do_login') as login:
            self.m.main()

        init.assert_called_once()
        sanity.assert_called_once_with()
        logout.assert_called_once_with(maybe=True)
        login.assert_called_once_with(register_device='Laptop')


if __name__ == '__main__':
    unittest.main()
