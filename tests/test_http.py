import io
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest import mock

from tests._load_mbank_cli import load_module


class _FakeResponse:
    def __init__(self, status=200, content=b'{}', url='https://example.com/ok', headers=None):
        self.status = status
        self._content = content
        self._url = url
        self.headers = headers or {'Content-Encoding': ''}

    def read(self):
        return self._content

    def geturl(self):
        return self._url


class _FakeUA:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def open(self, request, timeout=60):
        _ = timeout
        if self.error is not None:
            raise self.error
        return self.response


class TestHttpHelpers(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_log_http_writes_request_and_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.m.opt_debug_dir = tmp
            req = urllib.request.Request('https://example.com/test', data=b'{"x":1}', headers={'X-Test': '1'}, method='POST')
            resp = _FakeResponse(status=201, content=b'{"ok":true}', headers={'Content-Type': 'application/json'})

            self.m.log_http(req, response=resp, content='{"ok":true}')

            with open(f'{tmp}/log', 'r', encoding='utf-8') as fh:
                content = fh.read()

            self.assertIn('HTTP POST https://example.com/test', content)
            self.assertIn('< STATUS 201', content)
            self.assertIn('{"ok":true}', content)

    def test_download_success(self):
        req = urllib.request.Request('https://example.com/test', method='GET')
        self.m.ua = _FakeUA(response=_FakeResponse(status=200, content=b'abc', headers={'Content-Encoding': ''}))

        out = self.m.download(req)

        self.assertEqual(out['status'], 200)
        self.assertEqual(out['content'], 'abc')
        self.assertEqual(out['url'], 'https://example.com/ok')

    def test_download_http_error_ignored(self):
        req = urllib.request.Request('https://example.com/not-found', method='GET')
        err = urllib.error.HTTPError(
            req.full_url,
            404,
            'not found',
            {'Content-Encoding': ''},
            io.BytesIO(b'{"err":1}'),
        )
        self.m.ua = _FakeUA(error=err)

        out = self.m.download(req, ignore_errors=(404,))

        self.assertEqual(out['status'], 404)
        self.assertEqual(out['content'], '{"err":1}')

    def test_download_http_error_not_ignored_calls_server_fail(self):
        req = urllib.request.Request('https://example.com/forbidden', method='GET')
        err = urllib.error.HTTPError(req.full_url, 451, 'forbidden', {}, io.BytesIO(b''))
        self.m.ua = _FakeUA(error=err)

        with mock.patch.object(self.m, 'server_fail', side_effect=RuntimeError('server_fail')) as sf:
            with self.assertRaises(RuntimeError):
                self.m.download(req)
            sf.assert_called_once()

    def test_download_url_error_calls_server_fail(self):
        req = urllib.request.Request('https://example.com/down', method='GET')
        self.m.ua = _FakeUA(error=urllib.error.URLError('dns'))

        with mock.patch.object(self.m, 'server_fail', side_effect=RuntimeError('server_fail')) as sf:
            with self.assertRaises(RuntimeError):
                self.m.download(req)
            sf.assert_called_once()


if __name__ == '__main__':
    unittest.main()
