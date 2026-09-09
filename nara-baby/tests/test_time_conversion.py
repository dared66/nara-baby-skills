import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from nara_timezone import epoch_ms, resolve_timezone


class TimeConversionTests(unittest.TestCase):
    def test_no_geographical_default(self):
        with patch.dict(os.environ, {}, clear=True), patch("nara_config.load_config", return_value={}):
            with self.assertRaises(ValueError):
                resolve_timezone()

    def test_timezone_precedence(self):
        with patch.dict(os.environ, {"NARA_TIMEZONE": "Europe/Paris"}), patch("nara_config.load_config", return_value={"timezone": "Asia/Tokyo"}):
            self.assertEqual(resolve_timezone().key, "Europe/Paris")
            self.assertEqual(resolve_timezone("UTC").key, "UTC")

    def test_utc_and_offset_same_instant(self):
        self.assertEqual(epoch_ms("2026-01-01T09:00:00+09:00"), epoch_ms("2026-01-01T00:00:00Z"))

    def test_dst_gap(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            epoch_ms("2026-03-08T02:30:00", "America/New_York")

    def test_dst_overlap(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            epoch_ms("2026-11-01T01:30:00", "America/New_York")
        self.assertEqual(epoch_ms("2026-11-01T01:30:00", "America/New_York", fold=1) - epoch_ms("2026-11-01T01:30:00", "America/New_York", fold=0), 3600000)

    def test_invalid_zone_and_time(self):
        for value in ("not-a-time", "2026-13-01T00:00:00"):
            with self.assertRaises(ValueError):
                epoch_ms(value, "UTC")
        with self.assertRaises(ValueError):
            epoch_ms("2026-01-01T00:00:00", "UTC", fold=2)
