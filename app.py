from __future__ import annotations

import argparse
import atexit
from datetime import datetime
import json
import logging
import math
import os
import re
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
import cv2

cv2.setNumThreads(2)  # Leave CPU capacity for WebView and input while importing/exporting.

from flask import Flask, jsonify, request, send_file, abort
from waitress import create_server

from engine import RESOURCES, Cancelled, make_proxy, probe, render, video_bitrate, output_dimensions
from notifications import TrayNotifications
from batching import VIDEO_EXTENSIONS, model_score, group_sources, safe_folder, is_generated_video
from version import VERSION
from updater import Updater
from video_formats import DEFAULT_FORMATS, validate_catalog
from workspace_store import WorkspaceStore
from automation import AutoAssembler
from batching import name_role, suggest_pair

BASE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OutmaxCut"
BASE.mkdir(parents=True, exist_ok=True)
WORK = BASE / "work" / uuid.uuid4().hex
WORK.mkdir(parents=True, exist_ok=True)
OUTPUT = Path.home() / "Desktop" / "Готовые видео"
logging.basicConfig(filename=str(BASE / "app.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
app = Flask(__name__, static_folder=str(RESOURCES / "ui"), static_url_path="/ui")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024**3
TOKEN = secrets.token_urlsafe(32)
sources = {}
jobs = {}
imports = {}
batches = {}
lock = threading.Lock()
import_slots = threading.Semaphore(2)
render_slots = threading.Semaphore(1)
window = None
notifications = TrayNotifications(RESOURCES / "assets/icon.ico")
shell_paths = []
shell_updated = 0
updater = Updater(BASE / "updates")
installing_update = False
workspace = WorkspaceStore(BASE)
shell_command = None
last_workspace_store = None
cleanup_done = False
automation = None
automation_init_lock = threading.Lock()
background_exit_requested = False
background_start = False
active_requests = 0
SETTINGS_FILE = BASE / "settings.json"


def load_preferences():
    defaults = dict(save_processing_log=False, mode="smart", bitrate_kbps=2500, sensitivity=40,
                    video_formats=DEFAULT_FORMATS)
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return defaults | preference_updates(data)
    except (OSError, ValueError, AttributeError):
        return defaults


def preference_updates(data):
    if not isinstance(data, dict):
        raise ValueError("Некорректные настройки.")
    result = {}
    for key, value in data.items():
        if key == "save_processing_log":
            if not isinstance(value, bool):
                raise ValueError("Настройка должна быть включена или выключена.")
        elif key == "mode":
            if value not in ("smart", "template"):
                raise ValueError("Неизвестный режим монтажа.")
        elif key == "bitrate_kbps":
            value = video_bitrate({key: value})
        elif key == "sensitivity":
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError("Удаление пауз должно быть от 0 до 100%.")
        elif key == 'video_formats':
            value = validate_catalog(value)
        elif key == 'last_preset_id':
            if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{0,64}',value):raise ValueError('Некорректный пресет.')
        else:
            continue
        result[key] = value
    return result


preferences = load_preferences()


@app.post("/api/settings")
def save_preferences():
    data = request.get_json(silent=True) or {}
    try:
        updates = preference_updates(data)
        if not updates:
            raise ValueError("Не переданы настройки для сохранения.")
        with lock:
            updated = preferences | updates
            temporary = SETTINGS_FILE.with_suffix(".tmp")
            temporary.write_text(json.dumps(updated), encoding="utf-8")
            temporary.replace(SETTINGS_FILE)
            preferences.update(updated)
        return jsonify(updated)
    except (OSError, ValueError) as exc:
        return jsonify(error=str(exc)), 400


@app.before_request
def local_only():
    global active_requests
    host = request.host.split(":")[0]
    if host not in ("127.0.0.1", "localhost"):
        abort(403)
    if request.method == "POST" and request.headers.get("X-Outmax-Token") != TOKEN:
        abort(403)
    if request.method == "POST":
        with lock:
            if installing_update:
                return jsonify(error="Приложение закрывается для обновления."), 409
            active_requests += 1
            from flask import g
            g.counted_request = True


@app.teardown_request
def request_finished(_):
    global active_requests
    from flask import g
    if getattr(g, "counted_request", False):
        g.counted_request = False
        with lock:
            active_requests -= 1


@app.after_request
def headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "private, max-age=3600" if request.path.startswith(("/media/", "/result/", "/poster/")) else "no-store"
    return response


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="Файл больше 2 ГБ. Выберите короткий исходный ролик."), 413


@app.get("/")
def index():
    return (RESOURCES / "ui/index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN).replace("__VERSION__", VERSION)


@app.get("/api/config")
def config():
    return jsonify(output=str(OUTPUT), preferences=preferences, version=VERSION, native=window is not None,background_start=background_start,
                   can_install_update=window is not None and getattr(sys, "frozen", False))


@app.get("/api/updates")
def update_status():
    return jsonify(updater.snapshot())


@app.post("/api/updates/check")
def check_update():
    updater.check()
    return jsonify(updater.snapshot())


@app.post("/api/updates/download")
def download_update():
    try:
        updater.download()
        return jsonify(updater.snapshot())
    except ValueError as exc:
        return jsonify(error=str(exc)), 409


@app.post("/api/updates/install")
def install_update():
    global installing_update
    if window is None or not getattr(sys, "frozen", False) or os.name != "nt":
        return jsonify(error="Установка доступна в Windows-приложении."), 409
    with lock:
        if busy() or active_requests > 1 or any(i["status"] == "running" for i in imports.values()):
            return jsonify(error="Завершите импорт и экспорт перед установкой обновления."), 409
        installing_update = True
    try:
        installer = updater.installer()
        subprocess.Popen([str(installer), "/SP-", "/NORESTART"], cwd=str(installer.parent))
        updater._set(status="installing")
        threading.Timer(1, window.destroy).start()
        return jsonify(ok=True)
    except (OSError, ValueError) as exc:
        with lock:
            installing_update = False
        return jsonify(error=str(exc)), 400


def public_source(entry):
    return {k: entry[k] for k in ("id", "name", "info", "relative", "model_score")} | {
        "preview": f"/media/{entry['id']}", "poster": f"/poster/{entry['id']}",
        "location":str(entry.get('path','')),"missing":bool(entry.get('path') and (not entry['path'].is_file() or not entry.get('preview_path',entry['path']).is_file()))}


def register_source(path, folder, name, relative=None, cancel=None, progress=None):
    if progress:
        progress(.01, "Проверяем видео")
    info = probe(path)
    if path.stat().st_size > 2 * 1024**3:
        raise ValueError("Файл больше 2 ГБ.")
    if cancel and cancel.is_set():
        raise Cancelled()
    direct = info["codec"] == "h264" and not info["hdr"] and path.suffix.lower() == ".mp4" and max(info["width"], info["height"]) <= 1280
    preview = path if direct else folder / "preview.mp4"
    if not direct:
        make_proxy(path, info, preview, cancel,
                   (lambda value: progress(.03 + value * .9, "Готовим превью")) if progress else None)
    if progress:
        progress(.95, "Готовим миниатюру")
    cap = cv2.VideoCapture(str(preview))
    cap.set(cv2.CAP_PROP_POS_MSEC, min(3, info["duration"]/2)*1000)
    ok, frame = cap.read()
    cap.release()
    if ok:
        encoded = cv2.imencode(".jpg", frame)[1]
        encoded.tofile(str(folder / "poster.jpg"))
    key = folder.name
    entry = dict(id=key, name=name, relative=relative or name, info=info, path=path,
                 preview_path=preview, poster_path=folder/'poster.jpg', model_score=model_score(preview))
    with lock:
        sources[key] = entry
    if progress:
        progress(1, "Готово")
    return entry


@app.post("/api/upload")
def upload():
    incoming = request.files.get("file")
    if not incoming or not incoming.filename:
        return jsonify(error="Выберите видеофайл."), 400
    ext = Path(incoming.filename).suffix.lower()
    if ext not in VIDEO_EXTENSIONS:
        return jsonify(error="Поддерживаются MP4, MOV, M4V, MKV, AVI и WebM."), 400
    key = uuid.uuid4().hex
    folder = WORK / key
    folder.mkdir()
    path = folder / ("source" + ext)
    try:
        incoming.save(path)
        return start_import([(path, request.form.get("relative") or Path(incoming.filename).name)],
                            display_names={path: Path(incoming.filename).name})
    except Exception as exc:
        logging.exception("Upload failed")
        shutil.rmtree(folder, ignore_errors=True)
        return jsonify(error=str(exc)), 400


@app.post("/api/choose-source")
def choose_source():
    if window is None:
        return jsonify(error="Выбор доступен в Windows-приложении."), 400
    import webview
    selected = window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
        file_types=("Видео (*.mp4;*.mov;*.m4v;*.mkv;*.avi;*.webm)",))
    if not selected:
        return jsonify(source=None)
    folder = WORK / uuid.uuid4().hex
    folder.mkdir()
    try:
        path = Path(selected[0])
        return start_import([(path, path.name)])
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        return jsonify(error=str(exc)), 400


@app.get("/media/<key>")
def media(key):
    with lock:
        entry = sources.get(key)
    if not entry:
        abort(404)
    return send_file(entry["preview_path"], conditional=True)


@app.get("/reference")
def reference():
    return send_file(RESOURCES / "assets/reference.mp4", conditional=True)


@app.get("/app-icon.<kind>")
def app_icon(kind):
    if kind not in ("png", "ico"):
        abort(404)
    return send_file(RESOURCES / f"assets/icon.{kind}")


@app.get("/poster/<key>")
def poster(key):
    entry = sources.get(key)
    if not entry:
        abort(404)
    return send_file(sources[key].get('poster_path',WORK / key / 'poster.jpg'), conditional=True)


def validate_settings(data):
    mode = data.get("mode", preferences["mode"])
    transition = data.get("transition", "lens")
    crops = data.get("crops", [.824, .5])
    crops_x = data.get("crops_x", [.5, .5])
    sensitivity = float(data.get("sensitivity", preferences["sensitivity"]))
    if mode not in ("template", "smart") or transition not in ("lens", "morph", "cut"):
        raise ValueError("Неизвестный режим монтажа.")
    if any(not isinstance(values, list) or len(values) != 2 or any(
            isinstance(c, bool) or not isinstance(c, (float, int)) or
            not math.isfinite(c) or not 0 <= c <= 1 for c in values) for values in (crops, crops_x)):
        raise ValueError("Положение кадра должно быть от 0 до 100%.")
    if not math.isfinite(sensitivity) or not 0 <= sensitivity <= 100:
        raise ValueError("Чувствительность должна быть от 0 до 100.")
    catalog = validate_catalog(data.get('format_catalog', preferences.get('video_formats', DEFAULT_FORMATS)))
    output_dimensions(data | {'format_catalog': catalog})
    formats = data.get("formats", [data.get("format", "standard")])
    if not isinstance(formats, list) or not 1 <= len(formats) <= len(catalog) or any(
            not isinstance(name, str) or name not in {item['id'] for item in catalog} for name in formats) or len(set(formats)) != len(formats):
        raise ValueError("Выберите хотя бы одно разрешение без повторов.")
    zooms = data.get('zooms', [1, 1])
    if not isinstance(zooms, list) or len(zooms) != 2 or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not 1 <= n <= 3 for n in zooms):
        raise ValueError('Масштаб должен быть от 100 до 300%.')
    trims = data.get('trims', [None, None])
    if not isinstance(trims, list) or len(trims) != 2 or any(trim is not None and (
            not isinstance(trim, list) or len(trim) != 2 or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in trim) or
            not 0 <= trim[0] < trim[1] <= 600 or trim[1]-trim[0] < 1/24) for trim in trims):
        raise ValueError('Укажите начало и конец каждого исходника; оставьте хотя бы один кадр.')
    return dict(mode=mode, transition=transition, crops=crops, crops_x=crops_x, sensitivity=sensitivity,
                zooms=zooms, trims=trims, format_catalog=catalog,
                format=data.get("format", formats[0]), formats=formats,
                bitrate_kbps=video_bitrate(data if "bitrate_kbps" in data else {"bitrate_kbps":preferences["bitrate_kbps"]}))


