import gzip
import os
import tempfile
import unittest
from unittest import mock

from tests._load_mbank_cli import load_module


class TestUtils(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_pick_skips_none_and_blank(self):
        self.assertEqual(self.m.pick(None, '', '   ', 'abc', 'zzz'), 'abc')

    def test_pick_returns_none_when_empty(self):
        self.assertIsNone(self.m.pick(None, '', '  '))

    def test_expand_and_unexpand_tilde(self):
        expanded = self.m.expand_tilde('~/tmp')
        self.assertTrue(expanded.endswith('/tmp'))
        self.assertEqual(self.m.unexpand_tilde(expanded), '~/tmp')

    def test_decode_http_content_plain(self):
        out = self.m.decode_http_content(b'a\r\nb', {'Content-Encoding': ''})
        self.assertEqual(out, 'a\nb')

    def test_decode_http_content_gzip(self):
        raw = gzip.compress(b'a\r\nb')
        out = self.m.decode_http_content(raw, {'Content-Encoding': 'gzip'})
        self.assertEqual(out, 'a\nb')

    def test_decode_http_content_deflate(self):
        import zlib

        raw = zlib.compress(b'a\r\nb')
        out = self.m.decode_http_content(raw, {'Content-Encoding': 'deflate'})
        self.assertEqual(out, 'a\nb')

    def test_read_config_parses_values(self):
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as fh:
            path = fh.name
            fh.write('# comment\n')
            fh.write('CookieJar ~/.cache/mbank.cookies\n')
            fh.write('Country PL\n')
            fh.write('Login "john.doe"\n')
            fh.write("Password 'secret value'\n")

        try:
            cfg = self.m.read_config(path)
            self.assertEqual(cfg['cookiejar'], '~/.cache/mbank.cookies')
            self.assertEqual(cfg['country'], 'PL')
            self.assertEqual(cfg['login'], 'john.doe')
            self.assertEqual(cfg['password'], 'secret value')
            self.assertEqual(cfg['__path__'], path)
        finally:
            os.unlink(path)

    def test_read_config_syntax_error_exits(self):
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as fh:
            path = fh.name
            fh.write('this-is-not-valid\n')

        try:
            with self.assertRaises(SystemExit) as exc:
                self.m.read_config(path)
            self.assertEqual(exc.exception.code, 1)
        finally:
            os.unlink(path)

    def test_cfg_get_default(self):
        self.m.global_config = {'country': 'PL'}
        self.assertEqual(self.m.cfg_get('country'), 'PL')
        self.assertEqual(self.m.cfg_get('missing', 'x'), 'x')

    def test_decode_json_invalid_exits_with_code_3(self):
        with self.assertRaises(SystemExit) as exc:
            self.m.decode_json('{', 'ctx')
        self.assertEqual(exc.exception.code, 3)

    def test_match_uuid_valid_and_invalid(self):
        good = '123e4567-e89b-12d3-a456-426614174000'
        self.assertEqual(self.m.match_uuid(good, 'ctx'), good)

        with self.assertRaises(SystemExit) as exc:
            self.m.match_uuid('bad-uuid', 'ctx')
        self.assertEqual(exc.exception.code, 3)

    def test_timestamp_to_date(self):
        self.assertEqual(self.m.timestamp_to_date('2026-02-16T10:11:12+01:00'), '2026-02-16')
        self.assertEqual(self.m.timestamp_to_date('2026-02-16'), '')

    def test_normalize_number(self):
        self.assertEqual(self.m.normalize_number(' 1 234,50 '), '1234.50')
        self.assertEqual(self.m.normalize_number('\xa0-12,7'), '-12.7')
        self.assertIsNone(self.m.normalize_number('abc'))

    def test_format_money(self):
        self.assertEqual(self.m.format_money('1234,5', 'pln'), '1234.50 PLN')
        self.assertEqual(self.m.format_money('-1.2', 'USD'), '-1.20 USD')
        self.assertEqual(self.m.format_money('abc', 'PLN'), '')
        self.assertEqual(self.m.format_money('1', 'BAD!'), '')

    def test_make_config_line(self):
        self.assertEqual(self.m.make_config_line('Country', 'PL'), 'Country PL\n')
        self.assertEqual(
            self.m.make_config_line('Password', 'with spaces and "quotes"'),
            'Password "with spaces and \\"quotes\\""\n',
        )

    def test_get_tz_country_guess(self):
        with mock.patch.object(self.m.locale, 'getlocale', return_value=('pl_PL', 'UTF-8')):
            self.assertEqual(self.m.get_tz_country_guess(), 'pl')

        with mock.patch.object(self.m.locale, 'getlocale', return_value=('en_US', 'UTF-8')):
            self.assertIsNone(self.m.get_tz_country_guess())

        with mock.patch.object(self.m.locale, 'getlocale', side_effect=RuntimeError('boom')):
            self.assertIsNone(self.m.get_tz_country_guess())


if __name__ == '__main__':
    unittest.main()
