import sys
import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from nara_bottle import bottle_fields, decoded_volume, log_bottle
from nara_keychain import NaraError
from nara_cli import parser, execute, display_record


class BottleTests(unittest.TestCase):
    def fixture(self):
        api = Mock(family_key='family', activity_timezone='America/Los_Angeles',
                   _selected_child='child', _allow_writes=True)
        tracks = {}
        api.get_data.side_effect = lambda: dict(tracks)
        def save(kind, begin_dt, track_id, **fields):
            tracks[track_id] = dict(fields, type=kind, beginDt=begin_dt,
                                    childKey='child', familyKey='family', tz=api.activity_timezone)
            return track_id
        api.log_activity.side_effect = save
        return api, tracks

    def invoke(self, api, **kwargs):
        return log_bottle(api, child='child', begin=1000, amount='2.5', breast_milk=True, **kwargs)

    def test_observed_two_point_five_encoding(self):
        fields = bottle_fields('2.5')
        self.assertEqual(fields['bottleVolumeNum'], 25)
        self.assertEqual(fields['bottleVolumeExp'], 1)
        self.assertEqual(fields['bottleBreastMilkVolumeNum'], 25)
        self.assertEqual(str(decoded_volume(fields)), '2.5')
        self.assertEqual(display_record(dict(fields, feedType='BOTTLE'), 'UTC')['display']['volume']['amount'], '2.5')

    def test_formula_encoding(self):
        fields = bottle_fields('1.1', False, 'Named formula')
        self.assertEqual(fields['bottleFormulaVolumeNum'], 11)
        self.assertFalse(fields['bottleTypeBreastMilk'])
        self.assertEqual(fields['formulaName'], 'Named formula')

    def test_legacy_python_entrypoint_uses_corrected_encoding(self):
        import nara_client
        source = Path(os.environ.get('NARA_SOURCE_FILE') or Path(__file__).with_name('fixtures') / 'upstream_contract.py')
        with patch.object(nara_client, 'SOURCE', source), patch.object(nara_client, 'SOURCE_SHA256', hashlib.sha256(source.read_bytes()).hexdigest()):
            client_type = nara_client.load_api(Mock())
        api = object.__new__(client_type)
        api.log_activity = Mock(return_value='known-id')
        api.log_bottle_feed(breast_milk=True, volume_floz=2.5, begin_dt=1000, track_id='known-id')
        fields = api.log_activity.call_args.kwargs
        self.assertEqual(fields['bottleVolumeNum'], 25)
        self.assertEqual(fields['bottleBreastMilkVolumeNum'], 25)
        self.assertEqual(fields['track_id'], 'known-id')

    def test_invalid_amounts_never_round(self):
        for value in ['0', '-1', 'nan', 'inf', '2.55', 'oops']:
            with self.subTest(value=value), self.assertRaises(NaraError):
                bottle_fields(value)

    def test_create_and_repeat_have_one_write(self):
        api, tracks = self.fixture()
        self.assertEqual(self.invoke(api)['status'], 'saved')
        self.assertEqual(self.invoke(api)['status'], 'already_recorded')
        api.log_activity.assert_called_once()
        self.assertEqual(len(tracks), 1)

    def test_uncertain_submission_recovers_same_id(self):
        api, tracks = self.fixture()
        save = api.log_activity.side_effect
        def timeout(*args, **kwargs):
            save(*args, **kwargs)
            raise TimeoutError
        api.log_activity.side_effect = timeout
        self.assertTrue(self.invoke(api)['verified'])
        api.log_activity.assert_called_once()

    def test_mismatched_volume_never_reports_success(self):
        api, tracks = self.fixture()
        save = api.log_activity.side_effect
        def wrong(*args, **kwargs):
            key = save(*args, **kwargs)
            tracks[key]['bottleVolumeNum'] = 250
        api.log_activity.side_effect = wrong
        with patch('nara_bottle.time.sleep'), self.assertRaises(NaraError):
            self.invoke(api)
        api.log_activity.assert_called_once()

    def test_existing_wrong_bottle_not_duplicated_or_overwritten(self):
        api, tracks = self.fixture()
        tracks['mobile'] = dict(bottle_fields('25'), type='FEED', beginDt=1000, childKey='child', tz=api.activity_timezone)
        with self.assertRaises(NaraError):
            self.invoke(api)
        api.log_activity.assert_not_called()

    def test_read_only_never_creates(self):
        api, tracks = self.fixture()
        self.assertEqual(self.invoke(api, check_only=True)['status'], 'not_found')
        api.log_activity.assert_not_called()

    def test_wrong_child_fails_before_write(self):
        api, tracks = self.fixture()
        api._selected_child = 'someone_else'
        with self.assertRaises(NaraError):
            self.invoke(api)
        api.log_activity.assert_not_called()

    def test_cli_child_check_and_readonly_client(self):
        api, tracks = self.fixture()
        api.get_children.return_value = {'child': {'name': 'Baby A'}}
        args = parser().parse_args(['log-bottle', '--milk', 'breast-milk', '--amount', '2.5',
             '--unit', 'fl-oz', '--at', '2026-01-15T10:30:00-08:00', '--expect-child', 'Baby A', '--check-only'])
        with patch('nara_cli.load_config', return_value=dict(child='child', family='family', timezone='America/Los_Angeles')), patch('nara_cli.connected_client') as connection:
            connection.return_value.__enter__.return_value = api
            result = execute(args)
            self.assertEqual(result['child'], 'Baby A')
            self.assertFalse(connection.call_args.kwargs['allow_writes'])
            args.expect_child = 'Someone else'
            with self.assertRaises(NaraError):
                execute(args)
        api.log_activity.assert_not_called()


if __name__ == '__main__':
    unittest.main()
