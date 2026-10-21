"""Stable GitHub Releases updates, downloaded and verified before installation."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import re
import threading
import urllib.error
import urllib.request

from version import VERSION

REPOSITORY = "divangames/outmax-cut"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("Неизвестный формат версии релиза.")
    return tuple(map(int, value.removeprefix("v").split(".")))


def release_info(data, current=VERSION):
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name", "")
    if version_tuple(tag) <= version_tuple(current):
        return None
    version = tag.removeprefix("v")
    name = f"OUTMAX-Cut-Setup-{version}.exe"
    asset = next((a for a in data.get("assets", []) if a.get("name") == name), None)
    if not asset:
        raise ValueError("В новом релизе пока нет установщика для Windows.")
    url = f"{RELEASES_URL}/download/{tag}/{name}"
    if asset.get("browser_download_url") != url:
        raise ValueError("Некорректный адрес установщика.")
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError("В релизе отсутствует SHA-256 установщика. Повторите проверку позже.")
    size = asset.get("size")
    if not isinstance(size, int) or not 0 < size <= 2 * 1024**3:
        raise ValueError("Некорректный размер установщика.")
    return dict(version=version, name=name, url=url, size=size, sha256=digest[7:].lower())


def open_url(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={
        "User-Agent": f"OUTMAX-Cut/{VERSION}", "Accept": "application/vnd.github+json"
    }), timeout=30)


class Updater:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.lock = threading.Lock()
        self.release = None
        self.state = dict(status="idle", current=VERSION, progress=0, error=None)

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def _set(self, **values):
        with self.lock:
            self.state.update(values)

    def check(self):
        with self.lock:
            if self.state["status"] in ("checking", "downloading", "installing"):
                return
            self.state = dict(status="checking", current=VERSION, progress=0, error=None)
            self.release = None
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        try:
            with open_url(API_URL) as response:
                data = json.loads(response.read(2 * 1024**2))
            release = release_info(data)
            with self.lock:
                self.release = release
                self.state.update(status="available" if release else "current",
                                  latest=release["version"] if release else VERSION,
                                  size=release["size"] if release else 0)
        except urllib.error.HTTPError as exc:
            message = ("Релизы пока не опубликованы." if exc.code == 404 else
                       "GitHub временно ограничил проверку. Попробуйте позже." if exc.code in (403, 429) else
                       "GitHub недоступен. Повторите проверку позже.")
            self._set(status="error", error=message)
        except Exception as exc:
            logging.exception("Update check failed")
            message = str(exc) if isinstance(exc, ValueError) else "Не удалось проверить обновления. Проверьте подключение к интернету."
            self._set(status="error", error=message)

    def download(self):
        with self.lock:
            if self.state["status"] == "downloading":
                return
            if self.state["status"] != "available" or not self.release:
                raise ValueError("Сначала проверьте наличие новой версии.")
            release = dict(self.release)
            self.state.update(status="downloading", progress=0, error=None)
        threading.Thread(target=self._download, args=(release,), daemon=True).start()

    def _download(self, release):
        partial = self.folder / (release["name"] + ".part")
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            received = 0
            with open_url(release["url"]) as response, partial.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > release["size"]:
                        raise ValueError("Размер загрузки не совпадает с релизом.")
                    output.write(chunk)
                    digest.update(chunk)
                    self._set(progress=round(received / release["size"] * 100))
            if received != release["size"] or digest.hexdigest() != release["sha256"]:
                raise ValueError("Проверка SHA-256 не пройдена. Скачайте обновление заново.")
            partial.replace(self.folder / release["name"])
            self._set(status="ready", progress=100)
        except Exception as exc:
            logging.exception("Update download failed")
            partial.unlink(missing_ok=True)
            message = str(exc) if isinstance(exc, ValueError) else "Не удалось скачать обновление. Проверьте интернет и свободное место на диске."
            self._set(status="available", error=message, progress=0)

    def installer(self):
        with self.lock:
            if self.state["status"] != "ready" or not self.release:
                raise ValueError("Сначала скачайте обновление.")
            path = self.folder / self.release["name"]
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if digest != self.release["sha256"]:
                self.state.update(status="available", progress=0)
                raise ValueError("Файл установщика изменился. Скачайте его заново.")
            return path