def busy():
    return (automation is not None and automation.active) or any(j["status"] in ("running", "queued") and not j.get("preview") for j in jobs.values())


def cancel_previews():
    for job in jobs.values():
        if job.get("preview") and job["status"] in ("running", "queued"):
            job["cancel"].set()


def article_number(data):
    explicit = str(data.get("article") or "").strip()
    if explicit:
        if not re.fullmatch(r"[0-9]+", explicit):
            raise ValueError("Артикул должен содержать только цифры.")
        return explicit
    folder = str(data.get("folder") or "").replace("\\", "/")
    parts = [part for part in folder.split("/") if part and part != "Руки + Ноги"]
    if parts:
        numbers = re.findall(r"(?<![0-9])[0-9]+(?![0-9])", parts[-1])
        if len(numbers) == 1:
            return numbers[0]
    candidates = [set(re.findall(r"[0-9]+", Path(sources[key]["name"]).stem))
                  for key in data["sources"]]
    common = candidates[0] & candidates[1]
    if len(common) == 1:
        return common.pop()
    parents = {sources[key]["path"].parent.name for key in data["sources"]}
    if len(parents) == 1 and re.fullmatch(r"[0-9]+", next(iter(parents))):
        return parents.pop()
    raise ValueError("Не удалось определить артикул. Укажите номер артикула или назовите папку его номером.")


