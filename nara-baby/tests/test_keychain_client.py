import contextlib
import io
import json
import os
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "keychain-credentials/scripts"))
import nara_client
import nara_cli
import nara_keychain
import skill_credentials


class Response:
    status_code = 200

    def __init__(self, value):
        self.value = value

    def json(self):
        return self.value

    def raise_for_status(self):
        pass


class FakeTransport:
    def request(self, method, url, **kwargs):
        print("upstream-password-canary", file=sys.stderr)
        if "signInWithPassword" in url:
            assert kwargs["json"]["password"] == "password-canary"
            return Response({"idToken": "token-canary", "localId": "user"})
        if "familyKeyz" in url:
            return Response({"family": True})
        if "/childz.json" in url:
            return Response({"child-a": {"name": "Baby A"}, "child-b": {"name": "Baby B"}})
        if "cloudfunctions" in url:
            return Response({"result": {"data": {"trackz": {
                "a": {"childKey": "child-a", "type": "DIAPER", "beginDt": 1},
                "b": {"childKey": "child-b", "type": "SLEEP", "beginDt": 2},
            }}}})
        raise AssertionError("Unexpected endpoint")

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def close(self):
        pass


class ClientTests(unittest.TestCase):
    def test_output_removes_nested_database_identifiers(self):
        raw = {"family": "family-canary", "child": "child-canary", "child_label": "Baby B",
               "tracks": [{"key": "track-canary", "userKey": "user-canary", "createUserKey": "creator-canary",
                           "childKey": "child-canary", "familyKey": "family-canary", "note": "Nap",
                           "nested": {"syncKey": "cursor-canary", "name": "Test"}}]}
        public = nara_cli.public_result(raw)
        self.assertNotIn("canary", json.dumps(public))
        self.assertEqual(public["child"], "Baby B")
        self.assertEqual(public["tracks"][0]["note"], "Nap")
        self.assertEqual(raw["tracks"][0]["key"], "track-canary")

    def test_internal_ids_require_explicit_diagnostic_flag(self):
        normal = nara_cli.execute(nara_cli.parser().parse_args(["children"]))
        internal = nara_cli.execute(nara_cli.parser().parse_args(["children", "--include-internal"]))
        self.assertNotIn("family", normal)
        self.assertNotIn("key", normal["children"][0])
        self.assertEqual(internal["family"], "family")
        self.assertEqual(internal["children"][0]["key"], "child-a")

    def test_live_and_legacy_sync_envelopes(self):
        tracks = {"a": {"childKey": "child-a"}, "b": {"childKey": "child-b"}}
        self.assertEqual(nara_client.parse_tracks({"result": {"trackz": tracks, "nextSyncKey": "cursor"}}), tracks)
        self.assertEqual(nara_client.parse_tracks({"result": {"data": {"trackz": tracks}}}), tracks)
        self.assertEqual(nara_client.parse_tracks({"result": {"trackz": {}}}), {})
        for invalid in ({}, {"result": {}}, {"error": "private-error-canary"}, {"result": {"trackz": []}}):
            with self.subTest(invalid=invalid), self.assertRaises(nara_keychain.NaraError):
                nara_client.parse_tracks(invalid)

    def setUp(self):
        for mock in (
            patch.object(nara_client, "SOURCE", Path(__file__).parent / "fixtures/upstream_contract.py"),
            patch.object(nara_client, "SOURCE_SHA256", hashlib.sha256((Path(__file__).parent / "fixtures/upstream_contract.py").read_bytes()).hexdigest()),
            patch.dict(os.environ, {"NARA_TIMEZONE": "America/Los_Angeles"}),
            patch.object(nara_cli, "load_config", return_value={"timezone": "America/Los_Angeles"}),
            patch.object(nara_client, "Transport", FakeTransport),
            patch.object(nara_keychain, "load_record", return_value={"email": "email-canary", "password": "password-canary"}),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def test_history_child_filter_and_secret_suppression(self):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = nara_cli.main(["history", "--child", "child-b"])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual([t["type"] for t in result["tracks"]], ["SLEEP"])
        self.assertEqual(result["timezone"], "America/Los_Angeles")
        self.assertNotIn("canary", output.getvalue() + errors.getvalue())

    def test_reauthentication_preserves_child_and_clears_client_on_exit(self):
        with nara_client.connected_client(child="child-b") as api:
            api.login()
            self.assertEqual(api.child_key, "child-b")
            self.assertEqual(api.family_key, "family")
        self.assertIsNone(api.password)
        self.assertIsNone(api.id_token)

    def test_missing_keychain_prevents_login(self):
        with patch.object(nara_client, "load_credentials", side_effect=nara_keychain.NaraError("No saved login")), patch.object(FakeTransport, "post") as post:
            with self.assertRaises(nara_keychain.NaraError):
                with nara_client.connected_client(child="child-b"):
                    pass
            post.assert_not_called()

    def test_authentication_exception_has_no_sensitive_output(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(FakeTransport, "post", side_effect=RuntimeError("password-canary token-canary")), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(nara_cli.main(["children"]), 1)
        self.assertNotIn("canary", output.getvalue() + errors.getvalue())

    def test_unknown_child_rejected(self):
        with self.assertRaisesRegex(nara_keychain.NaraError, "selected child"):
            with nara_client.connected_client(child="wrong-child"):
                self.fail("Must not connect to an unknown child")

    def test_onboarding_requests_credentials_without_network(self):
        with patch.object(nara_cli, "load_credentials", side_effect=nara_keychain.NaraError("not set")), patch.object(nara_cli, "connected_client") as connect:
            result = nara_cli.execute(nara_cli.parser().parse_args(["onboard"]))
        self.assertEqual(result["state"], "needs_credentials")
        connect.assert_not_called()

    def test_onboarding_requests_timezone_before_network(self):
        with patch.object(nara_cli, "load_config", return_value={}), patch.object(nara_cli, "connected_client") as connect:
            result = nara_cli.execute(nara_cli.parser().parse_args(["onboard"]))
        self.assertEqual(result["state"], "needs_timezone")
        connect.assert_not_called()

    def test_onboarding_two_children_never_picks_first(self):
        result = nara_cli.execute(nara_cli.parser().parse_args(["onboard"]))
        self.assertEqual(result["state"], "needs_child_selection")
        self.assertEqual(result["children"], [{"name": "Baby A"}, {"name": "Baby B"}])
        self.assertTrue(result["names_available"])
        self.assertNotIn("child", result)

    def test_saved_selection_is_ready_and_used_for_history(self):
        with patch.object(nara_cli, "load_config", return_value={"timezone": "America/Los_Angeles", "family": "family", "child": "child-b", "child_label": "Baby B"}):
            result = nara_cli.execute(nara_cli.parser().parse_args(["onboard"]))
            history = nara_cli.execute(nara_cli.parser().parse_args(["history"]))
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["child"], "Baby B")
        self.assertEqual([t["type"] for t in history["tracks"]], ["SLEEP"])

    def test_history_without_selection_requires_onboarding(self):
        with patch.object(nara_cli, "connected_client") as connect:
            result = nara_cli.execute(nara_cli.parser().parse_args(["history"]))
        self.assertEqual(result["state"], "needs_child_selection")
        connect.assert_not_called()

    def test_read_auth_failure_retries_once_and_refreshes_token(self):
        with nara_client.connected_client(child="child-b") as api:
            failed = Response({})
            failed.status_code = 401
            failed.raise_for_status = lambda: (_ for _ in ()).throw(RuntimeError("token-canary"))
            with patch.object(api, "_authenticate") as auth, patch.object(FakeTransport, "request", return_value=failed) as request:
                auth.side_effect = lambda: setattr(api, "id_token", "refreshed-canary")
                with self.assertRaises(RuntimeError):
                    api.get_data()
                self.assertEqual(request.call_count, 2)
                auth.assert_called_once()
                self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer refreshed-canary")

    def test_writes_are_disabled_before_http_by_default(self):
        with nara_client.connected_client(child="child-b") as api:
            with patch.object(FakeTransport, "request") as request:
                with self.assertRaisesRegex(nara_keychain.NaraError, "Writes require"):
                    api._do_request("PATCH", api.DB_URL + "/example.json", json={})
                request.assert_not_called()

    def test_enabled_write_is_never_retried_on_auth_failure(self):
        with nara_client.connected_client(child="child-b", allow_writes=True) as api:
            failed = Response({})
            failed.status_code = 401
            failed.raise_for_status = lambda: (_ for _ in ()).throw(RuntimeError("token-canary"))
            with patch.object(FakeTransport, "request", return_value=failed) as request, patch.object(api, "_authenticate") as auth:
                with self.assertRaises(RuntimeError):
                    api._do_request("PATCH", api.DB_URL + "/example.json", json={})
                request.assert_called_once()
                auth.assert_not_called()

    def test_duplicate_names_cannot_change_default(self):
        with patch.object(nara_cli, "child_choices", return_value=[{"key": "a", "name": "Example"}, {"key": "b", "name": "Example"}]), patch.object(nara_cli, "save_config") as save:
            with self.assertRaises(nara_keychain.NaraError):
                nara_cli.execute(nara_cli.parser().parse_args(["configure", "--name", "Example"]))
            save.assert_not_called()

    def test_sync_only_record_edit_uses_existing_id_and_preserves_fields(self):
        original = {"childKey": "child-b", "type": "DIAPER", "beginDt": 123, "tz": "UTC", "note": "preserve", "etag": "old"}
        saved = dict(original, diaperPoopColor="YELLOW", diaperPoopTexture="MUSH")
        with nara_client.connected_client(child="child-b", allow_writes=True) as api:
            with patch.object(api, "get_data", side_effect=[{"existing": original}, {"existing": saved}]), patch.object(FakeTransport, "request", return_value=Response({})) as request:
                self.assertEqual(api.patch_activity("existing", {"diaperPoopColor": "YELLOW", "diaperPoopTexture": "MUSHY"}), "existing")
                request.assert_called_once()
                method, url = request.call_args.args
                self.assertEqual(method, "PUT")
                self.assertIn("/instreamz/", url)
                self.assertIn("/value/existing.json", url)
                payload = request.call_args.kwargs["json"]
                self.assertEqual(payload["diaperPoopTexture"], "MUSH")
                for field in ("note", "tz", "beginDt", "etag"):
                    self.assertEqual(payload[field], original[field])

    def test_edit_missing_or_other_child_never_submits(self):
        with nara_client.connected_client(child="child-b", allow_writes=True) as api:
            for records in ({}, {"existing": {"childKey": "child-a"}}):
                with patch.object(api, "get_data", return_value=records), patch.object(FakeTransport, "request") as request:
                    with self.assertRaises(nara_keychain.NaraError):
                        api.patch_activity("existing", {"diaperPoopColor": "YELLOW", "diaperPoopTexture": "MUSHY"})
                    request.assert_not_called()

    def test_edit_unconfirmed_or_failed_submission_never_retries_write(self):
        with nara_client.connected_client(child="child-b", allow_writes=True) as api:
            for failure in (None, RuntimeError("token-canary")):
                with patch.object(api, "get_data", return_value={"existing": {"childKey": "child-b"}}), patch.object(FakeTransport, "request", return_value=Response({}), side_effect=failure) as request, patch.object(nara_client.time, "sleep"):
                    with self.assertRaises(nara_keychain.NaraError) as error:
                        api.patch_activity("existing", {"diaperPoopColor": "YELLOW", "diaperPoopTexture": "MUSHY"})
                    self.assertNotIn("canary", str(error.exception))
                    request.assert_called_once()

    def test_edit_rejects_identity_changes_and_invalid_ids(self):
        with nara_client.connected_client(child="child-b", allow_writes=True) as api:
            with patch.object(FakeTransport, "request") as request:
                for updates in ({"childKey": "child-a"}, {"type": "SLEEP"}, {"etag": "changed"}, {}):
                    with self.assertRaises(nara_keychain.NaraError):
                        api.patch_activity("existing", updates)
                with self.assertRaises(nara_keychain.NaraError):
                    api.get_track("../invalid")
                request.assert_not_called()

    def test_select_default_by_profile_name(self):
        with patch.object(nara_cli, "save_config") as save:
            result = nara_cli.execute(nara_cli.parser().parse_args(["configure", "--name", "baby b"]))
        self.assertEqual(result["preferences"]["child"], "Baby B")
        self.assertNotIn("family", result["preferences"])
        self.assertEqual(save.call_args.args[0]["child"], "child-b")
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
