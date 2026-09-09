import contextlib
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nara_cli


class HistoryDisplayTests(unittest.TestCase):
    def test_display_preserves_data_and_formats_local_time_and_duration(self):
        record = {'beginDt': 1768501800000, 'breastLeftDuration': 750000}
        result = nara_cli.display_record(record, 'America/Los_Angeles')
        self.assertEqual(result['display']['local_times']['beginDt'], '2026-01-15T10:30:00-08:00')
        self.assertEqual(result['display']['durations']['breastLeftDuration'], '12 min 30 sec')
        self.assertNotIn('breastRightDuration', result['display']['durations'])
        self.assertEqual(record, {'beginDt': 1768501800000, 'breastLeftDuration': 750000})

    def test_unknown_values_are_not_zero_or_completed(self):
        result = nara_cli.display_record({'beginDt': None, 'breastLeftDuration': -1,
                                         'breastRightDuration': True}, 'UTC')
        self.assertEqual(result['display'], {'local_times': {}, 'durations': {}})

    def test_dst_offset_comes_from_requested_zone(self):
        winter = nara_cli.display_record({'beginDt': 1767268800000}, 'America/Los_Angeles')
        self.assertTrue(winter['display']['local_times']['beginDt'].endswith('-08:00'))

    def test_history_filters_before_limit_and_uses_single_connection(self):
        api = Mock(family_key='family', activity_timezone='America/Los_Angeles')
        api.get_children.return_value = {'a': {'name': 'Baby A'}}
        api.get_data.return_value = {
            'wrong-child': {'childKey': 'b', 'type': 'FEED', 'beginDt': 9999999999999},
            'wrong-type': {'childKey': 'a', 'type': 'DIAPER', 'beginDt': 9999999999999},
            'older': {'childKey': 'a', 'type': 'FEED', 'beginDt': 1768498200000},
            'latest': {'childKey': 'a', 'type': 'FEED', 'beginDt': 1768501800000,
                       'breastLeftDuration': 750000},
        }
        args = nara_cli.parser().parse_args(['history', '--type', 'FEED', '--limit', '1', '--display'])
        with patch.object(nara_cli, 'load_config', return_value={
            'child': 'a', 'family': 'family', 'timezone': 'America/Los_Angeles'
        }), patch.object(nara_cli, 'connected_client', return_value=contextlib.nullcontext(api)) as connection:
            result = nara_cli.execute(args)
        connection.assert_called_once_with(family='family', child='a', timezone_name='America/Los_Angeles')
        api.get_data.assert_called_once()
        self.assertEqual(result['child'], 'Baby A')
        self.assertEqual(len(result['tracks']), 1)
        self.assertEqual(result['tracks'][0]['beginDt'], 1768501800000)
        self.assertNotIn('key', result['tracks'][0])
        self.assertIn('display', result['tracks'][0])

    def test_missing_selection_returns_setup_without_connecting(self):
        args = nara_cli.parser().parse_args(['history', '--display'])
        with patch.object(nara_cli, 'load_config', return_value={}), patch.object(nara_cli, 'connected_client') as connection:
            result = nara_cli.execute(args)
        self.assertEqual(result['state'], 'needs_child_selection')
        connection.assert_not_called()


if __name__ == '__main__':
    unittest.main()
