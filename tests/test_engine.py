import pathlib
import sys
import threading
import tempfile
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engine import template_segments, morph, run, Cancelled, MODEL_SECONDS, HANDS_SECONDS, active_intervals, smart_segments
from app import app, TOKEN, validate_settings
from engine import transition, output_dimensions, scan_content, content_bounds, scene_bounds


class MontageTests(unittest.TestCase):
    def test_formats_and_crop_validation(self):
        for name, dimensions in (("standard", (1080,1080)), ("marketplace", (900,1200)), ("vertical", (1080,1920))):
            self.assertEqual(output_dimensions(validate_settings({"format":name})), dimensions)
            width,height=output_dimensions({"format":name,"preview":True})
            self.assertLessEqual(max(width,height),480)
            self.assertAlmostEqual(width/height,dimensions[0]/dimensions[1],places=2)
        for data in ({"format":"bad"},{"format":[]},{"formats":[]},{"formats":["standard","standard"]},{"formats":["unknown"]},{"formats":"vertical"},{"crops_x":[-1,.5]},{"crops_x":None},{"crops_x":[True,.5]}):
            with self.assertRaises(ValueError):validate_settings(data)

    def test_transitions_preserve_portrait_shape(self):
        a=np.zeros((480,270,3),np.uint8)
        b=np.full_like(a,200)
        for kind in ("lens","morph","cut"):
            self.assertEqual(transition(a,b,.5,kind).shape,a.shape)

    def test_premiere_timing(self):
        segments = template_segments([MODEL_SECONDS, HANDS_SECONDS])
        self.assertEqual(sum(s["frames"] for s in segments), 676)
        self.assertEqual(sum(s["frames"] for s in segments[:6]), 277)
        self.assertAlmostEqual(segments[6]["start"], .5/30)
        self.assertAlmostEqual(segments[6]["end"], 15.8916666667)
        self.assertEqual(segments[6]["frames"], 381)

    def test_scaled_sources_stay_inside_source(self):
        for durations in ([1, 1], [7.1, 12.7], [600, 500]):
            for segment in template_segments(durations):
                self.assertGreaterEqual(segment["start"], 0)
                self.assertLessEqual(segment["end"], durations[segment["source"]])
                self.assertGreaterEqual(segment["end"], segment["start"])

    def test_loop_return_ends_at_the_first_useful_frame(self):
        segments=template_segments([MODEL_SECONDS,HANDS_SECONDS])
        self.assertTrue(segments[-1]['loop'])
        self.assertEqual(segments[-1]['frames'],18)
        self.assertEqual(segments[-1]['end'],segments[0]['start'])
        self.assertEqual(sum(s['frames'] for s in segments),676)

    def test_no_blank_backdrop_signal_keeps_complete_source(self):
        analysis=dict(duration=10,times=list(range(10)),details=[4,4.1,4.2,4.1,4,4.2,4.1,4.1,4,4])
        self.assertEqual(content_bounds(analysis),(0,10))

    def test_exposure_drift_on_empty_backdrop_is_trimmed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'backdrop.avi'
            writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),30,(128,128))
            for i in range(210):
                frame=np.full((128,128,3),150+int(10*np.sin(i/12)),np.uint8)
                if 60<=i<150:
                    x=30+int(10*np.sin(i/8))
                    cv2.rectangle(frame,(x,25),(x+45,105),(25,25,25),-1)
                    for y in range(30,100,10):cv2.line(frame,(x,y),(x+45,y),(240,240,240),2)
                writer.write(frame)
            writer.release()
            bounds=content_bounds(scan_content(path,threading.Event()))
            self.assertGreaterEqual(bounds[0],2)
            self.assertLessEqual(bounds[1],5.05)
            segments=smart_segments([path,path],40,threading.Event())
            self.assertLess(segments[0]['start'],bounds[0])
            model=[s for s in segments if s['source']==0 and not s.get('loop')]
            self.assertGreater(model[-1]['end'],bounds[1])
            for segment in segments:
                if not segment.get('loop'):
                    self.assertEqual(segment['speed'],1.25)
                    self.assertEqual(segment['frames'],round((segment['end']-segment['start'])/1.25*30))
            self.assertEqual(segments[-1]['end'],segments[0]['start'])

    def test_morph_moves_shape_not_just_opacity(self):
        a = np.zeros((270, 270, 3), np.uint8)
        b = a.copy()
        cv2.circle(a, (120, 130), 30, (255, 255, 255), -1)
        cv2.circle(b, (138, 130), 30, (255, 255, 255), -1)
        mid = morph(a, b, .5)
        dissolve = cv2.addWeighted(a, .5, b, .5, 0)
        self.assertGreater(float(np.mean(cv2.absdiff(mid, dissolve))), .1)
        np.testing.assert_array_equal(morph(a, b, 0), a)
        np.testing.assert_array_equal(morph(a, b, 1), b)

    def test_cancel_terminates_child(self):
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(Cancelled):
            run([sys.executable, "-c", "import time; time.sleep(30)"], cancelled)

    def test_motion_analysis_removes_long_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "motion.avi"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (128, 128))
            for i in range(240):
                frame = np.zeros((128, 128, 3), dtype=np.uint8)
                x = 20
                if 45 <= i < 90:
                    x = 20 + (i-45)
                elif 90 <= i < 165:
                    x = 64
                elif 165 <= i < 210:
                    x = 64 - (i-165)
                cv2.rectangle(frame, (x, 40), (x+25, 85), (240,240,240), -1)
                writer.write(frame)
            writer.release()
            ranges = active_intervals(path, 40, threading.Event())
            self.assertGreaterEqual(len(ranges), 2)
            self.assertLess(sum(b-a for a,b in ranges), 7)
            segments = smart_segments([path,path], 40, threading.Event())
            self.assertTrue(all(s.get('speed')==1.25 for s in segments if not s.get('loop')))

    def test_invalid_settings_and_csrf(self):
        for data in ({"crops":[float("nan"),.5]}, {"crops":[-1,.5]},
                     {"mode":"bad"}, {"transition":"fake"}, {"sensitivity":float("inf")}):
            with self.assertRaises(ValueError):
                validate_settings(data)
        with app.test_client() as client:
            self.assertEqual(client.post("/api/render", json={}).status_code, 403)
            self.assertEqual(client.post("/api/render", json={},
                             headers={"X-Outmax-Token":TOKEN}).status_code, 400)
            self.assertEqual(client.get("/", headers={"Host":"example.com"}).status_code, 403)
            self.assertEqual(client.get("/media/not-a-source").status_code, 404)


if __name__ == "__main__":
    unittest.main()
