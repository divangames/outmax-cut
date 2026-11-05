"""Real FFmpeg fixtures and exports for format/preview/crop regression checks."""
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import binary, run, normalize, probe, render
import cv2

ROOT = Path(__file__).resolve().parents[1] / "analysis/features"


def fixtures():
    for article in ("90001", "90002"):
        folder = ROOT / "inputs" / article
        folder.mkdir(parents=True, exist_ok=True)
        for role, size, ext in (("model", "640x360", "mp4"), ("hands", "360x640", "mov")):
            path = folder / f"{article}_{role}.{ext}"
            if not path.exists():
                run([binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
                     f"testsrc2=size={size}:rate=30:duration=2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)])


def exports():
    fixtures()
    paths = [ROOT / "inputs/90001/90001_model.mp4", ROOT / "inputs/90001/90001_hands.mov"]
    infos = [probe(path) for path in paths]
    cancel = threading.Event()
    results = []
    # Real encoded crop must match the position shown by object-position in the UI.
    for position in (0., 1.):
        dest=ROOT / f"crop-{position}.mp4"
        normalize(paths[0],infos[0],dest,.5,cancel,size=120,crop_x=position,preview=True)
        cap=cv2.VideoCapture(str(dest));ok,frame=cap.read();cap.release()
        assert ok
        results.append(frame)
    assert cv2.norm(results[0],results[1],cv2.NORM_L1)>10000, "Horizontal crop did not change the picture"
    results=[]
    for position in (0.,1.):
        dest=ROOT / f"crop-y-{position}.mp4"
        normalize(paths[1],infos[1],dest,position,cancel,size=120,preview=True)
        cap=cv2.VideoCapture(str(dest));ok,frame=cap.read();cap.release()
        assert ok
        results.append(frame)
    assert cv2.norm(results[0],results[1],cv2.NORM_L1)>10000, "Vertical crop did not change the picture"
    reports=[]
    for name,dims in (("standard",(1080,1080)),("marketplace",(900,1200)),("vertical",(1080,1920))):
        work=ROOT / f"work-{name}"
        work.mkdir(exist_ok=True)
        output=ROOT / f"export-{name}-{time.time_ns()}.mp4"
        started=time.monotonic()
        report=render(paths,infos,dict(mode="template",transition="lens",crops=[.82,.5],crops_x=[.2,.8],format=name,bitrate_kbps=500),work,output,lambda *_:None,cancel)
        assert (report["result"]["width"],report["result"]["height"])==dims
        cap=cv2.VideoCapture(str(output))
        assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT))==report['frames']
        cap.release()
        reports.append(dict(format=name,seconds=round(time.monotonic()-started,2),path=str(output),result=report["result"]))
        print(json.dumps(reports[-1]),flush=True)
    (ROOT / "exports.json").write_text(json.dumps(reports,indent=2),encoding="utf-8")


if __name__ == "__main__":
    fixtures() if "--fixtures" in sys.argv else exports()
