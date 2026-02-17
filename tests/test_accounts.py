import io
import json
import unittest
from unittest import mock

from tests._load_mbank_cli import load_module


class TestAccounts(unittest.TestCase):
    def setUp(self):
        self.m = load_module()
        self.m.base_url = 'https://online.mbank.pl/pl'
        self.m.root_url = 'https://online.mbank.pl'

    def test_normalize_account_number(self):
        self.assertEqual(self.m.normalize_account_number('PL 12 3456 7890'), '1234567890')
        self.assertEqual(self.m.normalize_account_number(' 11 22 '), '1122')
        self.assertEqual(self.m.normalize_account_number(None), '')

    def test_normalize_mbank_account(self):
        raw = {
            'ProductName': 'eKonto',
            'SubTitle': 'osobiste',
            'AccountNumber': 'PL 12 3456 7890 1234 5678 9012',
            'Balance': {'amount': '10,5', 'currency': 'PLN'},
            'AvailableBalance': {'amount': '9.5', 'currency': 'PLN'},
        }
        out = self.m.normalize_mbank_account(raw)
        self.assertEqual(out['name'], 'eKonto - osobiste')
        self.assertEqual(out['number'], '1234567890123456789012')
        self.assertEqual(out['currency'], 'PLN')
        self.assertEqual(out['source'], 'mbank')

    def test_normalize_external_account(self):
        raw = {
            'accountNameClient': 'Konto w innym banku',
            'iban': 'PL 98 7654 3210 0000 1111 2222 3333',
            'bookingBalance': {'amount': '1000.12', 'currency': 'USD'},
            'bankName': 'Test Bank',
        }
        out = self.m.normalize_external_account(raw)
        self.assertEqual(out['name'], 'Konto w innym banku')
        self.assertEqual(out['number'], '98765432100000111122223333')
        self.assertEqual(out['currency'], 'USD')
        self.assertEqual(out['source'], 'Test Bank')

    def test_normalize_external_account_missing_name_or_number(self):
        self.assertIsNone(self.m.normalize_external_account({'name': 'A'}))
        self.assertIsNone(self.m.normalize_external_account({'accountNumber': '1'}))

    def test_normalize_external_account_maps_known_bank_ids(self):
        cases = [
            ('05855557-d3ee-46c9-98e1-375c10e1af12', 'Bank Millennium'),
            ('8bd46568-f90e-445a-bec8-5fef7dc90569', 'Alior Bank'),
            ('b5165570-f6f1-11e8-8eb2-f2801f1b9fd1', 'Bank Pekao SA'),
            ('555dd77f-7424-4bf7-8869-5576e47793b9', 'Santander Bank Polska'),
            ('a32d692c-397e-4307-9da8-8367fc3f9237', 'Santander Bank Polska'),
            ('0789b9be-67d1-468d-9c98-93eb9a058630', 'VeloBank'),
        ]
        for bank_id, expected in cases:
            raw = {
                'name': 'Zewnetrzne',
                'accountNumber': 'PL 11 11',
                'balance': {'amount': '1', 'currency': 'PLN'},
                'bankId': bank_id,
            }
            out = self.m.normalize_external_account(raw)
            self.assertEqual(out['source'], expected)

    def test_normalize_external_account_maps_bank_id_case_insensitive(self):
        raw = {
            'name': 'Zewnetrzne',
            'accountNumber': 'PL 11 11',
            'balance': {'amount': '1', 'currency': 'PLN'},
            'bankId': '8BD46568-F90E-445A-BEC8-5FEF7DC90569',
        }
        out = self.m.normalize_external_account(raw)
        self.assertEqual(out['source'], 'Alior Bank')

    def test_normalize_external_account_unknown_bank_id_passthrough(self):
        raw = {
            'name': 'Zewnetrzne',
            'accountNumber': 'PL 11 11',
            'balance': {'amount': '1', 'currency': 'PLN'},
            'bankId': 'unknown-id',
        }
        out = self.m.normalize_external_account(raw)
        self.assertEqual(out['source'], 'unknown-id')

    def test_iter_dict_nodes(self):
        data = {'a': {'b': [{'c': 1}, {'d': 2}]}, 'e': [1, {'f': 3}]}
        nodes = list(self.m.iter_dict_nodes(data))
        keys = [sorted(x.keys()) for x in nodes]
        self.assertIn(['a', 'e'], keys)
        self.assertIn(['b'], keys)
        self.assertIn(['c'], keys)
        self.assertIn(['d'], keys)
        self.assertIn(['f'], keys)

    def test_fetch_offline_accounts_deduplicates(self):
        payload = {
            'accounts': [
                {
                    'name': 'Ext A',
                    'accountNumber': 'PL 11 11',
                    'balance': {'amount': '1', 'currency': 'PLN'},
                    'bankName': 'X',
                },
                {
                    'name': 'Ext A',
                    'accountNumber': 'PL 11 11',
                    'balance': {'amount': '1', 'currency': 'PLN'},
                    'bankName': 'X',
                },
            ]
        }
        with mock.patch.object(
            self.m,
            'post_json',
            return_value={'status': 200, 'content': json.dumps(payload)},
        ):
            out = self.m.fetch_offline_accounts({'headers': {}})

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['name'], 'Ext A')

    def test_fetch_offline_accounts_fallback_to_get(self):
        with mock.patch.object(self.m, 'post_json', return_value={'status': 404, 'content': '{}'}), mock.patch.object(
            self.m,
            'download',
            return_value={
                'status': 200,
                'content': json.dumps(
                    [{'name': 'Ext B', 'accountNumber': 'PL 22 22', 'balance': {'amount': '2', 'currency': 'EUR'}}]
                ),
            },
        ) as mock_download:
            out = self.m.fetch_offline_accounts({'headers': {}})

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['name'], 'Ext B')
        mock_download.assert_called_once()

    def test_fetch_offline_accounts_non_2xx(self):
        with mock.patch.object(self.m, 'post_json', return_value={'status': 500, 'content': '{}'}):
            out = self.m.fetch_offline_accounts({'headers': {}})
        self.assertEqual(out, [])

    def test_print_account_row_uses_semicolon_separator(self):
        account = {'name': 'A', 'number': '123', 'balance': '1', 'available': '1', 'currency': 'PLN', 'source': 'mbank'}
        with mock.patch.object(self.m, 'current_timestamp_iso', return_value='2026-02-17T21:37:12+01:00'), mock.patch(
            'sys.stdout', new_callable=io.StringIO
        ) as out:
            self.m.print_account_row(account)
        self.assertEqual(out.getvalue().strip(), '2026-02-17T21:37:12+01:00;A;123;1.00 PLN;1.00 PLN;mbank')

    def test_do_list_merges_main_and_external(self):
        main_payload = {
            'accountDetailsList': [
                {
                    'ProductName': 'eKonto',
                    'SubTitle': '',
                    'AccountNumber': 'PL 12 34',
                    'Balance': {'amount': '10', 'currency': 'PLN'},
                    'AvailableBalance': {'amount': '9', 'currency': 'PLN'},
                }
            ]
        }
        ext_payload = [
            {
                'name': 'External',
                'number': '5678',
                'balance': '3',
                'available': '3',
                'currency': 'USD',
                'source': 'OtherBank',
            }
        ]

        with mock.patch.object(
            self.m,
            'download',
            return_value={'status': 200, 'content': json.dumps(main_payload)},
        ), mock.patch.object(self.m, 'fetch_offline_accounts', return_value=ext_payload), mock.patch(
            'sys.stdout', new_callable=io.StringIO
        ) as out:
            result = self.m.do_list({'headers': {'X-Tab-Id': '1'}})

        self.assertEqual(len(result), 2)
        printed = out.getvalue().strip().splitlines()
        self.assertEqual(len(printed), 2)
        self.assertIn('eKonto;1234;10.00 PLN;9.00 PLN;mbank', printed[0])
        self.assertIn('External;5678;3.00 USD;3.00 USD;OtherBank', printed[1])

    def test_do_list_requires_account_details_list(self):
        with mock.patch.object(self.m, 'download', return_value={'status': 200, 'content': '{}'}):
            with self.assertRaises(SystemExit) as exc:
                self.m.do_list({'headers': {}})
        self.assertEqual(exc.exception.code, 3)


if __name__ == '__main__':
    unittest.main()
