import subprocess
import unittest
from unittest import mock

from tests._load_wrapper import load_wrapper


class TestHttpWrapper(unittest.TestCase):
    def load_app(self, **env):
        defaults = {
            'MBANK_WRAPPER_API_KEY': 'secret-key',
            'MBANK_WRAPPER_ALLOW_IPS': '',
            'MBANK_WRAPPER_DENY_IPS': '',
            'MBANK_WRAPPER_TRUST_XFF': '0',
        }
        defaults.update(env)
        mod = load_wrapper(defaults)
        return mod, mod.app.test_client()

    def test_parse_networks_supports_single_ipv4_and_ipv6(self):
        mod, _ = self.load_app()
        nets = mod._parse_networks('127.0.0.1,::1')
        self.assertEqual(len(nets), 2)
        self.assertEqual(str(nets[0]), '127.0.0.1/32')
        self.assertEqual(str(nets[1]), '::1/128')

    def test_parse_networks_supports_cidr(self):
        mod, _ = self.load_app()
        nets = mod._parse_networks('10.0.0.0/8,2001:db8::/32')
        self.assertEqual(str(nets[0]), '10.0.0.0/8')
        self.assertEqual(str(nets[1]), '2001:db8::/32')

    def test_parse_networks_invalid_raises(self):
        mod, _ = self.load_app()
        with self.assertRaises(ValueError):
            mod._parse_networks('not-an-ip')

    def test_misconfigured_empty_api_key_returns_500(self):
        mod, client = self.load_app(MBANK_WRAPPER_API_KEY='')
        resp = client.get('/accounts')
        self.assertEqual(resp.status_code, 500)
        self.assertIn('misconfigured', resp.get_json()['error'].lower())

    def test_unauthorized_when_missing_api_key(self):
        _, client = self.load_app()
        resp = client.get('/accounts', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 401)

    def test_unauthorized_when_wrong_api_key(self):
        _, client = self.load_app()
        resp = client.get('/accounts?api_key=wrong', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 401)

    def test_auth_via_header(self):
        mod, client = self.load_app()
        mod._run_cli = lambda args: (0, 'ok\n', '')
        resp = client.get('/accounts', headers={'X-API-Key': 'secret-key'}, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), 'ok\n')

    def test_auth_via_query(self):
        mod, client = self.load_app()
        mod._run_cli = lambda args: (0, 'ok\n', '')
        resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 200)

    def test_auth_via_post_form(self):
        mod, client = self.load_app()
        mod._run_cli = lambda args: (0, 'ok\n', '')
        resp = client.post('/accounts', data={'api_key': 'secret-key'}, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 200)

    def test_auth_via_post_json(self):
        mod, client = self.load_app()
        mod._run_cli = lambda args: (0, 'ok\n', '')
        resp = client.post('/accounts', json={'api_key': 'secret-key'}, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 200)

    def test_allow_list_blocks_unknown_ip(self):
        _, client = self.load_app(MBANK_WRAPPER_ALLOW_IPS='127.0.0.1/32')
        resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '10.0.0.2'})
        self.assertEqual(resp.status_code, 403)

    def test_allow_list_allows_known_ip(self):
        mod, client = self.load_app(MBANK_WRAPPER_ALLOW_IPS='127.0.0.1/32')
        mod._run_cli = lambda args: (0, 'ok\n', '')
        resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 200)

    def test_deny_list_has_precedence(self):
        _, client = self.load_app(MBANK_WRAPPER_ALLOW_IPS='10.0.0.0/8', MBANK_WRAPPER_DENY_IPS='10.0.0.2/32')
        resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '10.0.0.2'})
        self.assertEqual(resp.status_code, 403)

    def test_xff_trusted_when_enabled(self):
        mod, client = self.load_app(MBANK_WRAPPER_TRUST_XFF='1', MBANK_WRAPPER_ALLOW_IPS='10.10.10.10/32')
        mod._run_cli = lambda args: (0, 'ok\n', '')
        resp = client.get(
            '/accounts?api_key=secret-key',
            headers={'X-Forwarded-For': '10.10.10.10, 127.0.0.1'},
            environ_overrides={'REMOTE_ADDR': '127.0.0.1'},
        )
        self.assertEqual(resp.status_code, 200)

    def test_xff_ignored_when_disabled(self):
        _, client = self.load_app(MBANK_WRAPPER_TRUST_XFF='0', MBANK_WRAPPER_ALLOW_IPS='10.10.10.10/32')
        resp = client.get(
            '/accounts?api_key=secret-key',
            headers={'X-Forwarded-For': '10.10.10.10'},
            environ_overrides={'REMOTE_ADDR': '127.0.0.1'},
        )
        self.assertEqual(resp.status_code, 403)

    def test_xff_invalid_ip_is_forbidden_when_trusted(self):
        _, client = self.load_app(MBANK_WRAPPER_TRUST_XFF='1')
        resp = client.get(
            '/accounts?api_key=secret-key',
            headers={'X-Forwarded-For': 'not-an-ip, 127.0.0.1'},
            environ_overrides={'REMOTE_ADDR': '127.0.0.1'},
        )
        self.assertEqual(resp.status_code, 403)

    def test_deny_list_only_blocks_and_other_ips_work(self):
        mod, client = self.load_app(MBANK_WRAPPER_DENY_IPS='10.0.0.2/32')
        mod._run_cli = lambda args: (0, 'ok\n', '')
        blocked = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '10.0.0.2'})
        allowed = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '10.0.0.3'})
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(allowed.status_code, 200)

    def test_accounts_runs_list(self):
        mod, client = self.load_app()
        called = {}

        def fake_run(args):
            called['args'] = args
            return (0, 'line\n', '')

        mod._run_cli = fake_run
        resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(called['args'], ['list'])

    def test_history_runs_history_all(self):
        mod, client = self.load_app()
        called = {}

        def fake_run(args):
            called['args'] = args
            return (0, 'line\n', '')

        mod._run_cli = fake_run
        resp = client.post('/history', json={'api_key': 'secret-key'}, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(called['args'], ['history', '--all'])

    def test_fixed_command_ignores_query_injection(self):
        mod, client = self.load_app()
        called = {}

        def fake_run(args):
            called['args'] = args
            return (0, 'ok\n', '')

        mod._run_cli = fake_run
        resp = client.get(
            '/accounts?api_key=secret-key&cmd=logout&args=--all',
            environ_overrides={'REMOTE_ADDR': '127.0.0.1'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(called['args'], ['list'])

    def test_success_returns_plain_output_and_exit_header(self):
        mod, client = self.load_app()
        mod._run_cli = lambda args: (0, 'abc\n', '')
        resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get('X-Exit-Code'), '0')
        self.assertEqual(resp.headers.get('Content-Type'), 'text/plain; charset=utf-8')
        self.assertEqual(resp.get_data(as_text=True), 'abc\n')

    def test_cli_failure_uses_stderr(self):
        mod, client = self.load_app()
        mod._run_cli = lambda args: (2, 'out\n', 'err\n')
        resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.headers.get('X-Exit-Code'), '2')
        self.assertEqual(resp.get_data(as_text=True), 'err\n')

    def test_cli_failure_falls_back_to_stdout_when_stderr_empty(self):
        mod, client = self.load_app()
        mod._run_cli = lambda args: (2, 'out-only\n', '')
        resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.get_data(as_text=True), 'out-only\n')

    def test_timeout_returns_504(self):
        mod, client = self.load_app()

        def fake_run(args):
            raise subprocess.TimeoutExpired(cmd=['python3', 'mbank-cli.py'], timeout=123)

        mod._run_cli = fake_run
        resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 504)

    def test_lock_returns_429_when_busy(self):
        mod, client = self.load_app()
        acquired = mod._command_lock.acquire(blocking=False)
        self.assertTrue(acquired)
        try:
            resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
            self.assertEqual(resp.status_code, 429)
        finally:
            mod._command_lock.release()

    def test_invalid_ip_format_is_forbidden(self):
        _, client = self.load_app()
        resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': 'invalid-ip'})
        self.assertEqual(resp.status_code, 403)

    def test_rate_limit_blocks_third_request_in_window(self):
        mod, client = self.load_app()
        mod._run_cli = lambda args: (0, 'ok\n', '')
        with mock.patch.object(mod.time, 'monotonic', side_effect=[100.0, 100.2, 100.4]):
            r1 = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
            r2 = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
            r3 = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r3.status_code, 429)
        self.assertEqual(r3.headers.get('Retry-After'), '10')

    def test_rate_limit_resets_after_window(self):
        mod, client = self.load_app()
        mod._run_cli = lambda args: (0, 'ok\n', '')
        with mock.patch.object(mod.time, 'monotonic', side_effect=[100.0, 100.1, 111.0]):
            r1 = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
            r2 = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
            r3 = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r3.status_code, 200)

    def test_rate_limit_disabled_when_count_zero(self):
        mod, client = self.load_app(MBANK_WRAPPER_RATE_LIMIT_COUNT='0')
        mod._run_cli = lambda args: (0, 'ok\n', '')
        for _ in range(5):
            resp = client.get('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
            self.assertEqual(resp.status_code, 200)

    def test_method_not_allowed_for_put(self):
        _, client = self.load_app()
        resp = client.put('/accounts?api_key=secret-key', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 405)

    def test_unknown_route_404(self):
        _, client = self.load_app()
        resp = client.get('/not-found', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        self.assertEqual(resp.status_code, 404)

    def test_run_cli_invokes_subprocess_with_expected_args(self):
        mod, _ = self.load_app(
            MBANK_WRAPPER_PYTHON='/usr/bin/pythonX',
            MBANK_WRAPPER_SCRIPT='/tmp/fake-mbank-cli.py',
            MBANK_WRAPPER_CWD='/tmp',
            MBANK_WRAPPER_TIMEOUT='77',
        )
        fake_proc = mock.Mock(returncode=0, stdout='out', stderr='err')
        with mock.patch.object(mod.subprocess, 'run', return_value=fake_proc) as run_mock:
            rc, out, err = mod._run_cli(['list'])
        self.assertEqual((rc, out, err), (0, 'out', 'err'))
        run_mock.assert_called_once_with(
            ['/usr/bin/pythonX', '/tmp/fake-mbank-cli.py', 'list'],
            cwd='/tmp',
            capture_output=True,
            text=True,
            timeout=77,
            check=False,
        )


if __name__ == '__main__':
    unittest.main()
