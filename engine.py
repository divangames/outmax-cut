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
from video_formats import DEFAULT_FORMATS, catalog_dimensions
from quality import FrameQuality

FPS = 30
PLAYBACK_SPEED = 1.25
SIZE = 1080
REFERENCE_FRAMES = 685
REFERENCE_BITRATE = 1_064_741
DEFAULT_BITRATE_KBPS = 2500
MIN_BITRATE_KBPS = 500
MAX_BITRATE_KBPS = 2500
FORMATS = {"standard": (1080, 1080), "marketplace": (900, 1200), "vertical": (1080, 1920)}


def output_dimensions(settings):
    name = settings.get("format", "standard")
    width, height = catalog_dimensions(settings.get('format_catalog', DEFAULT_FORMATS), name)
    if settings.get("preview"):
        scale = min(1,480 / max(width, height))
        width, height = (max(2, int(value * scale) // 2 * 2) for value in (width, height))
    return width, height


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


def probe(path, min_duration=1, max_duration=600):
    raw = json.loads(run([binary("ffprobe"), "-v", "error", "-show_format",
                          "-show_streams", "-of", "json", str(path)], timeout=30))
    video = next((s for s in raw["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise ValueError("В файле нет видеодорожки.")
    duration = float(video.get("duration") or raw["format"].get("duration", 0))
    if not math.isfinite(duration) or not min_duration <= duration <= max_duration:
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


def normalize(source, info, dest, crop, cancel, size=SIZE, width=None, height=None, crop_x=.5, preview=False, zoom=1):
    width, height = width or size, height or size
    ratio = width / height
    filt = (f"fps={FPS},crop=min(iw\\,ih*{ratio:.9f})/{zoom:.9f}:min(ih\\,iw/{ratio:.9f})/{zoom:.9f}:(iw-ow)*{crop_x:.6f}:(ih-oh)*{crop:.6f}," +
            color_filter(info) + f"scale={width}:{height}:flags={'bilinear' if preview else 'lanczos'},setsar=1,format=yuv420p")
    run([binary("ffmpeg"), "-v", "error", "-y", "-i", str(source), "-an",
         "-vf", filt, "-c:v", "libx264", "-preset", "ultrafast" if preview else "fast", "-crf", "24" if preview else "15",
         "-g", "30", "-bf", "0",
         "-threads", "4", "-map_metadata", "-1", str(dest)], cancel)


def make_proxy(source, info, dest, cancel=None, progress=None):
    # Tone mapping the small playback proxy avoids processing full-HD float RGB frames.
    # Full exports still tone-map their full-resolution crop in normalize().
    filt = ("fps=30,scale=360:640:force_original_aspect_ratio=decrease:force_divisible_by=2," +
            color_filter(info) + "setsar=1,format=yuv420p")
    args = [binary("ffmpeg"), "-v", "error", "-y", "-i", str(source), "-an",
         "-vf", filt, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "25",
         "-g", "30", "-bf", "0", "-tune", "zerolatency",
         "-threads", "2", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(dest)]
    # Read machine progress on its own thread; run() retains cancellation/timeout handling.
    if progress is None:
        run(args, cancel, timeout=180)
        return
    import time
    with dest.with_suffix(".log").open("wb") as errors:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors, creationflags=NO_WINDOW)
        def read_progress():
            for line in proc.stdout:
                if line.startswith(b"out_time_us="):
                    try:
                        progress(min(.99, int(line.split(b"=", 1)[1]) / 1e6 / info["duration"]))
                    except ValueError:
                        pass
        reader = threading.Thread(target=read_progress, daemon=True)
        reader.start()
        started = time.monotonic()
        try:
            while proc.poll() is None:
                if cancel and cancel.is_set():
                    raise Cancelled()
                if time.monotonic() - started > 600:
                    raise RuntimeError("Подготовка превью заняла слишком много времени.")
                time.sleep(.1)
            if proc.returncode:
                raise RuntimeError(dest.with_suffix(".log").read_text(errors="replace")[-2000:])
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            reader.join(2)
            proc.stdout.close()
    progress(1)


def template_segments(durations):
    # Recovered from НОГИ-РУКИ НОВАЯ.prproj. Values are source and sequence frames.
    recipe = [
        (0, 28, 93, 65), (0, 93, 130, 37), (0, 130, 152.5, 15),
        (0, 153, 188, 35), (0, 188, 204.5, 11), (0, 204, 318, 114),
        (1, .5, 476.75, 381),
    ]
    segments = [dict(source=s, start=a / 30 * durations[s] / [MODEL_SECONDS, HANDS_SECONDS][s],
                 end=b / 30 * durations[s] / [MODEL_SECONDS, HANDS_SECONDS][s],
                 frames=n, label=("Модель" if s == 0 else "Руки"))
            for s, a, b, n in recipe]
    return segments + [loop_return(segments[0], 0)]


def scan_content(path, cancel):
    """Small frames distinguish subject detail from exposure changes on an empty backdrop."""
    cap = cv2.VideoCapture(str(path))
    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or FPS)
    times, scores, details = [], [], []
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
            scores.append(float(np.mean(cv2.absdiff(gray, prev))) if prev is not None else 0.)
            times.append(float(t))
            details.append(float(np.mean(cv2.absdiff(gray, cv2.GaussianBlur(gray, (15, 15), 0)))))
            prev = gray
    finally:
        cap.release()
    return dict(duration=duration, times=times, motion=scores, details=details)


def content_bounds(analysis):
    duration = analysis["duration"]
    details = analysis["details"]
    if not details:
        return (0, duration)
    low, high = np.percentile(details, [15, 80])
    # No clearly empty backdrop: keep the source rather than guess at the subject.
    if high < max(1.2, low * 1.8):
        return (0, duration)
    threshold = low + (high - low) * .2
    present = np.flatnonzero(np.asarray(details) >= threshold)
    start = analysis["times"][int(present[0])]
    end = min(duration, analysis["times"][int(present[-1])] + 1 / FPS)
    return (start, end) if end - start >= .5 else (0, duration)


def active_intervals(path, sensitivity, cancel, analysis=None):
    """Motion-based pause detection; never claims semantic understanding of a pose."""
    analysis = analysis or scan_content(path, cancel)
    duration, times, scores = analysis["duration"], analysis["times"], analysis["motion"]
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


def loop_return(first, minimum):
    return dict(source=0, start=first["start"], end=first["start"],
                frames=18, label="Пустой фон перед появлением модели", loop=True)


def scene_bounds(analysis, source):
    duration=analysis["duration"]
    if source==0 and analysis["details"]:
        low,high=np.percentile(analysis["details"],[15,80])
        if high>=max(1.2,low*1.8):
            present=np.flatnonzero(np.asarray(analysis["details"])>=low+(high-low)*.05)
            # Keep the complete entrance and exit, including a short empty backdrop.
            return (max(0,analysis["times"][int(present[0])]-.4),
                    min(duration,analysis["times"][int(present[-1])]+.4))
    # Hands leave a shoe on the table: texture cannot identify their withdrawal.
    # Use movement, with room after the final motion for the hands to fully leave.
    scores=np.asarray(analysis["motion"])
    if len(scores):
        threshold=max(.3,float(np.percentile(scores,80))*.04)
        moving=np.flatnonzero(scores>threshold)
        if len(moving):
            return (max(0,analysis["times"][int(moving[0])]-.4),
                    min(duration,analysis["times"][int(moving[-1])]+.6))
    return (0,duration)


def smart_segments(paths, sensitivity, cancel, analyses=None, bounds=None, remove_pauses=True):
    analyses = analyses or [scan_content(path, cancel) for path in paths]
    bounds = bounds or [scene_bounds(analysis,s) for s,analysis in enumerate(analyses)]
    result = []
    for s, path in enumerate(paths):
        selected=active_intervals(path,sensitivity,cancel,analyses[s]) if remove_pauses else [bounds[s]]
        ranges = [(max(a, bounds[s][0]), min(b, bounds[s][1])) for a,b in selected]
        ranges = [(a, b) for a, b in ranges if b - a >= 1/FPS] or [bounds[s]]
        ranges[0]=(bounds[s][0],ranges[0][1])
        ranges[-1]=(ranges[-1][0],bounds[s][1])
        for a,b in ranges:
            frames=max(1,round((b-a)/PLAYBACK_SPEED*FPS))
            if frames:
                result.append(dict(source=s, start=a, end=b, frames=int(frames),
                                   speed=PLAYBACK_SPEED,label="Модель" if s == 0 else "Руки"))
    result.append(loop_return(result[0], bounds[0][0]))
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
    scale = np.array([w / small, h / small], dtype=np.float32)
    ab = cv2.resize(flow_ab, (w, h)) * scale
    ba = cv2.resize(flow_ba, (w, h)) * scale
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
        height, width = mixed.shape[:2]
        scale = min(1, 360 / max(width, height))
        small = cv2.resize(mixed, (max(2, round(width * scale)), max(2, round(height * scale))), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), max(.1, sigma * scale * min(width, height) / SIZE))
        mixed = cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)
    return mixed


def render(sources, infos, settings, work, output, progress, cancel):
    width, height = output_dimensions(settings)
    preview = settings.get("preview", False)
    paths = []
    readers = []
    proc = None
    temp_output = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.partial.mp4")
    try:
        for s in range(2):
            progress(4 + s * 12, f"Подготовка видео: {'модель' if s == 0 else 'руки'}")
            path = work / f"normalized-{s}.mp4"
            normalize(sources[s], infos[s], path, settings["crops"][s], cancel,
                      width=width, height=height, crop_x=settings.get("crops_x", [.5, .5])[s], preview=preview,
                      zoom=settings.get('zooms', [1, 1])[s])
            paths.append(path)
        progress(29, "Анализ движения и точек монтажа")
        analyses = [scan_content(path, cancel) for path in settings.get("_analysis_paths", sources)]
        auto_bounds = [scene_bounds(analysis,s) for s,analysis in enumerate(analyses)]
        bounds = [tuple(trim) if trim is not None else auto_bounds[s]
                  for s,trim in enumerate(settings.get('trims', [None, None]))]
        segments = smart_segments(paths,settings["sensitivity"],cancel,analyses,bounds,
                                  remove_pauses=settings["mode"]=="smart")
        readers = [FrameReader(p) for p in paths]
        timeline = []
        for seg in segments:
            for i in range(seg["frames"]):
                timeline.append((seg["source"], seg["start"] +
                                 (0 if seg.get("loop") else i*PLAYBACK_SPEED/FPS)))
        frame_count=len(timeline)
        model_frames=sum(seg["frames"] for seg in segments if seg["source"]==0 and not seg.get("loop"))
        hands_frames=sum(seg["frames"] for seg in segments if seg["source"]==1)
        transitions = {}
        # Reference transitions: 9.267–10.033 and 21.8–22.467 s.
        # Preserve the total duration; sample source handles around each boundary.
        for boundary, length, lead in [(model_frames,min(15,hands_frames),0),(model_frames+hands_frames,18,0)]:
            kind = settings["transition"] if boundary==model_frames else "lens"
            if kind != "cut":
                for j in range(length):
                    at = boundary - lead + j
                    transitions[at] = (boundary, j, length, lead, kind)
        intermediate = work / "assembled.mp4"
        errfile = work / "encoder.log"
        with errfile.open("wb") as error:
            proc = subprocess.Popen([
                binary("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo",
                "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", "30",
                "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "ultrafast" if preview else "fast",
                "-crf", "26" if preview else "16", "-threads", "4", "-pix_fmt", "yuv420p",
                "-g", "30", "-bf", "0",
                str(intermediate)], stdin=subprocess.PIPE, stderr=error, creationflags=NO_WINDOW)
            first_frame = readers[timeline[0][0]].get(timeline[0][1])
            quality = FrameQuality()
            for index, (s, t) in enumerate(timeline):
                if cancel.is_set():
                    raise Cancelled()
                frame = readers[s].get(t)
                if index in transitions:
                    boundary, j, n, lead, kind = transitions[index]
                    old_s, old_t = timeline[boundary-1]
                    new_s, new_t = timeline[boundary]
                    old_step = max(0, old_t - timeline[boundary-2][1]) if boundary >= 2 and timeline[boundary-2][0] == old_s else 0
                    new_step = max(0, timeline[boundary+1][1] - new_t)
                    old_sample = t if index < boundary else min(bounds[old_s][1]-1/FPS, old_t+(index-boundary+1)*old_step)
                    new_sample = t if index >= boundary else max(bounds[new_s][0], new_t+(index-boundary)*new_step)
                    a = readers[old_s].get(old_sample)
                    b = readers[new_s].get(new_sample)
                    frame = b if n == 1 else transition(a, b, j/(n-1), kind)
                if index == frame_count - 1:
                    frame = first_frame.copy()
                quality.add(frame,index,eligible=index not in transitions and index<frame_count-18)
                proc.stdin.write(frame.tobytes())
                if index % 10 == 0:
                    progress(32 + 43 * (index+1)/frame_count, "Монтаж и переходы")
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
                    "-preset", "medium", "-profile:v", "high",
                    "-pix_fmt", "yuv420p", "-threads", "4",
                    "-passlogfile", passlog]
        if preview:
            progress(88, "Сохраняем быстрое превью")
            encoding = ["-c:v", "copy"]
        else:
            progress(77, f"Сжатие · {bitrate} кбит/с · проход 1 из 2")
            run(common + encoding + ["-pass", "1", "-an", "-f", "null", os.devnull], cancel)
            progress(88, f"Сжатие · {bitrate} кбит/с · проход 2 из 2")
            encoding += ["-pass", "2"]
        run(common + ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"] +
            encoding + ["-map", "0:v:0", "-map", "1:a:0",
                        "-c:a", "aac", "-b:a", "64k", "-t", str(frame_count/FPS),
                        "-movflags", "+faststart", "-map_metadata", "-1",
                        "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-colorspace", "bt709", str(temp_output)], cancel)
        if cancel.is_set():
            raise Cancelled()
        result = probe(temp_output, min_duration=1/FPS, max_duration=1200)
        if (result["width"], result["height"]) != (width, height):
            raise RuntimeError("Проверка формата результата не пройдена.")
        if os.name == "nt":
            temp_output.rename(output)  # Windows refuses to replace an existing file.
        else:
            os.link(temp_output, output)
            temp_output.unlink()
        report = dict(generator="OUTMAX Cut", segments=segments, settings={k:v for k,v in settings.items() if not k.startswith("_")}, result=result,
                      loop=True, quality=quality.report(), content_bounds=bounds, auto_bounds=auto_bounds,
                      activity_ranges=[active_intervals(path,settings['sensitivity'],cancel,analyses[s]) for s,path in enumerate(paths)],
                      black_opening_frame=False,
                      frames=frame_count, fps=FPS, speed=PLAYBACK_SPEED,model_frames=model_frames,hands_frames=hands_frames,
                      transition_note="Independent Lens Blur approximation / optical flow")
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
