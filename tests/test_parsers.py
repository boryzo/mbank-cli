import json
import unittest

from tests._load_mbank_cli import load_module


class TestParsers(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_extract_js_object_assignment_simple(self):
        html = 'x; Ebre.Venezia.ProfileData = {"a":1}; y;'
        out = self.m.extract_js_object_assignment(html, 'Ebre.Venezia.ProfileData')
        self.assertEqual(out, '{"a":1}')

    def test_extract_js_object_assignment_nested_and_strings(self):
        html = (
            "Ebre.Venezia.ProfileData = "
            "{\"a\": {\"b\": 1}, \"txt\": \"value with } and { inside\"};"
        )
        out = self.m.extract_js_object_assignment(html, 'Ebre.Venezia.ProfileData')
        self.assertEqual(json.loads(out), {'a': {'b': 1}, 'txt': 'value with } and { inside'})

    def test_extract_js_object_assignment_missing(self):
        self.assertIsNone(self.m.extract_js_object_assignment('var x = 1;', 'Ebre.Venezia.ProfileData'))

    def test_extract_csrf_token(self):
        html = (
            '<meta name="viewport" content="x">'
            '<meta CONTENT="abc" NAME="__AjaxRequestVerificationToken">'
        )
        self.assertEqual(self.m.extract_csrf_token(html), 'abc')
        self.assertIsNone(self.m.extract_csrf_token('<meta name="x" content="y">'))

    def test_extract_login_profiles_single(self):
        payload = {
            'iProfiles': {'profiles': [{'profileCode': 'T'}]},
            'fProfiles': {'profiles': [{'profileCode': 'B1', 'firmName': 'ACME'}]},
        }
        html = f'<script>Ebre.Venezia.ProfileData = {json.dumps(payload)};</script>'
        profiles = self.m.extract_login_profiles(html)

        self.assertEqual(profiles['personal'], ['T'])
        self.assertEqual(profiles['business'], ['B1'])
        self.assertEqual(profiles['ACME'], ['B1'])

    def test_extract_login_profiles_multiple_business_removes_business_alias(self):
        payload = {
            'iProfiles': {'profiles': [{'profileCode': 'P1'}]},
            'fProfiles': {
                'profiles': [
                    {'profileCode': 'B1', 'firmName': 'One'},
                    {'profileCode': 'B2', 'firmName': 'Two'},
                ]
            },
        }
        html = f'<script>Ebre.Venezia.ProfileData = {json.dumps(payload)};</script>'
        profiles = self.m.extract_login_profiles(html)

        self.assertNotIn('business', profiles)
        self.assertEqual(profiles['One'], ['B1'])
        self.assertEqual(profiles['Two'], ['B2'])

    def test_extract_login_profiles_no_data(self):
        profiles = self.m.extract_login_profiles('<html><body>no profile script</body></html>')
        self.assertEqual(profiles, {'personal': [], 'business': []})

    def test_sort_profile_key_ordering(self):
        names = ['business', 'acme', 'personal', 'personal/company']
        ordered = sorted(names, key=self.m.sort_profile_key)
        self.assertEqual(ordered[0], 'personal')
        self.assertEqual(ordered[1], 'personal/company')


if __name__ == '__main__':
    unittest.main()
