import unittest
from unittest.mock import Mock,patch
from nara_diaper import log_diaper,diaper_fields
from nara_keychain import NaraError
from nara_cli import parser,execute

class DiaperTests(unittest.TestCase):
    def fixture(self):
        api=Mock(family_key='family',activity_timezone='UTC',_selected_child='child',_allow_writes=True)
        data={}
        api.get_data.side_effect=lambda:dict(data)
        api.get_children.return_value={'child':{'name':'Baby A'}}
        def save(kind,begin_dt,track_id,**fields):
            data[track_id]=dict(fields,type=kind,beginDt=begin_dt,childKey='child',tz='UTC')
            return track_id
        api.log_activity.side_effect=save
        return api,data
    def invoke(self,api,**extra):return log_diaper(api,child='child',begin=1000,contents='both',color='yellow',texture='mushy',**extra)
    def test_create_and_repeat_one_write(self):
        api,data=self.fixture()
        self.assertEqual(self.invoke(api)['status'],'saved')
        self.assertEqual(self.invoke(api)['status'],'already_recorded')
        api.log_activity.assert_called_once()
        self.assertEqual(len(data),1)
        record=next(iter(data.values()))
        self.assertTrue(record['diaperTypePee'] and record['diaperTypePoop'])
        self.assertEqual(record['diaperPoopTexture'],'MUSH')
        self.assertNotIn('diaperTypeRash',record)
    def test_check_only_does_not_write(self):
        api,_=self.fixture();self.assertEqual(self.invoke(api,check_only=True)['status'],'not_found');api.log_activity.assert_not_called()
    def test_conflicting_existing_record_not_overwritten(self):
        api,data=self.fixture();self.invoke(api);next(iter(data.values()))['diaperPoopColor']='GREEN'
        with self.assertRaises(NaraError):self.invoke(api)
        api.log_activity.assert_called_once()
    def test_lost_submission_response_recovers(self):
        api,_=self.fixture();save=api.log_activity.side_effect
        def timeout(*a,**kw):save(*a,**kw);raise TimeoutError()
        api.log_activity.side_effect=timeout
        self.assertTrue(self.invoke(api)['verified']);api.log_activity.assert_called_once()
    def test_wrong_readback_never_reports_saved(self):
        api,_=self.fixture();api.log_activity.side_effect=None
        with patch('nara_diaper.time.sleep'),self.assertRaises(NaraError):self.invoke(api)
        api.log_activity.assert_called_once()
    def test_invalid_observations(self):
        for contents,color in [('both','blue'),('wet','yellow')]:
            with self.assertRaises(NaraError):diaper_fields(contents,color)
    def test_cli_handles_config_time_and_verification(self):
        api,_=self.fixture()
        args=parser().parse_args(['log-diaper','--contents','both','--color','yellow','--texture','mushy','--at','1970-01-01T00:00:01Z','--expect-child','Baby A'])
        with patch('nara_cli.load_config',return_value={'family':'family','child':'child','timezone':'UTC'}),patch('nara_cli.connected_client') as connect:
            connect.return_value.__enter__.return_value=api
            result=execute(args)
            self.assertTrue(result['verified'])
            self.assertEqual(result['child'],'Baby A')
            self.assertEqual(api.log_activity.call_args.kwargs['begin_dt'],1000)
            connect.assert_called_once_with(family='family',child='child',timezone_name='UTC',allow_writes=True)
    def test_wrong_child_stops_before_write(self):
        api,_=self.fixture()
        args=parser().parse_args(['log-diaper','--contents','wet','--at','1970-01-01T00:00:01Z','--expect-child','Different child'])
        with patch('nara_cli.load_config',return_value={'family':'family','child':'child','timezone':'UTC'}),patch('nara_cli.connected_client') as connect:
            connect.return_value.__enter__.return_value=api
            with self.assertRaises(NaraError):execute(args)
            api.log_activity.assert_not_called()
