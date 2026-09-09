"""Offline tests against a supplied checkout of the upstream API."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from nara_timezone import epoch_ms, timezone_client

if not os.environ.get("NARA_SOURCE_FILE"):
    raise unittest.SkipTest("Upstream compatibility suite: supply --upstream to scripts/test.py")
spec = importlib.util.spec_from_file_location("nara_upstream", os.environ["NARA_SOURCE_FILE"])
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)


class CaptureAPI(timezone_client(upstream.NaraAPI)):
    def _authenticate(self):
        self.uid, self.family_key, self.child_key = "test-user", "test-family", "test-child"

    def _push_payload(self, payload, track_id=None):
        self.payload = payload
        return "test-track"


class TimezoneTests(unittest.TestCase):
    def setUp(self):
        # Any accidental network use fails; no test credentials reach a server.
        self.network = patch.object(upstream.requests.sessions.Session, "request", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.env = patch.dict(os.environ, {"NARA_TIMEZONE": "America/Los_Angeles"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.api = CaptureAPI("test", "test")

    def test_every_creation_helper_uses_pacific(self):
        calls = [
            ("log_activity", ("SLEEP",)), ("log_note", ("test",)),
            ("log_breast_feed", ()), ("start_breast_feed", ()),
            ("start_sleep", ()), ("start_pump", ()),
            ("log_bottle_feed", ()), ("log_solid_feed", ()),
            ("log_combo_feed", ()), ("log_milestone", ("test",)),
            ("log_medical_appointment", ()), ("log_vaccine", ("test",)),
            ("log_diaper", ()), ("log_sleep", (1000, 2000)),
            ("log_routine", ("BATH",)), ("log_growth", ()),
            ("log_health", ()), ("log_pump", (1000, 2000)),
        ]
        for name, args in calls:
            with self.subTest(name=name), contextlib.redirect_stdout(io.StringIO()):
                getattr(self.api, name)(*args)
                self.assertEqual(self.api.payload["tz"], "America/Los_Angeles")

    def test_override_and_invalid_zone_before_login(self):
        with patch.dict(os.environ, {"NARA_TIMEZONE": "Europe/London"}):
            self.assertEqual(CaptureAPI("test", "test").activity_timezone, "Europe/London")
            self.assertEqual(CaptureAPI("test", "test", timezone_name="Asia/Tokyo").activity_timezone, "Asia/Tokyo")
        with patch.object(CaptureAPI, "_authenticate") as login:
            with self.assertRaises(ValueError):
                CaptureAPI("test", "test", timezone_name="/bad-zone")
            login.assert_not_called()
        with contextlib.redirect_stdout(io.StringIO()):
            self.api.log_diaper(tz="Europe/London", begin_dt=123456)
        self.assertEqual(self.api.payload["tz"], "Europe/London")
        self.assertEqual(self.api.payload["beginDt"], 123456)
        self.assertEqual(self.api.payload["ord"], -123456)

    def test_pacific_winter_and_summer(self):
        self.assertEqual(epoch_ms("2026-01-15T09:00:00"), epoch_ms("2026-01-15T17:00:00+00:00"))
        self.assertEqual(epoch_ms("2026-07-15T09:00:00"), epoch_ms("2026-07-15T16:00:00+00:00"))

    def test_timer_stops_preserve_original_timezone(self):
        for method in ("stop_sleep", "stop_breast_feed", "stop_pump"):
            with self.subTest(method=method):
                record = {"tz": "Europe/London", "beginDt": 1000}

                class Response:
                    status_code = 200

                    def json(self):
                        return dict(record)

                def request(verb, url, **kwargs):
                    if verb == "PATCH":
                        record.update(kwargs["json"])
                    elif verb == "PUT":
                        self.assertEqual(kwargs["json"]["tz"], "Europe/London")
                    return Response()

                with patch.object(self.api, "_do_request", side_effect=request):
                    getattr(self.api, method)("test-track")
                self.assertEqual(record["tz"], "Europe/London")

    def test_dst_gap_and_repeated_hour(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            epoch_ms("2026-03-08T02:30:00")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            epoch_ms("2026-11-01T01:30:00")
        first = epoch_ms("2026-11-01T01:30:00", fold=0)
        second = epoch_ms("2026-11-01T01:30:00", fold=1)
        self.assertEqual(second - first, 3600000)
        self.assertEqual(first, epoch_ms("2026-11-01T01:30:00-07:00"))


if __name__ == "__main__":
    unittest.main()