def output_path(data, key):
    article = article_number(data)
    base = Path(str(data.get("output") or OUTPUT)).expanduser()
    if not base.is_absolute():
        raise ValueError("Укажите абсолютный путь к папке экспорта.")
    base = base.resolve()
    dest = base if base.name == article else base / article
    if not dest.resolve().is_relative_to(base):
        raise ValueError("Недопустимая папка экспорта.")
    suffix = ""
    if data.get("_variant"):
        width, height = output_dimensions(data | {"format":data["_variant"]})
        suffix = f"_{width}x{height}"
        if data['_variant'] not in ('standard', 'marketplace', 'vertical'):
            suffix += '_' + data['_variant']
    filename = dest / f"{article}{suffix}.mp4"
    used = {str(variant["output"]).casefold() for j in jobs.values()
            if j["status"] in ("running", "queued") for variant in j.get("variants", [{"output":j["output"]}])}
    if filename.exists() or str(filename).casefold() in used:
        if data.get('_repeat'):
            index=2
            while filename.exists() or str(filename).casefold() in used:
                filename=dest/f'{article}{suffix}_v{index}.mp4';index+=1
        else:raise ValueError(f"Файл уже существует или поставлен в очередь: {filename}. Переместите его перед повторным экспортом.")
    return filename


def archive_targets(job):
    folder = job["output"].parent / "Руки + Ноги"
    if folder.is_symlink() or not folder.resolve().is_relative_to(job["output"].parent.resolve()):
        raise ValueError("Недопустимая папка исходников.")
    return [(sources[key], folder / f"{job.get('article', job['output'].stem)}_{role}{sources[key]['path'].suffix.lower()}")
            for key, role in zip(job["source_ids"], ("ноги", "руки"))]


def check_archive(job):
    targets = archive_targets(job)
    for source, target in targets:
        if not source["path"].is_file():
            raise ValueError(f"Исходник не найден: {source['path']}")
        if target.exists() and source["path"].resolve() != target.resolve():
            raise ValueError(f"Исходник уже существует: {target}")
    if job["save_processing_log"] and (job["output"].parent / job.get('log_name','монтаж.txt')).exists():
        raise ValueError("Лог монтаж.txt уже существует. Переместите его перед экспортом.")
    return targets


def archive_sources(job):
    targets = check_archive(job)
    created = []
    folder = targets[0][1].parent
    folder.mkdir(exist_ok=True)
    try:
        # Copy every source exclusively before deleting any original. Works across disks.
        for source, target in targets:
            if source["path"].resolve() == target.resolve():
                continue
            with target.open("xb") as out:
                created.append(target)
                with source["path"].open("rb") as incoming:
                    shutil.copyfileobj(incoming, out)
            shutil.copystat(source["path"], target)
    except Exception:
        for target in created:
            target.unlink(missing_ok=True)
        if not any(folder.iterdir()):
            folder.rmdir()
        raise
    # All copies are complete; on a deletion failure retain the archive and remaining originals.
    for source, target in targets:
        original = source["path"]
        if original.resolve() != target.resolve():
            if not original.resolve().is_relative_to(workspace.media.resolve()):original.unlink()
            for entry in sources.values():
                if entry["path"] == original:
                    entry["path"] = target
                    workspace.record_location(entry)
                if entry.get("preview_path") == original:
                    entry["preview_path"] = target


def create_job(data, status="running", preview=False):
    settings = validate_settings(data)
    settings["preview"] = preview
    ids = data.get("sources", [])
    if len(ids) != 2 or any(s not in sources for s in ids):
        raise ValueError("Добавьте видео «Модель» и «Руки».")
    if ids[0] == ids[1] or sources[ids[0]]["path"].resolve() == sources[ids[1]]["path"].resolve():
        raise ValueError("Модель и руки должны быть разными файлами.")
    for s,trim in enumerate(settings['trims']):
        if trim is not None and trim[1] > sources[ids[s]]['info']['duration'] + .001:
            raise ValueError('Монтажная граница выходит за длительность исходника.')
    key = uuid.uuid4().hex
    variants = ([dict(format=settings["format"], output=WORK / key / "preview.mp4")] if preview else
                [dict(format=name, output=output_path(data | settings | ({"_variant":name} if len(settings["formats"]) > 1 else {}), key)) for name in settings["formats"]])
    job = dict(id=key, status=status, progress=0, stage="В очереди" if status == "queued" else "Начинаем",
               cancel=threading.Event(), output=variants[0]["output"], variants=variants,
               article=None if preview else article_number(data),
               preview=preview,
               log_name=(f'{variants[0]["output"].stem}-монтаж.txt' if data.get('_repeat') else 'монтаж.txt'),
               settings=settings, source_ids=list(ids), item_id=data.get("item_id"),
               save_processing_log=preferences["save_processing_log"])
    jobs[key] = job
    return job


def execute_job(job):
    with render_slots:
        _execute_job(job)


def _execute_job(job):
    folder = WORK / job["id"]
    folder.mkdir(exist_ok=True)
    selected = [sources[s] for s in job["source_ids"]]
    def progress(value, stage):
        with lock:
            job.update(progress=round(value), stage=stage)
    destination_existed = job["output"].parent.exists()
    created_outputs = []
    rendered_all = False
    try:
        job['started_at']=time.monotonic()
        if job["cancel"].is_set():
            raise Cancelled()
        with lock:
            job.update(status="running")
        if not job["preview"]:
            check_archive(job)
        job["output"].parent.mkdir(parents=True, exist_ok=True)
        inputs = [s["preview_path"] if job["preview"] else s["path"] for s in selected]
        infos = [dict(s["info"], hdr=False) if job["preview"] else s["info"] for s in selected]
        variants = job["variants"]
        for index, variant in enumerate(variants):
            if job["cancel"].is_set():
                raise Cancelled()
            settings = job["settings"] | {"format":variant["format"]}
            def variant_progress(value, stage):
                progress(min(99, (index + value / 100) / len(variants) * 100),
                         f"{index+1}/{len(variants)} · {stage}" if len(variants) > 1 else stage)
            render_settings = settings | {"_analysis_paths":[str(s.get("preview_path",s["path"])) for s in selected]}
            report = render(inputs, infos, render_settings, folder, variant["output"], variant_progress, job["cancel"])
            created_outputs.append(variant["output"])
            variant.update(report=report, status="done")
        if job["cancel"].is_set():
            raise Cancelled()
        rendered_all = True
        if not job["preview"]:
            archive_sources(job)
        if job["save_processing_log"] and not job["preview"]:
            with (job["output"].parent / job.get('log_name','монтаж.txt')).open("x", encoding="utf-8") as log:
                json.dump(report, log, ensure_ascii=False, indent=2)
        with lock:
            job.update(status="done", report=variants[0]["report"], progress=100, stage="Видео готово")
    except Cancelled:
        with lock:
            job.update(status="cancelled", stage="Экспорт отменён")
    except Exception as exc:
        logging.exception("Render failed")
        with lock:
            job.update(status="error", error=str(exc), stage=("Видео сохранено; ошибка организации файлов"
                       if job["output"].exists() else "Не удалось собрать видео"))
    finally:
        if not rendered_all:
            for output in created_outputs:
                output.unlink(missing_ok=True)
            for variant in job["variants"]:
                variant.pop("report", None)
                variant.pop("status", None)
        if not destination_existed and job["output"].parent.is_dir():
            try:
                job["output"].parent.rmdir()  # Only remove a newly created, empty destination.
            except OSError:
                pass
        if not job["preview"] and not job.get("batch_id") and not job.get('automation_id') and job["status"] in ("done", "error"):
            title = "Превью готово" if job["preview"] else "Видео готово"
            notifications.notify(window, title if job["status"] == "done" else "Ошибка сборки",
                                 job.get("error") or ("Можно посмотреть результат в приложении." if job["preview"] else str(job["output"])),
                                 job["status"] == "error")


