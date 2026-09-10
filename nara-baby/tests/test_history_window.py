import unittest
from unittest.mock import Mock, patch
from nara_cli import execute, parser
from nara_keychain import NaraError

class HistoryWindowTests(unittest.TestCase):
    def run_history(self, extra):
        api = Mock(family_key='family', activity_timezone='UTC')
        api.get_children.return_value = {'child': {'name': 'Baby A'}}
        api.get_data.return_value = {
            str(i): dict(childKey=child, type=kind, beginDt=begin)
            for i, (child, kind, begin) in enumerate([
                ('child','FEED',1000), ('child','DIAPER',2000), ('child','SLEEP',3000),
                ('other','FEED',1500), ('child','FEED','bad'), ('child','PUMP',1500)])}
        with patch('nara_cli.load_config', return_value=dict(family='family',child='child',timezone='UTC')), patch('nara_cli.connected_client') as connect:
            connect.return_value.__enter__.return_value=api
            result=execute(parser().parse_args(['history']+extra))
        api.get_data.assert_called_once()
        return result

    def test_combined_types_window_and_coverage(self):
        result=self.run_history(['--type','FEED,DIAPER,SLEEP','--since','1970-01-01T00:00:01Z','--until','1970-01-01T00:00:03Z','--limit','1'])
        self.assertEqual([r['type'] for r in result['tracks']],['DIAPER'])
        self.assertEqual(result['coverage']['matched'],2)
        self.assertTrue(result['coverage']['truncated'])
        self.assertEqual(result['coverage']['invalid_timestamps'],1)

    def test_old_single_type_command(self):
        self.assertEqual([r['type'] for r in self.run_history(['--type','SLEEP'])['tracks']], ['SLEEP'])

    def test_invalid_window_does_not_connect(self):
        with patch('nara_cli.load_config', return_value=dict(child='child',timezone='UTC')), patch('nara_cli.connected_client') as connect:
            with self.assertRaises(NaraError):
                execute(parser().parse_args(['history','--since','2026-01-02T00:00:00Z','--until','2026-01-01T00:00:00Z']))
            connect.assert_not_called()
