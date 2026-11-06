import copy
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import app as server
from engine import output_dimensions, smart_segments, probe
from video_formats import DEFAULT_FORMATS, validate_catalog


class EditControlsTests(unittest.TestCase):
    def test_short_manual_results_allow_subsecond_duration_without_relaxing_imports(self):
        metadata=dict(streams=[dict(codec_type='video',codec_name='h264',width=480,height=480,duration='.666667')],format={})
        with patch('engine.run',return_value=json.dumps(metadata).encode()):
            with self.assertRaises(ValueError):probe(__file__)
            self.assertAlmostEqual(probe(__file__,min_duration=1/30,max_duration=1200)['duration'],2/3,places=5)

    def test_proportional_presets_custom_sizes_and_extreme_preview(self):
        catalog=copy.deepcopy(DEFAULT_FORMATS)
        catalog[1].update(width=450,height=600)
        catalog.append(dict(id='custom_site',name='Для сайта',width=640,height=480))
        settings=server.validate_settings(dict(format='custom_site',formats=['marketplace','custom_site'],format_catalog=catalog))
        self.assertEqual(output_dimensions(settings),(640,480))
        self.assertEqual(output_dimensions(settings | {'format':'marketplace'}),(450,600))
        extreme=catalog+[dict(id='thin',name='Узкий',width=32,height=8192)]
        self.assertEqual(output_dimensions({'format':'thin','format_catalog':extreme,'preview':True}),(2,480))
        for change in (dict(width=601),dict(height=1000),dict(name='Другое')):
            invalid=copy.deepcopy(DEFAULT_FORMATS);invalid[1].update(change)
            with self.assertRaises(ValueError):validate_catalog(invalid)
        for custom in (dict(width=641),dict(id='../file'),dict(name='Стандарт'),dict(height=True)):
            invalid=copy.deepcopy(catalog);invalid[-1].update(custom)
            with self.assertRaises(ValueError):validate_catalog(invalid)

    def test_zoom_and_trim_validation(self):
        self.assertEqual(server.validate_settings({'zooms':[1,3],'trims':[[.5,3],None]})['trims'],[[.5,3],None])
        for setting in ({'zooms':[0,1]},{'zooms':[1,float('nan')]},{'zooms':[True,1]},{'trims':[[3,2],None]},{'trims':[[0,.01],None]},{'trims':[[0,float('inf')],None]}):
            with self.assertRaises(ValueError):server.validate_settings(setting)

    def test_manual_bounds_keep_speed_and_override_automatic_edges(self):
        analyses=[dict(duration=10,times=[],motion=[],details=[])]*2
        ranges=[[(0,2),(4,6),(8,10)],[(0,10)]]
        with patch('engine.active_intervals',side_effect=ranges):
            segments=smart_segments(['a','b'],40,None,analyses,[(1,8.5),(.5,9)])
        self.assertEqual(segments[0]['start'],1)
        self.assertEqual(segments[2]['end'],8.5)
        self.assertEqual(segments[3]['start'],.5)
        self.assertEqual(segments[3]['end'],9)
        self.assertTrue(all(s.get('speed',1.25)==1.25 for s in segments))
        self.assertEqual(segments[-1]['start'],1)

    def test_custom_format_preferences_persist_and_jobs_freeze_sizes(self):
        catalog=copy.deepcopy(DEFAULT_FORMATS)+[dict(id='custom_test',name='Тест',width=800,height=600)]
        result=server.preference_updates({'video_formats':catalog})
        settings=server.validate_settings({'format':'custom_test','format_catalog':result['video_formats']})
        catalog[-1]['width']=1000
        self.assertEqual(output_dimensions(settings),(800,600))

if __name__=='__main__':unittest.main()