def job_view(job):
    result = {k: v for k, v in job.items() if k not in ("cancel", "output", "thread", "variants")}
    result["output"] = str(job["output"])
    result["variants"] = [v | {"output":str(v["output"])} for v in job["variants"]]
    elapsed=time.monotonic()-job.get('started_at',time.monotonic())
    progress=job.get('progress',0)
    result['eta_seconds']=round(elapsed/progress*(100-progress)) if job['status']=='running' and progress>3 and elapsed>2 else None
    return result


@app.post("/api/render")
@app.post("/api/preview")
def start_render():
    data = request.get_json(silent=True) or {}
    try:
        with lock:
            if busy():
                return jsonify(error="Дождитесь текущего экспорта или отмените его."), 409
            preview = request.path == "/api/preview"
            if preview:
                settings = validate_settings(data)
                cache_settings = {k:v for k,v in settings.items() if k not in ("bitrate_kbps", "formats")}
                signature = json.dumps([data.get("sources"), cache_settings], sort_keys=True)
                cached = next((j for j in jobs.values() if j.get("signature") == signature and j["status"] == "done" and j["output"].exists()), None)
                if cached:
                    return jsonify(id=cached["id"], cached=True)
            cancel_previews()
            job = create_job(data, preview=preview)
            if preview:
                job["signature"] = signature
        job["thread"] = threading.Thread(target=execute_job, args=(job,), daemon=True)
        job["thread"].start()
        return jsonify(id=job["id"])
    except (ValueError, TypeError, OSError) as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/jobs/<key>")
def get_job(key):
    with lock:
        job = jobs.get(key)
        if not job:
            abort(404)
        result = job_view(job)
    return jsonify(result)


@app.post("/api/jobs/<key>/cancel")
def cancel_job(key):
    with lock:
        job = jobs.get(key)
        if not job:
            abort(404)
        job["cancel"].set()
    return jsonify(ok=True)


@app.get("/result/<key>")
def result(key):
    with lock:
        job = jobs.get(key)
        if not job or job["status"] != "done":
            abort(404)
    name = request.args.get("format")
    variant = next((v for v in job["variants"] if v["format"] == name), None) if name else job["variants"][0]
    if variant is None:
        abort(404)
    return send_file(variant["output"], conditional=True,
                     as_attachment=request.args.get("download") == "1")


@app.post("/api/folder")
def open_folder():
    data = request.get_json(silent=True) or {}
    path = Path(str(data.get("path") or OUTPUT))
    if not path.is_absolute() or not path.is_dir():
        return jsonify(error="Папка не найдена."), 400
    os.startfile(str(path))
    return jsonify(ok=True)


@app.post("/api/choose-folder")
def choose_folder():
    if window is None:
        return jsonify(browser=True)
    import webview
    selected = window.create_file_dialog(webview.FileDialog.FOLDER, allow_multiple=False)
    return jsonify(path=selected[0] if selected else None)


@app.post("/api/batch/group")
def batch_group():
    data = request.get_json(silent=True) or {}
    ids = data.get("sources", [])
    if not isinstance(ids, list) or len(ids) > 1000 or any(s not in sources for s in ids):
        return jsonify(error="Некорректный список исходников."), 400
    return jsonify(groups=group_sources([public_source(sources[s]) for s in ids]))


@app.post("/api/batch/import")
def import_directory():
    data = request.get_json(silent=True) or {}
    root = Path(str(data.get("path", ""))).expanduser()
    if not root.is_absolute() or not root.is_dir():
        return jsonify(error="Выберите существующую папку с видео."), 400
    root = root.resolve()
    # Refuse symbolic-link escapes and skip our own exports by their sidecar manifest.
    files, skipped = [], 0
    for path in root.rglob("*"):
        if path.suffix.lower() not in VIDEO_EXTENSIONS or not path.is_file():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        if is_generated_video(path):
            skipped += 1
            continue
        files.append(path)
        if len(files) > 1000:
            return jsonify(error="За один импорт можно добавить до 1000 видео."), 400
    if not files:
        return jsonify(error="В папке нет исходных видео. Готовые экспорты OUTMAX пропускаются."), 400
    return start_import([(path, str(Path(root.name) / path.relative_to(root)).replace("\\", "/"))
                         for path in files], skipped)


def start_import(files, skipped=0, display_names=None):
    from concurrent.futures import ThreadPoolExecutor
    key = uuid.uuid4().hex
    task = dict(id=key, status="running", processed=0, total=len(files), errors=[], skipped=skipped,
                groups=[], progress=0, stage="Ожидаем импорт", current="", eta_seconds=None,
                cancel=threading.Event())
    imports[key] = task
    started = time.monotonic()
    fractions = [0.] * len(files)
    def update(index, fraction, stage, relative):
        with lock:
            fractions[index] = fraction
            value = sum(fractions) / len(files)
            elapsed = time.monotonic() - started
            task.update(progress=round(value * 100, 1), stage=stage, current=relative,
                        eta_seconds=round(elapsed / value * (1 - value)) if value > .03 and elapsed > 2 else None)
    def prepare(index, path, relative):
        folder = WORK / uuid.uuid4().hex
        folder.mkdir()
        try:
            with import_slots:
                if task["cancel"].is_set():
                    return None
                entry = register_source(path, folder, (display_names or {}).get(path, path.name), relative,
                                        task["cancel"], lambda value, stage: update(index, value, stage, relative))
            return public_source(entry)
        except Cancelled:
            return None
        except Exception as exc:
            with lock:
                task["errors"].append(dict(file=relative, error=str(exc)))
            return None
        finally:
            with lock:
                task["processed"] += 1
            if not task["cancel"].is_set():
                update(index, 1, "Готово", relative)
            if not (WORK / folder.name / "poster.jpg").exists():
                shutil.rmtree(folder, ignore_errors=True)
    def worker():
        with ThreadPoolExecutor(max_workers=2) as pool:
            entries = [entry for entry in pool.map(lambda args: prepare(*args),
                       ((index, path, relative) for index, (path, relative) in enumerate(sorted(files)))) if entry]
        task["groups"] = group_sources(entries)
        task["status"] = "cancelled" if task["cancel"].is_set() else "done"
        if task["status"] == "done":
            notifications.notify(window, "Импорт завершён", f"Подготовлено {len(entries)} из {len(files)} видео. Ошибок: {len(task['errors'])}.")
    task["thread"] = threading.Thread(target=worker, daemon=True)
    task["thread"].start()
    return jsonify(id=key)


