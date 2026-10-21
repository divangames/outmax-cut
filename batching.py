"""Folder grouping and explainable local role suggestions."""
from collections import defaultdict
from pathlib import Path, PurePosixPath
import re
import unicodedata
import json

import cv2
import numpy as np

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
MODEL_WORDS = re.compile(r"(?i)(?:^|[\s_.()-])(model|модель|модели|ноги|ногах|feet|legs)(?=$|[\s_.()-])")
HANDS_WORDS = re.compile(r"(?i)(?:^|[\s_.()-])(hands?|руки|руках|ручки)(?=$|[\s_.()-])")


def is_generated_video(path):
    manifest = path.with_suffix(".json")
    if not manifest.is_file() or manifest.stat().st_size > 1024**2:
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return isinstance(data, dict) and (
            data.get("generator") == "OUTMAX Cut" or
            (data.get("frames") == 658 and data.get("fps") == 30 and
             "transition_note" in data and "settings" in data and "segments" in data))
    except (ValueError, OSError):
        return False


def name_role(name):
    stem = Path(name).stem
    model, hands = bool(MODEL_WORDS.search(stem)), bool(HANDS_WORDS.search(stem))
    return "model" if model and not hands else "hands" if hands and not model else None


def model_score(proxy):
    """Rank full portrait images by upper-body occupancy against a studio background.

    This is a heuristic, not a trained classifier. The UI always exposes corrections.
    """
    cap = cv2.VideoCapture(str(proxy))
    count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    samples = []
    try:
        for fraction in (.2, .35, .5, .65, .8):
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(count*fraction)))
            ok, image = cap.read()
            if not ok:
                continue
            image = cv2.resize(image, (90, 160))
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
            # Robust background estimate from both upper side margins.
            edges = np.concatenate([lab[:100, :8].reshape(-1,3), lab[:100, -8:].reshape(-1,3)])
            background = np.median(edges, axis=0)
            distance = np.linalg.norm(lab-background, axis=2)
            foreground = distance > 25
            upper = float(foreground[8:65, 20:70].mean())
            vertical = float((foreground[:, 20:70].mean(axis=1) > .3).mean())
            samples.append(.8*upper + .2*vertical)
    finally:
        cap.release()
    return float(np.median(samples)) if samples else .5


def suggest_pair(candidates):
    if len(candidates) != 2:
        return [None, None], "Выберите два исходника вручную: в папке не два видео."
    a, b = candidates
    ar, br = name_role(a["name"]), name_role(b["name"])
    if (ar == "model" and br != "model") or (br == "hands" and ar != "hands"):
        return [a["id"], b["id"]], "Роли определены по названиям файлов."
    if (br == "model" and ar != "model") or (ar == "hands" and br != "hands"):
        return [b["id"], a["id"]], "Роли определены по названиям файлов."
    ordered = sorted(candidates, key=lambda c: c.get("model_score", .5), reverse=True)
    difference = abs(a.get("model_score", .5)-b.get("model_score", .5))
    note = ("Роли предложены по изображению. Проверьте порядок." if difference >= .18 else
            "Неуверенное определение. Проверьте «Модель» и «Руки».")
    return [ordered[0]["id"], ordered[1]["id"]], note


def group_sources(entries):
    """One leaf folder per product, or matching *_model/*_hands names."""
    by_folder = defaultdict(list)
    for entry in entries:
        relative = PurePosixPath(entry.get("relative", entry["name"]).replace("\\", "/"))
        parent = str(relative.parent)
        by_folder[parent].append(entry)
    groups = []
    for folder, candidates in sorted(by_folder.items(), key=lambda item:item[0].casefold()):
        split = defaultdict(list)
        if len(candidates) > 2:
            for candidate in candidates:
                name = Path(candidate["name"]).stem
                stem = MODEL_WORDS.sub(" ", name)
                stem = HANDS_WORDS.sub(" ", stem)
                stem = re.sub(r"[\s_.()-]+", " ", stem).strip().casefold()
                split[stem if name_role(candidate["name"]) else "__unknown__"].append(candidate)
        if len(candidates) > 2 and len(split) > 1 and "__unknown__" not in split:
            for stem, members in sorted(split.items()):
                groups.append((f"{folder}/{stem}", members))
        else:
            groups.append((folder if folder != "." else "Ролик", candidates))
    result = []
    for name, candidates in groups:
        pair, note = suggest_pair(candidates)
        result.append(dict(name=name, candidates=candidates, sources=pair, detection=note))
    return result


def safe_folder(name):
    # Preserve product hierarchy but never permit traversal, ADS, or device names.
    parts = []
    for part in str(name).replace("\\", "/").split("/"):
        part = unicodedata.normalize("NFC", part)
        part = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", part).rstrip(" .")
        if not part:
            continue
        if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part):
            part = "_" + part
        parts.append(part)
    return Path(*parts) if parts else Path("Ролик")
