import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import nara_cli
import nara_client
import nara_config
from nara_keychain import NaraError


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'config/preferences.json'
        p = patch.object(nara_config, 'config_path', return_value=self.path)
        p.start()
        self.addCleanup(p.stop)

    def test_private_roundtrip(self):
        self.assertEqual(nara_config.load_config(), {})
        nara_config.save_config({'timezone': 'UTC', 'child': 'synthetic-child'})
        self.assertEqual(nara_config.load_config()['timezone'], 'UTC')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_credentials_and_invalid_values_rejected(self):
        for value in ({'password': 'secret-canary'}, {'timezone': None}, {'child': ''}, [], 'bad'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                nara_config.save_config(value)
        self.assertFalse(self.path.exists())

    def test_failed_replace_preserves_previous_preferences(self):
        nara_config.save_config({'timezone': 'UTC'})
        with patch.object(nara_config.os, 'replace', side_effect=OSError('failure')):
            with self.assertRaises(OSError):
                nara_config.save_config({'timezone': 'Europe/London'})
        self.assertEqual(nara_config.load_config(), {'timezone': 'UTC'})
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_malformed_stored_preferences_rejected(self):
        self.path.parent.mkdir()
        for content in ('[]', '{', '{"token":"secret-canary"}', '{"timezone":4}'):
            self.path.write_text(content)
            with self.assertRaises(ValueError):
                nara_config.load_config()


class BoundaryTests(unittest.TestCase):
    def test_identifier_filter_preserves_activity_fields(self):
        source = {'solid': True, 'liquid': 12, 'note': 'valid', 'trackId': 'secret-id', 'nested': {'syncKey': 'cursor', 'amount': 3}}
        self.assertEqual(nara_cli.public_result(source), {'solid': True, 'liquid': 12, 'note': 'valid', 'nested': {'amount': 3}})

    def test_missing_names_fail_instead_of_claiming_available(self):
        for profiles in ({}, {'example': {}}, {'example': {'name': ' '}}):
            api = Mock()
            api.get_children.return_value = profiles
            with self.assertRaises(NaraError):
                nara_cli.child_choices(api)

    def test_source_tampering_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'nara.py'
            path.write_text('raise AssertionError("must never execute")')
            with patch.object(nara_client, 'SOURCE', path), self.assertRaisesRegex(NaraError, 'reviewed version'):
                nara_client.load_api(Mock())

    def test_destination_tls_redirect_and_timeout_policy(self):
        transport = nara_client.Transport()
        self.addCleanup(transport.close)
        self.assertFalse(transport.session.trust_env)
        with patch.object(transport.session, 'request') as request:
            for url in ('http://identitytoolkit.googleapis.com/a', 'https://evil.example/a', 'https://identitytoolkit.googleapis.com.evil.example/a', 'https://user:pass@identitytoolkit.googleapis.com/a', 'https://identitytoolkit.googleapis.com:444/a'):
                with self.subTest(url=url), self.assertRaises(NaraError):
                    transport.get(url)
            with self.assertRaises(NaraError):
                transport.get('https://identitytoolkit.googleapis.com/a', verify=False)
            request.assert_not_called()
            request.return_value.status_code = 200
            transport.get('https://identitytoolkit.googleapis.com/a', timeout=999, allow_redirects=True)
            self.assertEqual(request.call_args.kwargs['timeout'], (10, 30))
            self.assertFalse(request.call_args.kwargs['allow_redirects'])
            request.return_value.status_code = 302
            with self.assertRaises(NaraError):
                transport.get('https://identitytoolkit.googleapis.com/a')