@app.post("/api/shell/enqueue")
def enqueue_shell():
    global shell_updated, shell_command
    data=request.get_json(silent=True) or {};paths=data.get('paths',[]);action=data.get('action','add')
    if action not in ('add','new','review','quick','new-only','check','model','hands','resume','results','settings','preset','focus','auto'):
        return jsonify(error='Неизвестная команда Проводника.'),400
    if not isinstance(paths, list) or not 0 <= len(paths) <= 1000 or any(
            not isinstance(p, str) or not Path(p).is_absolute() for p in paths):
        return jsonify(error="Некорректные пути."), 400
    if action=='auto':
        try:
            key=get_automation().enqueue(paths);ensure_background_tray();return jsonify(ok=True,automation_id=key)
        except (ValueError,OSError) as exc:return jsonify(error=str(exc)),400
    with lock:
        shell_paths.extend(p for p in paths if p not in shell_paths)
        shell_command=dict(action=action,preset=data.get('preset'))
        shell_updated = time.monotonic()
    if window:
        try:
            window.restore()
            window.show()
        except Exception:
            logging.exception("Could not focus window")
    return jsonify(ok=True)


@app.post("/api/shell/import")
def import_shell():
    global shell_command
    with lock:
        if (not shell_paths and not shell_command) or time.monotonic() - shell_updated < 1.5:
            return jsonify(pending=False)
        if busy() or any(i["status"] == "running" for i in imports.values()):
            return jsonify(pending=False)
        paths = list(shell_paths)
        shell_paths.clear()
        command=shell_command or dict(action='add');shell_command=None
    if command['action'] in ('settings','results','resume','focus'):
        return jsonify(command=command|{'paths':paths})
    files, seen, skipped = [], set(), 0
    for raw in paths:
        selected = Path(raw)
        if not selected.exists():
            continue
        root = selected.resolve() if selected.is_dir() else selected.resolve().parent
        for path in (root.rglob("*") if selected.is_dir() else [selected.resolve()]):
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root) or path.resolve() in seen:
                continue
            seen.add(path.resolve())
            if is_generated_video(path):
                skipped += 1
                continue
            files.append((path, str(Path(root.name) / path.relative_to(root)).replace("\\", "/")))
            if len(files) > 1000:
                return jsonify(error="За один импорт можно добавить до 1000 видео."), 400
    if not files:
        return jsonify(error="В выбранных файлах и папках нет исходных видео."), 400
    response=start_import(files, skipped)
    imported=(response.get_json() if hasattr(response,'get_json') else response)['id']
    if imported in imports:imports[imported]['command']=command
    return response


@app.get("/api/imports/<key>")
def get_import(key):
    task = imports.get(key)
    if not task:
        abort(404)
    return jsonify({k:v for k,v in task.items() if k not in ("cancel", "thread")})


@app.post("/api/imports/<key>/cancel")
def cancel_import(key):
    task = imports.get(key)
    if not task:
        abort(404)
    task["cancel"].set()
    return jsonify(ok=True)


@app.post("/api/batch/render")
def render_batch():
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    if not isinstance(items, list) or not 1 <= len(items) <= 500:
        return jsonify(error="Выберите от 1 до 500 роликов."), 400
    try:
        with lock:
            if busy():
                return jsonify(error="Уже выполняется экспорт."), 409
            # Validate every row before creating any jobs.
            used_sources = set()
            for item in items:
                validate_settings(item)
                ids = item.get("sources", [])
                if len(ids) != 2 or ids[0] == ids[1] or any(s not in sources for s in ids):
                    raise ValueError("У каждого выбранного ролика должны быть два разных исходника.")
                paths = {sources[key]["path"].resolve() for key in ids}
                if len(paths) != 2 or used_sources & paths:
                    raise ValueError("Каждый исходный файл можно использовать только в одном артикуле очереди.")
                used_sources.update(paths)
            cancel_previews()
            selected = []
            try:
                for item in items:
                    selected.append(create_job(item | {"output": data.get("output"),
                                                       "folder": item.get("name") or "Ролик"}, "queued"))
            except Exception:
                for job in selected:
                    jobs.pop(job["id"], None)
                raise
            key = uuid.uuid4().hex
            batch = dict(id=key, jobs=[j["id"] for j in selected], status="running",
                         cancel=threading.Event())
            batches[key] = batch
            for job in selected:
                job["batch_id"] = key
        def worker():
            for job in selected:
                if batch["cancel"].is_set():
                    job["cancel"].set()
                execute_job(job)
            with lock:
                batch["status"] = ("cancelled" if batch["cancel"].is_set() else
                                   "done_with_errors" if any(j["status"] == "error" for j in selected) else "done")
            if batch["status"] != "cancelled":
                count = sum(j["status"] == "done" for j in selected)
                notifications.notify(window, "Пакетная сборка завершена", f"Сохранено {count} из {len(selected)} роликов.", count != len(selected))
        batch["thread"] = threading.Thread(target=worker, daemon=True)
        batch["thread"].start()
        return jsonify(id=key)
    except (ValueError, TypeError, OSError) as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/batches/<key>")
def get_batch(key):
    with lock:
        batch = batches.get(key)
        if not batch:
            abort(404)
        return jsonify(id=key, status=batch["status"], jobs=[job_view(jobs[j]) for j in batch["jobs"]])


@app.post("/api/batches/<key>/cancel")
def cancel_batch(key):
    with lock:
        batch = batches.get(key)
        if not batch:
            abort(404)
        batch["cancel"].set()
        for key in batch["jobs"]:
            jobs[key]["cancel"].set()
    return jsonify(ok=True)


@app.post("/api/save/<key>")
def save_as(key):
    with lock:
        job = jobs.get(key)
        if not job or job["status"] != "done":
            abort(404)
    name = (request.get_json(silent=True) or {}).get("format")
    variant = next((v for v in job["variants"] if v["format"] == name), None) if name else job["variants"][0]
    if variant is None:
        return jsonify(error="Такой формат результата не найден."), 400
    output = variant["output"]
    if window is None:
        return jsonify(download=f"/result/{key}?download=1&format={variant['format']}")
    import webview
    dest = window.create_file_dialog(webview.FileDialog.SAVE, directory=str(OUTPUT),
                                    save_filename=output.name,
                                    file_types=("Видео MP4 (*.mp4)",))
    if dest:
        if isinstance(dest, (tuple, list)):
            dest = dest[0]
        dest = Path(dest).with_suffix(".mp4")
        if dest.resolve() != output.resolve():
            shutil.copy2(output, dest)
        return jsonify(saved=str(dest))
    return jsonify(cancelled=True)


