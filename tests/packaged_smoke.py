"""Run the packaged app with Cyrillic paths, no Python/FFmpeg in PATH."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from version import VERSION

def main():
    source = ROOT / "dist" / VERSION / "OUTMAX-Cut"
    target = ROOT / "analysis" / "Дизайнер" / "Программа"
    shutil.copytree(source, target, copy_function=os.link, dirs_exist_ok=False)
    profile = target.parent / "Профиль"
    profile.mkdir(exist_ok=True)
    env = dict(os.environ, LOCALAPPDATA=str(profile), USERPROFILE=str(profile),
               PATH=os.environ.get("SystemRoot", r"C:\Windows") + r"\System32")
    process = subprocess.Popen([str(target / "OUTMAX-Cut.exe"), "--no-open", "--port", "8771"],
                               env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for attempt in range(60):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8771/api/config", timeout=2) as response:
                    data = json.load(response)
                break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError("Packaged app exited before serving HTTP")
                time.sleep(.5)
        else:
            raise RuntimeError("Packaged app did not start")
        assert data["version"] == VERSION, data
        assert "Профиль" in data["output"], data
        for resource in ("/", "/reference", "/ui/app.js", "/ui/updates.js", "/api/updates"):
            with urllib.request.urlopen("http://127.0.0.1:8771" + resource) as response:
                assert response.status == 200
        ffprobe = target / "_internal" / "bin" / "ffprobe.exe"
        result = subprocess.run([str(ffprobe), "-v", "error", "-show_streams", "-of", "json",
                                 str(target / "_internal/assets/reference.mp4")], env=env,
                                capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        assert json.loads(result.stdout)["streams"][0]["width"] == 1080
        print("PASS: packaged app, Cyrillic install/profile paths, isolated PATH, assets, updater and bundled FFprobe.")
    finally:
        process.terminate()
        process.wait(20)

if __name__ == "__main__":
    main()
