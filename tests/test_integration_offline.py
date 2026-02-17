import io
import json
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

from tests._load_mbank_cli import load_module


FIXTURES = Path(__file__).resolve().parent / 'fixtures'
MAIN_ACCOUNTS = json.loads((FIXTURES / 'accounts_list_main.json').read_text(encoding='utf-8'))
OFFLINE_ACCOUNTS = json.loads((FIXTURES / 'accounts_offline_response.json').read_text(encoding='utf-8'))


class _FakeResponse:
    def __init__(self, status, url, payload, headers=None):
        self.status = status
        self._url = url
        self._payload = payload
        self.headers = headers or {'Content-Type': 'application/json'}

    def read(self):
        return self._payload

    def geturl(self):
        return self._url


class _FakeGateway:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def open(self, request, timeout=60):
        _ = timeout
        method = request.get_method()
        path = urllib.parse.urlsplit(request.full_url).path
        data = getattr(request, 'data', None)
        body = '' if not data else data.decode('utf-8', errors='replace')
        self.calls.append((method, path, body))

        status, payload = self.routes.get((method, path), (404, {'error': 'not found'}))
        raw = json.dumps(payload).encode('utf-8')
        headers = {'Content-Type': 'application/json'}

        if status >= 400:
            raise urllib.error.HTTPError(
                request.full_url,
                status,
                'error',
                headers,
                io.BytesIO(raw),
            )

        return _FakeResponse(status, request.full_url, raw, headers=headers)


class TestOfflineIntegration(unittest.TestCase):
    def setUp(self):
        self.m = load_module()
        self.m.root_url = 'https://offline.test'
        self.m.base_url = 'https://offline.test/pl'
        self.m.opt_debug_dir = None

    def test_do_list_offline_fallback_get(self):
        gateway = _FakeGateway(
            {
                ('POST', '/pl/MyDesktop/Desktop/GetAccountsList'): (200, MAIN_ACCOUNTS),
                ('POST', '/api/AccountsAggregation/Accounts/accounts/Offline'): (405, {'error': 'method not allowed'}),
                ('GET', '/api/AccountsAggregation/Accounts/accounts/Offline'): (200, OFFLINE_ACCOUNTS),
            }
        )
        self.m.ua = gateway

        login_info = {
            'headers': {
                'Referer': self.m.base_url,
                'X-Tab-Id': 'tab-1',
                'X-Request-Verification-Token': 'csrf-token-value-1234567890',
            }
        }

        with mock.patch('sys.stdout', new_callable=io.StringIO) as out:
            result = self.m.do_list(login_info)

        self.assertEqual(len(result), 4)
        printed = out.getvalue().strip().splitlines()
        self.assertEqual(len(printed), 4)
        self.assertIn('eKonto - osobiste;12114020040000310212345678;100.01 PLN;90.00 PLN;mbank', printed[0])
        self.assertIn('Revolut USD;77109025900000000100000001;50.50 USD;50.50 USD;REV', printed[2])

        self.assertIn(('POST', '/api/AccountsAggregation/Accounts/accounts/Offline', '{}'), gateway.calls)
        self.assertIn(('GET', '/api/AccountsAggregation/Accounts/accounts/Offline', ''), gateway.calls)

    def test_activate_profile_hits_activate_and_lazy_logout(self):
        gateway = _FakeGateway(
            {
                ('POST', '/pl/LoginMain/Account/JsonActivateProfile'): (200, {'ok': True}),
                ('POST', '/pl/LoginMain/Account/LazyLogout'): (200, {'lazy': True}),
            }
        )
        self.m.ua = gateway

        login_info = {
            'profiles': {'personal': ['T']},
            'headers': {
                'Referer': self.m.base_url,
                'X-Tab-Id': 'tab-1',
                'X-Request-Verification-Token': 'csrf-token-value-1234567890',
            },
        }

        self.m.do_activate_profile(login_info, 'personal')

        paths = [x[1] for x in gateway.calls]
        self.assertIn('/pl/LoginMain/Account/JsonActivateProfile', paths)
        self.assertIn('/pl/LoginMain/Account/LazyLogout', paths)


if __name__ == '__main__':
    unittest.main()
