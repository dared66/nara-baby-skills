import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import skill_credentials as store


class MemoryBackend:
    def __init__(self):
        self.data = {}

    def get_password(self, service, account):
        return self.data.get((service, account))

    def set_password(self, service, account, value):
        self.data[service, account] = value

    def delete_password(self, service, account):
        del self.data[service, account]


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.backend = MemoryBackend()
        mock = patch.object(store, "_backend", return_value=self.backend)
        mock.start()
        self.addCleanup(mock.stop)

    def test_service_account_isolation_and_delete(self):
        for service, account, token in [("nara-baby", "default", "one"), ("other", "default", "two"), ("nara-baby", "second", "three")]:
            store.save_record(service, account, {"token": token})
        self.assertEqual(store.load_record("nara-baby"), {"token": "one"})
        store.delete_record("nara-baby")
        with self.assertRaises(store.CredentialError):
            store.load_record("nara-baby")
        self.assertEqual(store.load_record("other"), {"token": "two"})
        self.assertEqual(store.load_record("nara-baby", "second"), {"token": "three"})
        self.assertTrue(all(s.startswith("local.skills.") for s, a in self.backend.data))

    def test_no_environment_fallback_or_injection(self):
        with patch.dict(os.environ, {"NARA_PASSWORD": "env-canary"}):
            before = dict(os.environ)
            with self.assertRaises(store.CredentialError):
                store.load_record("nara-baby")
            store.save_record("nara-baby", "default", {"password": "keychain-canary"})
            self.assertEqual(store.load_record("nara-baby")["password"], "keychain-canary")
            self.assertEqual(dict(os.environ), before)

    def test_status_never_displays_values(self):
        store.save_record("test", "default", {"api_key": "secret-canary"})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = store.main(["status", "--service", "test"])
        self.assertEqual(code, 0)
        self.assertNotIn("secret-canary", output.getvalue())
        self.assertTrue(json.loads(output.getvalue())["configured"])

    def test_backend_output_and_exception_are_hidden(self):
        def fail(*args):
            print("secret-canary")
            print("secret-canary", file=sys.stderr)
            raise RuntimeError("secret-canary")
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(self.backend, "get_password", side_effect=fail), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(store.main(["status", "--service", "test"]), 1)
        self.assertNotIn("secret-canary", output.getvalue() + errors.getvalue())

    def test_setup_requires_terminal(self):
        with patch.object(sys.stdin, "isatty", return_value=False), patch.object(store.getpass, "getpass") as prompt:
            with self.assertRaises(store.CredentialError):
                store.setup_record("test")
            prompt.assert_not_called()
        self.assertFalse(self.backend.data)

    def test_local_setup_confirms_hidden_fields(self):
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(store.getpass, "getpass", side_effect=["abc", "abc"]):
            store.setup_record("test", fields=["api_key"])
        self.assertEqual(store.load_record("test"), {"api_key": "abc"})
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(store.getpass, "getpass", side_effect=["new", "mismatch"] * 3), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(store.CredentialError):
                store.setup_record("test", fields=["api_key"])
        self.assertEqual(store.load_record("test"), {"api_key": "abc"})

    def test_blank_input_reprompts_without_losing_completed_fields(self):
        errors = io.StringIO()
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(store.getpass, "getpass", side_effect=["user-canary", "user-canary", "", "secret-canary", "secret-canary"]), contextlib.redirect_stderr(errors):
            store.setup_record("test")
        self.assertEqual(store.load_record("test"), {"email": "user-canary", "password": "secret-canary"})
        self.assertIn("password was empty", errors.getvalue())
        self.assertNotIn("canary", errors.getvalue())

    def test_exhausted_blank_attempts_preserve_saved_entry(self):
        store.save_record("test", "default", {"api_key": "old-canary"})
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(store.getpass, "getpass", side_effect=["", "", ""]), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(store.CredentialError, "api_key after three attempts"):
                store.setup_record("test", fields=["api_key"])
        self.assertEqual(store.load_record("test"), {"api_key": "old-canary"})

    def test_malformed_record(self):
        self.backend.data["local.skills.test", "default"] = "secret-canary-invalid-json"
        with self.assertRaises(store.CredentialError) as caught:
            store.load_record("test")
        self.assertNotIn("secret-canary", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