def saved_presets():
    try:
        value=json.loads((BASE/'presets.json').read_text(encoding='utf-8'))
        return value if isinstance(value,list) else []
    except (OSError,ValueError):return []


@app.get('/api/presets')
def get_presets():return jsonify(presets=saved_presets(),last_id=preferences.get('last_preset_id',''))


def remember_preset(key):
    with lock:
        updated=preferences|{'last_preset_id':key};temporary=SETTINGS_FILE.with_suffix('.tmp');temporary.parent.mkdir(parents=True,exist_ok=True)
        temporary.write_text(json.dumps(updated),encoding='utf-8');temporary.replace(SETTINGS_FILE);preferences.update(updated)


@app.post('/api/automation/preset')
def select_automation_preset():
    key=(request.get_json(silent=True) or {}).get('id')
    if not any(preset['id']==key for preset in saved_presets()):return jsonify(error='Пресет не найден.'),404
    try:remember_preset(key);return jsonify(selected=key)
    except OSError as exc:return jsonify(error=str(exc)),400


def automation_settings():
    presets=saved_presets();preset=next((preset for preset in presets if preset['id']==preferences.get('last_preset_id')),presets[-1] if presets else None)
    saved=workspace.read();payload=saved['payload'] if saved else {}
    selected=dict(preset['settings'] if preset else payload.get('lastSettings') or {})
    catalog=[dict(item) for item in preferences.get('video_formats',DEFAULT_FORMATS)]
    for item in selected.get('format_catalog',[]):
        if not any(existing['id']==item['id'] for existing in catalog):
            item=dict(item)
            if any(existing['name'].casefold()==item['name'].casefold() for existing in catalog):item['name']=item['name'][:35]+' (пресет)'
            catalog.append(item)
    selected.update(format_catalog=catalog,trims=[None,None])
    return validate_settings(selected),preset['name'] if preset else 'Последние настройки экспорта' if payload.get('lastSettings') else 'Стандартные настройки',Path(payload.get('output') or OUTPUT)


def show_automation_report():
    if window:
        window.restore();window.show();window.evaluate_js('window.automationUI && window.automationUI.open(); null')


def show_background_editor():
    if window:window.evaluate_js('window.batchWorkspace && window.batchWorkspace.activateEditor(); null')


def open_automation_folder(output=None):
    if output is None:
        latest=get_automation().snapshot()['runs']
        output=latest[0]['output'] if latest else OUTPUT
    path=Path(output)
    if path.is_dir():os.startfile(str(path))
    else:show_automation_report()


def ensure_background_tray(status='OUTMAX Cut · автосборка'):
    notifications.editor_callback=show_background_editor
    notifications.background(window,show_automation_report,open_automation_folder,lambda:get_automation().cancel(),status,exit_callback=exit_background)


def exit_background():
    global background_exit_requested
    background_exit_requested=True
    if window:window.destroy()


def automation_finished(run):
    ensure_background_tray('OUTMAX Cut · '+run['stage'])
    review=run['status'] in ('error','done_with_review')
    title='Автосборка завершена' if run['status'] not in ('error','cancelled') else 'Автосборка остановлена' if run['status']=='cancelled' else 'Ошибка автосборки'
    completed=run['status'] in ('done','done_with_review')
    output=run['output']
    notifications.notify(window,title,run['stage'],review,force=True,
                         on_click=(lambda:open_automation_folder(output)) if completed else show_automation_report,
                         activate_on_click=not completed)


def process_automatic_pair(item,settings,output,cancel,update):
    from concurrent.futures import ThreadPoolExecutor
    try:
        for name in settings['formats']:
            output_path(settings|{'article':item['article'],'output':str(output)}|({'_variant':name} if len(settings['formats'])>1 else {}),'auto-check')
    except ValueError as exc:return dict(status='skipped' if 'уже существует' in str(exc) else 'review',message=str(exc))
    def prepare(raw):
        path=Path(raw);folder=WORK/uuid.uuid4().hex;folder.mkdir()
        with import_slots:
            if cancel.is_set():raise Cancelled()
            return register_source(path,folder,path.name,str(Path(item['name'])/path.name),cancel)
    with ThreadPoolExecutor(max_workers=2) as pool:entries=list(pool.map(prepare,item['paths']))
    roles=[name_role(entry['name']) for entry in entries]
    if roles[0]==roles[1] and roles[0] is not None:return dict(status='review',message='Оба видео названы одной ролью. Проверьте пару.')
    if not any(roles) and abs(entries[0]['model_score']-entries[1]['model_score'])<.18:return dict(status='review',message='Роли определены неуверенно. Проверьте модель и руки.')
    ids,note=suggest_pair(entries)
    if None in ids:return dict(status='review',message=note)
    if cancel.is_set():raise Cancelled()
    try:
        with lock:
            job=create_job(settings|{'sources':ids,'article':item['article'],'output':str(output)},status='queued')
            job['automation_id']=item.get('run_id','auto');job['cancel']=cancel
    except ValueError as exc:
        return dict(status='skipped' if 'уже существует' in str(exc) else 'review',message=str(exc))
    update(job_id=job['id'],message='Ожидаем очередь экспорта')
    execute_job(job)
    if job['status']=='done':
        return dict(status='done',message='Видео готово',outputs=[str(variant['output']) for variant in job['variants']],paths=[str(sources[key]['path']) for key in ids],findings=sum(len(v['report'].get('quality',{}).get('findings',[])) for v in job['variants']))
    return dict(status='cancelled' if cancel.is_set() else 'review',message=job.get('error') or job['stage'])


def get_automation():
    global automation
    def view(key):
        with lock:return job_view(jobs[key]) if key in jobs else None
    with automation_init_lock:
        if automation is None:automation=AutoAssembler(BASE,automation_settings,process_automatic_pair,automation_finished,view)
    return automation


@app.get('/api/automation')
def automation_status():return jsonify(get_automation().snapshot(summary=request.args.get('summary')=='1')|{'tray_resident':notifications.resident,'notification':notifications.last_notification})


@app.post('/api/automation')
def start_automation():
    try:
        key=get_automation().enqueue((request.get_json(silent=True) or {}).get('paths',[]));ensure_background_tray();return jsonify(id=key)
    except (ValueError,OSError) as exc:return jsonify(error=str(exc)),400


@app.post('/api/automation/cancel')
def cancel_automation():get_automation().cancel();return jsonify(cancelled=True)


@app.post('/api/automation/hide')
def hide_automation():
    if window:window.hide()
    return jsonify(hidden=window is not None)


