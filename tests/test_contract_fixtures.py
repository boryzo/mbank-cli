import json
import unittest
from pathlib import Path

from tests._load_mbank_cli import load_module


FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def read_text(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


def read_json(name):
    return json.loads(read_text(name))


class TestContractFixtures(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_main_accounts_fixture_is_supported(self):
        payload = read_json('accounts_list_main.json')
        raw_accounts = payload['accountDetailsList']

        normalized = [self.m.normalize_mbank_account(a) for a in raw_accounts]
        normalized = [a for a in normalized if a]

        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0]['number'], '12114020040000310212345678')
        self.assertEqual(normalized[0]['currency'], 'PLN')
        self.assertEqual(normalized[1]['name'], 'mSaver')
        self.assertEqual(self.m.format_money(normalized[1]['balance'], normalized[1]['currency']), '200.50 PLN')

    def test_external_accounts_fixture_is_supported(self):
        payload = read_json('accounts_offline_response.json')

        normalized = []
        for node in self.m.iter_dict_nodes(payload):
            item = self.m.normalize_external_account(node)
            if item:
                normalized.append(item)

        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0]['number'], '77109025900000000100000001')
        self.assertEqual(normalized[0]['source'], 'REV')
        self.assertEqual(self.m.format_money(normalized[0]['balance'], normalized[0]['currency']), '50.50 USD')
        self.assertEqual(normalized[1]['source'], 'Santander')
        self.assertEqual(self.m.format_money(normalized[1]['available'], normalized[1]['currency']), '1199.50 PLN')

    def test_dashboard_html_fixture_is_supported(self):
        html = read_text('login_dashboard_page.html')
        csrf = self.m.extract_csrf_token(html)
        profiles = self.m.extract_login_profiles(html)

        self.assertEqual(csrf, 'csrf-token-value-1234567890')
        self.assertEqual(profiles['personal'], ['T'])
        self.assertEqual(profiles['business'], ['F1'])
        self.assertEqual(profiles['ACME Sp. z o.o.'], ['F1'])


if __name__ == '__main__':
    unittest.main()
