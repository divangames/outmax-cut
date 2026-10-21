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


class MontageTests(unittest.TestCase):
    def test_premiere_timing(self):
        segments = template_segments([MODEL_SECONDS, HANDS_SECONDS])
        self.assertEqual(sum(s["frames"] for s in segments), 684)
        self.assertEqual(sum(s["frames"] for s in segments[:6]), 277)
        self.assertAlmostEqual(segments[6]["start"], .5/30)
        self.assertAlmostEqual(segments[6]["end"], 15.8916666667)
        self.assertEqual(segments[6]["frames"], 381)

    def test_scaled_sources_stay_inside_source(self):
        for durations in ([1, 1], [7.1, 12.7], [600, 500]):
            for segment in template_segments(durations):
                self.assertGreaterEqual(segment["start"], 0)
                self.assertLessEqual(segment["end"], durations[segment["source"]])
                self.assertGreater(segment["end"], segment["start"])

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
            self.assertEqual(sum(s["frames"] for s in segments), 684)

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
