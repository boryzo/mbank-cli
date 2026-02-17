import io
import json
import unittest
from unittest import mock

from tests._load_mbank_cli import load_module


class TestHistory(unittest.TestCase):
    def setUp(self):
        self.m = load_module()
        self.m.base_url = 'https://online.mbank.pl/pl'
        self.m.root_url = 'https://online.mbank.pl'

    def test_parse_ymd_date_or_fail(self):
        self.assertEqual(self.m.parse_ymd_date_or_fail('2026-02-17', 'ctx'), '2026-02-17')
        with self.assertRaises(SystemExit) as exc:
            self.m.parse_ymd_date_or_fail('17-02-2026', 'ctx')
        self.assertEqual(exc.exception.code, 1)

    def test_local_midnight_to_utc_shape(self):
        out = self.m.local_midnight_to_utc('2026-02-17')
        self.assertRegex(out, r'^2026-02-\d{2}T\d{2}:\d{2}:\d{2}\.000Z$')

    def test_http_date_to_local_ymd(self):
        out = self.m.http_date_to_local_ymd('Tue, 17 Feb 2026 21:37:12 GMT')
        self.assertRegex(out, r'^2026-02-\d{2}$')

    def test_do_history_prints_rows_with_id_always(self):
        mode_info = {'pfmStartDate': '2026-01-01T00:00:00'}
        pfm_data = {'pfmProducts': [{'contractNumber': 'PL 11 22', 'id': '123'}]}
        accounts = {
            'accountDetailsList': [
                {
                    'ProductName': 'eKonto',
                    'SubTitle': '',
                    'AccountNumber': 'PL 11 22',
                    'Balance': {'amount': '0', 'currency': 'PLN'},
                    'AvailableBalance': {'amount': '0', 'currency': 'PLN'},
                    'Currency': 'PLN',
                }
            ]
        }
        ops = {
            'transactions': [
                {
                    'operationNumber': '789',
                    'operationType': 'TransferOut',
                    'transactionDate': '2026-02-10T09:00:00+01:00',
                    'currency': 'PLN',
                    'amount': '-10.5',
                    'balance': '100.25',
                    'description': 'Rachunek; test',
                    'comment': 'komentarz',
                }
            ],
            'nextPageUrl': None,
        }

        side_effect = [
            {'status': 200, 'content': json.dumps(mode_info), 'headers': {'Date': 'Tue, 17 Feb 2026 21:37:12 GMT'}},
            {'status': 200, 'content': json.dumps(pfm_data), 'headers': {}},
            {'status': 200, 'content': json.dumps(accounts), 'headers': {}},
            {'status': 200, 'content': json.dumps(ops), 'headers': {}},
        ]

        login_info = {'headers': {'X-Tab-Id': 'tab-1', 'X-Request-Verification-Token': 'csrf'}}
        with mock.patch.object(self.m, 'download', side_effect=side_effect), mock.patch(
            'sys.stdout', new_callable=io.StringIO
        ) as out:
            self.m.do_history(login_info, start_date='2026-02-01', end_date='2026-02-15', with_id=False)

        row = out.getvalue().strip()
        self.assertIn('2026-02-10;1122;789;TransferOut;-10.50 PLN;100.25 PLN;Rachunek, test;komentarz', row)

    def test_do_history_invalid_range(self):
        mode_info = {'pfmStartDate': '2026-01-01T00:00:00'}
        side_effect = [
            {'status': 200, 'content': json.dumps(mode_info), 'headers': {'Date': 'Tue, 17 Feb 2026 21:37:12 GMT'}},
        ]
        login_info = {'headers': {'X-Tab-Id': 'tab-1', 'X-Request-Verification-Token': 'csrf'}}
        with mock.patch.object(self.m, 'download', side_effect=side_effect):
            with self.assertRaises(SystemExit) as exc:
                self.m.do_history(login_info, start_date='2026-03-01', end_date='2026-02-01', with_id=False)
        self.assertEqual(exc.exception.code, 1)

    def test_do_history_retries_on_519(self):
        mode_info = {'pfmStartDate': '2026-01-01T00:00:00'}
        pfm_data = {'pfmProducts': [{'contractNumber': 'PL 11 22', 'id': '123'}]}
        accounts = {
            'accountDetailsList': [
                {
                    'ProductName': 'eKonto',
                    'SubTitle': '',
                    'AccountNumber': 'PL 11 22',
                    'Balance': {'amount': '0', 'currency': 'PLN'},
                    'AvailableBalance': {'amount': '0', 'currency': 'PLN'},
                    'Currency': 'PLN',
                }
            ]
        }
        ops = {'transactions': [], 'nextPageUrl': None}
        side_effect = [
            {'status': 200, 'content': json.dumps(mode_info), 'headers': {'Date': 'Tue, 17 Feb 2026 21:37:12 GMT'}},
            {'status': 200, 'content': json.dumps(pfm_data), 'headers': {}},
            {'status': 200, 'content': json.dumps(accounts), 'headers': {}},
            {'status': 519, 'content': '{}', 'headers': {}},
            {'status': 200, 'content': json.dumps(ops), 'headers': {}},
        ]
        login_info = {'headers': {'X-Tab-Id': 'tab-1', 'X-Request-Verification-Token': 'csrf'}}
        with mock.patch.object(self.m, 'download', side_effect=side_effect):
            self.m.do_history(login_info, start_date='2026-02-01', end_date='2026-02-15', with_id=False)

    def test_do_history_default_range_is_last_60_days(self):
        mode_info = {'pfmStartDate': '2020-01-01T00:00:00'}
        pfm_data = {'pfmProducts': [{'contractNumber': 'PL 11 22', 'id': '123'}]}
        accounts = {
            'accountDetailsList': [
                {
                    'ProductName': 'eKonto',
                    'SubTitle': '',
                    'AccountNumber': 'PL 11 22',
                    'Balance': {'amount': '0', 'currency': 'PLN'},
                    'AvailableBalance': {'amount': '0', 'currency': 'PLN'},
                    'Currency': 'PLN',
                }
            ]
        }
        ops = {'transactions': [], 'nextPageUrl': None}
        side_effect = [
            {'status': 200, 'content': json.dumps(mode_info), 'headers': {'Date': 'Tue, 17 Feb 2026 21:37:12 GMT'}},
            {'status': 200, 'content': json.dumps(pfm_data), 'headers': {}},
            {'status': 200, 'content': json.dumps(accounts), 'headers': {}},
            {'status': 200, 'content': json.dumps(ops), 'headers': {}},
        ]
        login_info = {'headers': {'X-Tab-Id': 'tab-1', 'X-Request-Verification-Token': 'csrf'}}
        with mock.patch.object(self.m, 'download', side_effect=side_effect) as dl, mock.patch.object(
            self.m, 'warning'
        ) as warn:
            self.m.do_history(login_info, with_id=False)
        ops_req = dl.call_args_list[3].args[0]
        url = ops_req.full_url
        self.assertRegex(url, r'dateFrom=2025-12-(18|19)T')
        self.assertIn('dateTo=2026-02-16T', url)
        warn.assert_called_once()

    def test_get_external_history_rows_done_only(self):
        external_accounts = {
            'status': 'ok',
            'code': 200,
            'payload': [
                {
                    'accountId': '4576adb5-09c0-4158-b6e1-3a6cb46b68dc',
                    'bankId': '0789b9be-67d1-468d-9c98-93eb9a058630',
                    'accountNumber': '95156000132012508990000004',
                    'externalAccountName': 'Elastyczne Konto Oszczednosciowe',
                }
            ],
        }
        status_payload = {'status': 'ok', 'code': 200, 'payload': {'eventStatus': 'SUCCESS'}}
        offline_payload = {
            'status': 'ok',
            'code': 200,
            'payload': {
                'transactions': [
                    {
                        'id': 'tx-1',
                        'transactionStatus': 'DONE',
                        'transactionCategory': 'DEBIT',
                        'currency': 'PLN',
                        'description': 'Przelew własny',
                        'bookingDate': '2026-02-17',
                        'postTransactionBalance': '2251.55',
                        'amount': '-600.00',
                        'bankName': 'Velo Bank',
                    },
                    {
                        'id': 'tx-2',
                        'transactionStatus': 'PENDING',
                        'transactionCategory': 'DEBIT',
                        'currency': 'PLN',
                        'description': 'To skip',
                        'bookingDate': '2026-02-18',
                        'postTransactionBalance': '2000',
                        'amount': '-10.00',
                    },
                ]
            },
        }
        side_effect = [
            {'status': 200, 'content': json.dumps(external_accounts), 'headers': {}},
            {'status': 200, 'content': json.dumps(status_payload), 'headers': {}},
            {'status': 200, 'content': json.dumps(offline_payload), 'headers': {}},
        ]
        login_info = {'headers': {'X-Tab-Id': 'tab-1', 'X-Request-Verification-Token': 'csrf'}}
        with mock.patch.object(self.m, 'download', side_effect=side_effect):
            rows = self.m.get_external_history_rows(login_info, '2026-01-01', '2026-02-17', with_id=False)
        self.assertEqual(len(rows), 1)
        self.assertIn('2026-02-17;95156000132012508990000004;tx-1;DEBIT;-600.00 PLN;2251.55 PLN;Przelew własny;Velo Bank', rows[0])

    def test_do_history_include_all_prints_external_rows(self):
        mode_info = {'pfmStartDate': '2026-01-01T00:00:00'}
        pfm_data = {'pfmProducts': [{'contractNumber': 'PL 11 22', 'id': '123'}]}
        accounts = {
            'accountDetailsList': [
                {
                    'ProductName': 'eKonto',
                    'SubTitle': '',
                    'AccountNumber': 'PL 11 22',
                    'Balance': {'amount': '0', 'currency': 'PLN'},
                    'AvailableBalance': {'amount': '0', 'currency': 'PLN'},
                    'Currency': 'PLN',
                }
            ]
        }
        ops = {'transactions': [], 'nextPageUrl': None}
        side_effect = [
            {'status': 200, 'content': json.dumps(mode_info), 'headers': {'Date': 'Tue, 17 Feb 2026 21:37:12 GMT'}},
            {'status': 200, 'content': json.dumps(pfm_data), 'headers': {}},
            {'status': 200, 'content': json.dumps(accounts), 'headers': {}},
            {'status': 200, 'content': json.dumps(ops), 'headers': {}},
        ]
        login_info = {'headers': {'X-Tab-Id': 'tab-1', 'X-Request-Verification-Token': 'csrf'}}
        with mock.patch.object(self.m, 'download', side_effect=side_effect), mock.patch.object(
            self.m, 'get_external_history_rows', return_value=['2026-02-17;X;ext-tx-1;DEBIT;-1.00 PLN;;;Velo Bank']
        ) as ext, mock.patch('sys.stdout', new_callable=io.StringIO) as out:
            self.m.do_history(login_info, start_date='2026-02-01', end_date='2026-02-15', include_all=True)
        self.assertIn('2026-02-17;X;ext-tx-1;DEBIT;-1.00 PLN;;;Velo Bank', out.getvalue())
        ext.assert_called_once_with(login_info, '2026-02-01', '2026-02-15', with_id=False)


if __name__ == '__main__':
    unittest.main()