@app.post('/api/presets')
def update_presets():
    data=request.get_json(silent=True) or {}
    try:
        with workspace.guard:
            presets=saved_presets();key=data.get('id') or uuid.uuid4().hex
            if data.get('action')=='delete':presets=[p for p in presets if p['id']!=key]
            else:
                name=str(data.get('name','')).strip()
                if not 1<=len(name)<=48 or any(ord(c)<32 for c in name):raise ValueError('Название пресета: от 1 до 48 символов.')
                if any(p['name'].casefold()==name.casefold() and p['id']!=key for p in presets):raise ValueError('Такое название пресета уже есть.')
                if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',key):raise ValueError('Некорректный пресет.')
                settings=validate_settings(data.get('settings',{}));settings['trims']=[None,None]
                presets=[p for p in presets if p['id']!=key]+[dict(id=key,name=name,settings=settings)]
                if len(presets)>50:raise ValueError('Можно сохранить до 50 пресетов.')
            temp=BASE/'presets.tmp';temp.write_text(json.dumps(presets,ensure_ascii=False),encoding='utf-8');temp.replace(BASE/'presets.json')
        if data.get('action')!='delete':remember_preset(key)
        elif preferences.get('last_preset_id')==key:remember_preset(presets[-1]['id'] if presets else '')
        if getattr(sys,'frozen',False) and (Path(sys.executable).parent/'unins000.exe').exists():
            from explorer_menu import register_menu
            register_menu(Path(sys.executable),presets)
        return jsonify(presets=presets)
    except (ValueError,OSError) as exc:return jsonify(error=str(exc)),400


@app.post('/api/session')
def save_session():
    global last_workspace_store
    if cleanup_done:return jsonify(error='Приложение закрывается.'),409
    try:
        workspace.save(request.get_json(silent=True) or {},sources,jobs,WORK)
        last_workspace_store=workspace
        return jsonify(saved=True)
    except (ValueError,TypeError,OSError,KeyError) as exc:return jsonify(error=str(exc)),400


