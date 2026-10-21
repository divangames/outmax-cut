"""Local, deterministic product-video assembly. No network or Adobe dependency."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import uuid

import cv2
import numpy as np

FPS = 30
SIZE = 1080
REFERENCE_FRAMES = 676
REFERENCE_BITRATE = 1_064_741
DEFAULT_BITRATE_KBPS = 2500
MIN_BITRATE_KBPS = 500
MAX_BITRATE_KBPS = 2500


def video_bitrate(settings):
    value = settings.get("bitrate_kbps", DEFAULT_BITRATE_KBPS)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not MIN_BITRATE_KBPS <= value <= MAX_BITRATE_KBPS or int(value) != value:
        raise ValueError("Битрейт должен быть целым числом от 500 до 2500 кбит/с.")
    return int(value)


MODEL_SECONDS = 341 / 30
HANDS_SECONDS = 496 / 30
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))


class Cancelled(Exception):
    pass


def binary(name):
    bundled = RESOURCES / "bin" / (name + (".exe" if os.name == "nt" else ""))
    if not bundled.exists() and not getattr(sys, "frozen", False):
        bundled = RESOURCES / "vendor" / "bin" / (name + (".exe" if os.name == "nt" else ""))
    path = str(bundled) if bundled.exists() else shutil.which(name)
    if not path:
        raise RuntimeError(f"Не найден {name}. Запустите BUILD.bat или установите FFmpeg.")
    return path


def run(args, cancel=None, timeout=600):
    """Drain process output without deadlocks; kill on cancellation and timeout."""
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=NO_WINDOW)
    import time
    started = time.monotonic()
    while True:
        try:
            out, err = proc.communicate(timeout=.25)
            break
        except subprocess.TimeoutExpired:
            if (cancel and cancel.is_set()) or time.monotonic() - started > timeout:
                proc.kill()
                proc.communicate()
                if cancel and cancel.is_set():
                    raise Cancelled()
                raise RuntimeError("Обработка заняла слишком много времени.")
    if proc.returncode:
        raise RuntimeError(err.decode("utf-8", "replace")[-2500:] or "Ошибка видеодекодера.")
    return out


def probe(path):
    raw = json.loads(run([binary("ffprobe"), "-v", "error", "-show_format",
                          "-show_streams", "-of", "json", str(path)], timeout=30))
    video = next((s for s in raw["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise ValueError("В файле нет видеодорожки.")
    duration = float(video.get("duration") or raw["format"].get("duration", 0))
    if not math.isfinite(duration) or not 1 <= duration <= 600:
        raise ValueError("Нужно видео длительностью от 1 секунды до 10 минут.")
    w, h = video["width"], video["height"]
    rotation = next((s.get("rotation", 0) for s in video.get("side_data_list", [])
                     if "rotation" in s), 0)
    if abs(rotation) % 180 == 90:
        w, h = h, w
    return dict(duration=duration, width=w, height=h, codec=video["codec_name"],
                hdr=video.get("color_transfer") in ("smpte2084", "arib-std-b67"),
                transfer=video.get("color_transfer", "bt709"),
                size=Path(path).stat().st_size)


def color_filter(info):
    if info["hdr"]:
        return ("zscale=t=linear:npl=100,format=gbrpf32le,"
                "zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
                "zscale=t=bt709:m=bt709:r=tv,format=yuv420p,")
    return ""


def normalize(source, info, dest, crop, cancel, size=SIZE):
    filt = (color_filter(info) +
            f"crop=min(iw\\,ih):min(iw\\,ih):(iw-ow)/2:(ih-oh)*{crop:.6f},"
            f"scale={size}:{size}:flags=lanczos,setsar=1,fps={FPS},format=yuv420p")
    run([binary("ffmpeg"), "-v", "error", "-y", "-i", str(source), "-an",
         "-vf", filt, "-c:v", "libx264", "-preset", "fast", "-crf", "15",
         "-threads", "4", "-map_metadata", "-1", str(dest)], cancel)


def make_proxy(source, info, dest, cancel=None):
    filt = color_filter(info) + "scale=360:640:force_original_aspect_ratio=decrease,setsar=1,fps=15,format=yuv420p"
    run([binary("ffmpeg"), "-v", "error", "-y", "-i", str(source), "-an",
         "-vf", filt, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "25",
         "-threads", "2", "-movflags", "+faststart", str(dest)], cancel, timeout=180)


def template_segments(durations):
    # Recovered from НОГИ-РУКИ НОВАЯ.prproj. Values are source and sequence frames.
    recipe = [
        (0, 28, 93, 65), (0, 93, 130, 37), (0, 130, 152.5, 15),
        (0, 153, 188, 35), (0, 188, 204.5, 11), (0, 204, 318, 114),
        (1, .5, 465.5, 372), (0, 5, 31, 26),
    ]
    return [dict(source=s, start=a / 30 * durations[s] / [MODEL_SECONDS, HANDS_SECONDS][s],
                 end=b / 30 * durations[s] / [MODEL_SECONDS, HANDS_SECONDS][s],
                 frames=n, label=("Модель" if s == 0 else "Руки"))
            for s, a, b, n in recipe]


def active_intervals(path, sensitivity, cancel):
    """Motion-based pause detection; never claims semantic understanding of a pose."""
    cap = cv2.VideoCapture(str(path))
    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / FPS
    times, scores = [], []
    prev = None
    try:
        for t in np.arange(0, duration, .2):
            if cancel.is_set():
                raise Cancelled()
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            gray = cv2.cvtColor(cv2.resize(frame, (128, 128)), cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            if prev is not None:
                scores.append(float(np.mean(cv2.absdiff(gray, prev))))
                times.append(float(t))
            prev = gray
    finally:
        cap.release()
    if not scores:
        return [(0, duration)]
    threshold = max(.4, float(np.percentile(scores, 80)) * (.04 + sensitivity * .003))
    active = np.array(scores) > threshold
    # Keep 0.4 s either side of motion, suppress cuts on short still poses.
    padded = active.copy()
    for i in range(len(active)):
        padded[i] = active[max(0, i-2):min(len(active), i+3)].any()
    ranges, start = [], None
    for i, yes in enumerate(padded):
        if yes and start is None:
            start = max(0, times[i] - .2)
        if start is not None and (not yes or i == len(padded)-1):
            end = min(duration, times[i] if not yes else times[i]+.2)
            if end - start >= .4:
                ranges.append((start, end))
            start = None
    if not ranges:
        return [(0, duration)]
    merged = [ranges[0]]
    for a, b in ranges[1:]:
        if a - merged[-1][1] < .8:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def smart_segments(paths, sensitivity, cancel):
    result = []
    for s, path in enumerate(paths):
        ranges = active_intervals(path, sensitivity, cancel)
        budget = [277, 372][s]
        total = sum(b-a for a, b in ranges)
        # Largest-remainder allocation keeps the exact frame count.
        weights = np.array([(b-a)/total*budget for a, b in ranges])
        counts = np.floor(weights).astype(int)
        for i in np.argsort(-(weights-counts))[:budget-int(counts.sum())]:
            counts[i] += 1
        for (a, b), frames in zip(ranges, counts):
            if frames:
                result.append(dict(source=s, start=a, end=b, frames=int(frames),
                                   label="Модель" if s == 0 else "Руки"))
    # Neutral opening shot of model is the reference's closing shot.
    result.append(dict(source=0, start=0, end=.8666667, frames=26, label="Финал"))
    return result


class FrameReader:
    def __init__(self, path):
        self.cap = cv2.VideoCapture(str(path))
        self.count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.position = -1
        self.frame = None
        if self.count == 0:
            raise RuntimeError("Не удалось открыть подготовленное видео.")

    def get(self, seconds):
        index = min(self.count-1, max(0, round(seconds * FPS)))
        if index == self.position and self.frame is not None:
            return self.frame.copy()
        if index < self.position or index > self.position + 12:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            self.position = index - 1
        while self.position < index:
            ok, frame = self.cap.read()
            if not ok:
                raise RuntimeError("Не удалось декодировать кадр.")
            self.frame = frame
            self.position += 1
        return self.frame.copy()

    def close(self):
        self.cap.release()


def morph(a, b, fraction):
    """Bidirectional dense optical-flow warp, not a renamed dissolve."""
    small = 270
    ga = cv2.cvtColor(cv2.resize(a, (small, small)), cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(cv2.resize(b, (small, small)), cv2.COLOR_BGR2GRAY)
    flow_ab = cv2.calcOpticalFlowFarneback(ga, gb, None, .5, 4, 25, 5, 7, 1.5, 0)
    flow_ba = cv2.calcOpticalFlowFarneback(gb, ga, None, .5, 4, 25, 5, 7, 1.5, 0)
    h, w = a.shape[:2]
    ab = cv2.resize(flow_ab, (w, h)) * (w / small)
    ba = cv2.resize(flow_ba, (w, h)) * (w / small)
    x, y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    wa = cv2.remap(a, x-fraction*ab[..., 0], y-fraction*ab[..., 1],
                   cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
    wb = cv2.remap(b, x-(1-fraction)*ba[..., 0], y-(1-fraction)*ba[..., 1],
                   cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
    return cv2.addWeighted(wa, 1-fraction, wb, fraction, 0)


def transition(a, b, fraction, kind):
    ease = fraction * fraction * (3 - 2 * fraction)
    if kind == "morph":
        return morph(a, b, ease)
    if kind == "cut":
        return b if fraction >= .5 else a
    mixed = cv2.addWeighted(a, 1-ease, b, ease, 0)
    sigma = 22 * math.sin(math.pi * fraction) ** 2
    if sigma > .2:
        # Low-res blur is substantially faster at 1080p.
        small = cv2.resize(mixed, (360, 360), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), sigma / 3)
        mixed = cv2.resize(small, (SIZE, SIZE), interpolation=cv2.INTER_LINEAR)
    return mixed


def render(sources, infos, settings, work, output, progress, cancel):
    paths = []
    readers = []
    proc = None
    temp_output = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.partial.mp4")
    try:
        for s in range(2):
            progress(4 + s * 12, f"Подготовка видео: {'модель' if s == 0 else 'руки'}")
            path = work / f"normalized-{s}.mp4"
            normalize(sources[s], infos[s], path, settings["crops"][s], cancel)
            paths.append(path)
        progress(29, "Анализ движения и точек монтажа")
        if settings["mode"] == "smart":
            segments = smart_segments(paths, settings["sensitivity"], cancel)
        else:
            segments = template_segments([i["duration"] for i in infos])
        readers = [FrameReader(p) for p in paths]
        timeline = []
        for seg in segments:
            for i in range(seg["frames"]):
                timeline.append((seg["source"], seg["start"] +
                                 (seg["end"]-seg["start"])*i/seg["frames"]))
        assert len(timeline) == REFERENCE_FRAMES - 1
        transitions = {}
        # Reference transitions: 9.267–10.033 and 21.5–22.167 s.
        # Preserve the total duration; sample source handles around each boundary.
        for boundary, length, lead in [(277, 23, 0), (649, 20, 5)]:
            if settings["transition"] != "cut":
                for j in range(length):
                    at = boundary - lead + j
                    transitions[at] = (boundary, j, length, lead)
        intermediate = work / "assembled.mp4"
        errfile = work / "encoder.log"
        with errfile.open("wb") as error:
            proc = subprocess.Popen([
                binary("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo",
                "-pix_fmt", "bgr24", "-s", "1080x1080", "-r", "30",
                "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "fast",
                "-crf", "16", "-threads", "4", "-pix_fmt", "yuv420p",
                str(intermediate)], stdin=subprocess.PIPE, stderr=error, creationflags=NO_WINDOW)
            # The original has exactly one black opening frame.
            proc.stdin.write(np.zeros((SIZE, SIZE, 3), np.uint8).tobytes())
            for index, (s, t) in enumerate(timeline):
                if cancel.is_set():
                    raise Cancelled()
                frame = readers[s].get(t)
                if index in transitions:
                    boundary, j, n, lead = transitions[index]
                    old_s, old_t = timeline[boundary-1]
                    new_s, new_t = timeline[boundary]
                    a = readers[old_s].get(old_t + (j-lead+1)/FPS)
                    b = readers[new_s].get(new_t + (j-lead)/FPS)
                    frame = transition(a, b, j/(n-1), settings["transition"])
                proc.stdin.write(frame.tobytes())
                if index % 10 == 0:
                    progress(32 + 43 * (index+1)/(REFERENCE_FRAMES - 1), "Монтаж и переходы")
            proc.stdin.close()
            proc.wait(timeout=120)
            if proc.returncode:
                raise RuntimeError(errfile.read_text(errors="replace")[-2000:])
        proc = None
        for reader in readers:
            reader.close()
        readers = []
        # Two-pass average bitrate gives predictable size, even on different shoes.
        passlog = str(work / "two-pass")
        common = [binary("ffmpeg"), "-v", "error", "-y", "-i", str(intermediate)]
        bitrate = video_bitrate(settings)
        encoding = ["-c:v", "libx264", "-b:v", str(bitrate * 1000),
                    "-maxrate", str(bitrate * 1000), "-bufsize", str(bitrate * 2000),
                    "-preset", "medium", "-profile:v", "high", "-level", "3.2",
                    "-pix_fmt", "yuv420p", "-threads", "4",
                    "-passlogfile", passlog]
        progress(77, f"Сжатие · {bitrate} кбит/с · проход 1 из 2")
        run(common + encoding + ["-pass", "1", "-an", "-f", "null", os.devnull], cancel)
        progress(88, f"Сжатие · {bitrate} кбит/с · проход 2 из 2")
        run(common + ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"] +
            encoding + ["-pass", "2", "-map", "0:v:0", "-map", "1:a:0",
                        "-c:a", "aac", "-b:a", "64k", "-t", str(REFERENCE_FRAMES/FPS),
                        "-movflags", "+faststart", "-map_metadata", "-1",
                        "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-colorspace", "bt709", str(temp_output)], cancel)
        if cancel.is_set():
            raise Cancelled()
        result = probe(temp_output)
        if (result["width"], result["height"]) != (1080, 1080):
            raise RuntimeError("Проверка формата результата не пройдена.")
        if os.name == "nt":
            temp_output.rename(output)  # Windows refuses to replace an existing file.
        else:
            os.link(temp_output, output)
            temp_output.unlink()
        report = dict(generator="OUTMAX Cut", segments=segments, settings=settings, result=result,
                      frames=REFERENCE_FRAMES, fps=FPS, transition_note="Independent Lens Blur approximation / optical flow")
        progress(100, "Видео готово")
        return report
    finally:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
        for reader in readers:
            reader.close()
        temp_output.unlink(missing_ok=True)
        for path in work.glob("normalized-*.mp4"):
            path.unlink(missing_ok=True)
        (work / "assembled.mp4").unlink(missing_ok=True)
        for path in work.glob("two-pass*"):
            path.unlink(missing_ok=True)
