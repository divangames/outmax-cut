"""Run the packaged app with Cyrillic paths, no Python/FFmpeg in PATH."""
import json
import re
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from version import VERSION

def main():
    source = ROOT / "dist" / VERSION / "OUTMAX-Cut"
    target = ROOT / "analysis" / ("Проверка-" + uuid.uuid4().hex[:8]) / "Программа"
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
        with urllib.request.urlopen('http://127.0.0.1:8771/ui/automation.js') as response:assert response.status==200
        with urllib.request.urlopen('http://127.0.0.1:8771/api/automation?summary=1') as response:assert json.load(response)['active'] is False
        assert "Профиль" in data["output"], data
        for resource in ("/", "/reference", "/ui/app.js", "/ui/formats.js", "/ui/timeline.js", "/ui/editor-extras.js", "/ui/workspace.js", "/ui/context-menu.js", "/ui/whats-new.js", "/ui/whats-new.json", "/ui/live-preview.js", "/ui/preview.js", "/ui/updates.js", "/api/updates"):
            with urllib.request.urlopen("http://127.0.0.1:8771" + resource) as response:
                assert response.status == 200
        ffprobe = target / "_internal" / "bin" / "ffprobe.exe"
        result = subprocess.run([str(ffprobe), "-v", "error", "-show_streams", "-of", "json",
                                 str(target / "_internal/assets/reference.mp4")], env=env,
                                capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        assert json.loads(result.stdout)["streams"][0]["width"] == 1080
        with urllib.request.urlopen("http://127.0.0.1:8771/") as response:
            html=response.read().decode('utf-8')
        token=re.search(r'name="outmax-token" content="([^"]+)"',html).group(1)
        assert 'id="previewButton"' not in html
        assert 'id="referenceTab"' not in html
        assert len(data['preferences']['video_formats'])==3
        with urllib.request.urlopen('http://127.0.0.1:8771/ui/whats-new.json') as response:history=json.load(response)
        assert history[0]['version']==VERSION
        for release in history:
            for shot in release['screenshots']:
                with urllib.request.urlopen('http://127.0.0.1:8771'+shot['src']) as response:assert response.headers['Content-Type'].startswith('image/')
        session=dict(items=[],mode=False,active=None,single=dict(sources=[None,None],settings=dict(zooms=[1.3,1.2])),output=str(profile))
        req=urllib.request.Request('http://127.0.0.1:8771/api/session',json.dumps(session).encode(),{'Content-Type':'application/json','X-Outmax-Token':token})
        with urllib.request.urlopen(req) as response:assert response.status==200
        assert data['preferences']['mode']=='smart'
        selected={'mode':'template','bitrate_kbps':750,'sensitivity':73,
                  'video_formats':data['preferences']['video_formats']+[dict(id='custom_smoke',name='Для сайта',width=640,height=480)]}
        req=urllib.request.Request('http://127.0.0.1:8771/api/settings',json.dumps(selected).encode(),
                                   {'Content-Type':'application/json','X-Outmax-Token':token})
        with urllib.request.urlopen(req) as response:assert response.status==200
        process.terminate();process.wait(20)
        process=subprocess.Popen([str(target/'OUTMAX-Cut.exe'),'--no-open','--port','8771'],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
        for attempt in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8771/api/config',timeout=2) as response:
                    restored=json.load(response)['preferences']
                break
            except OSError:time.sleep(.5)
        else:raise RuntimeError('Packaged restart failed')
        assert all(restored[key]==value for key,value in selected.items()),restored
        with urllib.request.urlopen('http://127.0.0.1:8771/api/session') as response:assert json.load(response)['session']['single']['settings']['zooms']==[1.3,1.2]
        print("PASS: packaged app, Cyrillic paths, isolated PATH, auto-preview assets, bundled FFprobe, defaults persist after process restart.")
    finally:
        process.terminate()
        process.wait(20)

if __name__ == "__main__":
    main()