@app.get('/api/session')
def restore_session():
    archive=request.args.get('archive')
    if archive:
        if not re.fullmatch(r'[a-f0-9]{32}',archive):return jsonify(error='Некорректный пакет.'),400
        try:data=json.loads((BASE/'queues'/f'{archive}.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):return jsonify(error='Сохранённый пакет не найден.'),404
    else:data=workspace.read()
    if not data:return jsonify(session=None)
    missing=[]
    for key,entry in data.get('sources',{}).items():
        try:
            entry=dict(entry)
            for field in ('path','preview_path','poster_path'):
                if field in entry:entry[field]=Path(entry[field])
            entry['path']=workspace.locate(key,entry['path'])
            if not entry['path'].is_file() or not entry['preview_path'].is_file():missing.append(str(entry['path']))
            if key not in sources or not any(job['status'] in ('running','queued') and key in job.get('source_ids',[]) for job in list(jobs.values())):sources[key]=entry
        except (KeyError,TypeError):continue
    restored_jobs={}
    for key,entry in data.get('jobs',{}).items():
        try:
            entry=dict(entry);entry['output']=Path(entry['output'])
            entry['variants']=[v|{'output':Path(v['output'])} for v in entry['variants']]
            if not all(v['output'].is_file() for v in entry['variants']):continue
            entry['cancel']=threading.Event();jobs.setdefault(key,entry);restored_jobs[key]=job_view(jobs[key])
        except (KeyError,TypeError):continue
    return jsonify(session=data['payload'],sources={key:public_source(sources[key]) for key in data['sources'] if key in sources},jobs=restored_jobs,missing=missing)


@app.get('/api/session/archives')
def queue_archives():
    result=[]
    for path in (BASE/'queues').glob('*.json'):
        try:
            data=json.loads(path.read_text(encoding='utf-8'));result.append(dict(id=path.stem,name=data.get('title','Пакет'),count=len(data['payload']['items']),saved_at=path.stat().st_mtime))
        except (OSError,ValueError,KeyError):continue
    return jsonify(archives=sorted(result,key=lambda item:item['saved_at'],reverse=True))


@app.post('/api/session/archive')
def archive_queue():
    data=workspace.read()
    if not data:return jsonify(saved=False)
    name=str((request.get_json(silent=True) or {}).get('name') or datetime.now().strftime('Пакет %d.%m.%Y %H:%M'))[:80]
    data['title']=name;key=uuid.uuid4().hex;folder=BASE/'queues';folder.mkdir(exist_ok=True)
    (folder/f'{key}.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    return jsonify(saved=True,id=key)


@app.post('/api/source-location')
def source_location():
    data=request.get_json(silent=True) or {};entry=sources.get(data.get('id'))
    if not entry:return jsonify(error='Исходник не найден.'),404
    path=entry['path']
    if data.get('open'):
        if not path.parent.is_dir():return jsonify(error='Папка исходника не найдена.'),400
        os.startfile(str(path.parent))
    return jsonify(path=str(path),folder=str(path.parent),exists=path.is_file())


@app.post('/api/job-log')
def job_log():
    job=jobs.get((request.get_json(silent=True) or {}).get('id'))
    if not job:return jsonify(error='Отчёт не найден.'),404
    return jsonify(reports=[v.get('report',{}) for v in job['variants']],error=job.get('error'))


@app.post('/api/frame')
def save_frame():
    import base64
    data=(request.get_json(silent=True) or {}).get('data','')
    if not isinstance(data,str) or not data.startswith('data:image/png;base64,') or len(data)>24*1024**2:return jsonify(error='Некорректный PNG-кадр.'),400
    try:
        raw=base64.b64decode(data.split(',',1)[1],validate=True)
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Некорректный PNG.')
        if window:
            import webview
            selected=window.create_file_dialog(webview.FileDialog.SAVE,save_filename='кадр.png',file_types=('PNG (*.png)',))
            if not selected:return jsonify(cancelled=True)
            path=Path(selected[0] if isinstance(selected,(list,tuple)) else selected).with_suffix('.png');path.write_bytes(raw);return jsonify(saved=str(path))
        key=uuid.uuid4().hex;folder=WORK/'frames';folder.mkdir(exist_ok=True);(folder/f'{key}.png').write_bytes(raw)
        return jsonify(download='/api/frames/'+key)
    except (ValueError,OSError) as exc:return jsonify(error=str(exc)),400


@app.get('/api/frames/<key>')
def frame_download(key):
    if not re.fullmatch(r'[a-f0-9]{32}',key):abort(404)
    return send_file(WORK/'frames'/f'{key}.png',as_attachment=True,download_name='кадр.png')


@app.post('/api/batch/preflight')
def preflight():
    data=request.get_json(silent=True) or {};items=data.get('items',[])
    if not isinstance(items,list) or len(items)>500:return jsonify(error='Некорректная очередь.'),400
    result=[];used_paths=set()
    for item in items:
        try:
            settings=validate_settings(item);ids=item.get('sources',[])
            if len(ids)!=2 or ids[0]==ids[1] or any(key not in sources or not sources[key]['path'].is_file() for key in ids):raise ValueError('Нужны два доступных разных исходника.')
            paths={sources[key]['path'].resolve() for key in ids}
            if len(paths)!=2 or paths&used_paths:raise ValueError('Один исходник используется в нескольких товарах. Оставьте одну пару.')
            used_paths.update(paths)
            for index,trim in enumerate(settings['trims']):
                if trim and trim[1]>sources[ids[index]]['info']['duration']+.001:raise ValueError('Граница выходит за исходник.')
            outputs=[output_path(item|settings|{'output':data.get('output'),'folder':item.get('name'),'_repeat':False}|({'_variant':fmt} if len(settings['formats'])>1 else {}),'check') for fmt in settings['formats']]
            result.append(dict(id=item.get('item_id'),status='ready',outputs=list(map(str,outputs))))
        except (ValueError,TypeError,KeyError) as exc:
            message=str(exc);result.append(dict(id=item.get('item_id'),status='existing' if 'уже существует' in message else 'error',error=message))
    return jsonify(items=result)


@app.post('/api/sources/check')
def check_sources():
    ids=(request.get_json(silent=True) or {}).get('sources',[])
    if not isinstance(ids,list) or not 1<=len(ids)<=1000 or any(key not in sources for key in ids):return jsonify(error='Выберите исходники.'),400
    key=uuid.uuid4().hex;task=dict(id=key,status='running',processed=0,total=len(ids),errors=[],groups=[],skipped=0,progress=0,stage='Проверяем исходники',current='',cancel=threading.Event(),eta_seconds=None);imports[key]=task
    def worker():
        for source_id in ids:
            if task['cancel'].is_set():break
            entry=sources[source_id];task['current']=entry['name']
            try:probe(entry['path'])
            except Exception as exc:task['errors'].append(dict(file=entry['name'],error=str(exc)))
            task['processed']+=1;task['progress']=round(task['processed']/task['total']*100)
        task['status']='cancelled' if task['cancel'].is_set() else 'done'
    task['thread']=threading.Thread(target=worker,daemon=True);task['thread'].start();return jsonify(id=key)


def cleanup():
    global cleanup_done
    if cleanup_done:return
    cleanup_done=True
    active = [*jobs.values(), *imports.values(), *batches.values()]
    for job in active:
        job["cancel"].set()
    if automation is not None:automation.shutdown()
    for job in active:
        worker = job.get("thread")
        if worker and worker.is_alive():
            try:
                worker.join(timeout=8)
            except RuntimeError:
                pass
    if last_workspace_store is workspace:
        try:
            saved=workspace.read()
            if saved:
                payload=saved['payload']
                for item in payload.get('items',[]):
                    ids=[source['id'] if source else None for source in item['snapshot'].get('sources',[])]
                    matching=[job for job in jobs.values() if not job.get('preview') and job.get('item_id')==item['id'] and job.get('source_ids')==ids and
                              (item.get('status') in ('queued','running') or payload.get('batch_id') and job.get('batch_id')==payload['batch_id'])]
                    if matching:
                        job=matching[-1];item['status']=job['status'];item['error']=job.get('error')
                        if job['status']=='done':item['snapshot'].update(result={'id':job['id']},stale=False)
                payload['batch_id']=None
                workspace.save(payload,sources,jobs,WORK)
        except Exception:logging.exception('Could not finalize saved workspace')
    # Session-specific directory: never touches source files or exported videos.
    shutil.rmtree(WORK, ignore_errors=True)


atexit.register(cleanup)


def main():
    global window, shell_updated, shell_command, background_start
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--open", nargs="+", default=[])
    parser.add_argument('--shell-action',default=None,choices=['add','new','review','quick','new-only','check','model','hands','resume','results','settings','preset','auto'])
    parser.add_argument('--preset')
    parser.add_argument('--register-shell',action='store_true')
    args = parser.parse_args()
    automatic=args.shell_action=='auto'
    background_start=automatic
    if automatic and not args.open:parser.error('Для автосборки укажите файл или папку через --open.')
    if args.register_shell:
        from explorer_menu import register_menu
        register_menu(Path(sys.executable),saved_presets());return
    from shell_bridge import claim_instance, publish_instance
    command=dict(action=args.shell_action,preset=args.preset) if args.shell_action else None
    owner = claim_instance(BASE, args.open, command) if command else claim_instance(BASE,args.open)
    if owner is False:
        return
    if not automatic:shell_paths.extend(str(Path(p).resolve()) for p in args.open)
    shell_command=None if automatic else command
    shell_updated = time.monotonic()
    server = create_server(app, host="127.0.0.1", port=args.port, threads=6)
    url = f"http://127.0.0.1:{server.effective_port}"
    if owner:
        publish_instance(BASE, url, TOKEN)
    if args.no_open:
        if automatic:get_automation().enqueue([str(Path(path).resolve()) for path in args.open])
        print(url, flush=True)
        server.run()
        return
    threading.Thread(target=server.run, daemon=True).start()
    if args.browser:
        webbrowser.open(url)
        threading.Event().wait()
    else:
        try:
            import webview
            window = webview.create_window("OUTMAX Cut", url, width=1340, height=900,
                                           min_size=(940, 700), background_color="#f4f4ef",hidden=automatic,focus=not automatic)
            if automatic:
                started=threading.Event()
                def start_automatic():
                    if started.is_set():return
                    started.set();ensure_background_tray()
                    try:get_automation().enqueue([str(Path(path).resolve()) for path in args.open])
                    except Exception as exc:
                        logging.exception('Automatic startup failed');notifications.notify(window,'Не удалось начать автосборку',str(exc),True,force=True,on_click=show_automation_report)
                window.events.loaded+=start_automatic
            close_state={'pending':False,'allowed':False}
            def closing():
                if close_state['allowed']:return True
                if close_state['pending']:return False
                if notifications.resident and automation is not None and automation.active and not background_exit_requested:
                    window.native.Hide();return False
                if busy() or any(i["status"] == "running" for i in imports.values()):
                    if not window.create_confirmation_dialog('Идёт обработка','Остановить обработку и закрыть программу? Очередь будет сохранена.'):return False
                close_state['pending']=True
                def persist_and_close():
                    try:
                        payload=window.evaluate_js('window.batchController && !state.backgroundMode ? JSON.stringify(window.batchController.persistPayload()) : null')
                        if payload:workspace.save(json.loads(payload),sources,jobs,WORK)
                        close_state['allowed']=True;window.destroy()
                    except Exception:
                        logging.exception('Could not save workspace on close');close_state['pending']=False
                        try:window.evaluate_js("showError('Не удалось сохранить очередь перед закрытием. Проверьте свободное место и повторите закрытие.')")
                        except Exception:pass
                threading.Thread(target=persist_and_close,daemon=True).start()
                return False
            window.events.closing += closing
            webview.start(gui="edgechromium", icon=str(RESOURCES / "assets/icon.ico"))
        except Exception:
            logging.exception("Native interface failed; opening browser")
            window = None
            webbrowser.open(url)
            threading.Event().wait()
        cleanup()
        server.close()


if __name__ == "__main__":
    main()
