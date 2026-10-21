"""Build a self-contained Windows executable and a per-user Inno Setup installer."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import importlib.metadata
import hashlib

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
from engine import binary
from version import VERSION


def copy_notices(dest):
    licenses = dest / "LICENSES"
    licenses.mkdir(exist_ok=True)
    for package in ("Flask", "Werkzeug", "waitress", "numpy", "opencv-python",
                    "pywebview", "pythonnet", "clr_loader", "cffi", "pycparser",
                    "bottle", "proxy_tools", "Jinja2", "MarkupSafe", "click",
                    "itsdangerous", "blinker", "typing_extensions"):
        distribution = importlib.metadata.distribution(package)
        for file in distribution.files or []:
            if any(word in file.name.lower() for word in ("license", "copying", "copyright")):
                source = distribution.locate_file(file)
                if source.is_file() and source.suffix.lower() not in (".pyc", ".pyd", ".dll"):
                    folder = licenses / package
                    folder.mkdir(exist_ok=True)
                    shutil.copy2(source, folder / file.name)
    (licenses / "Python.txt").write_text(sys.copyright, encoding="utf-8")


def main():
    if os.name != "nt":
        raise SystemExit("Run this build on Windows.")
    iscc = shutil.which("ISCC")
    if not iscc:
        for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""),
                     str(Path(os.environ["LOCALAPPDATA"]) / "Programs")):
            candidate = Path(base) / "Inno Setup 6" / "ISCC.exe"
            if candidate.is_file():
                iscc = str(candidate)
                break
    if not iscc:
        raise SystemExit("Install Inno Setup 6 from https://jrsoftware.org/isdl.php, then run BUILD.bat again.")
    bins = ROOT / "vendor" / "bin"
    bins.mkdir(parents=True, exist_ok=True)
    for name in ("ffmpeg", "ffprobe"):
        source = Path(binary(name)).resolve()
        target = bins / (name + ".exe")
        if source != target.resolve():
            shutil.copy2(source, target)
    notices = ROOT / "vendor" / "licenses"
    notices.mkdir(exist_ok=True)
    ffmpeg_root = Path(binary("ffmpeg")).resolve().parent.parent
    for filename in ("LICENSE", "LICENSE.txt", "README.txt"):
        if (ffmpeg_root / filename).exists():
            shutil.copy2(ffmpeg_root / filename, notices / ("FFmpeg-" + filename))
    (notices / "FFmpeg-build.txt").write_bytes(
        subprocess.check_output([str(bins / "ffmpeg.exe"), "-version"]))
    (notices / "FFmpeg-configuration.txt").write_bytes(
        subprocess.check_output([str(bins / "ffmpeg.exe"), "-buildconf"], stderr=subprocess.STDOUT))
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--onedir", "--windowed", "--name", "OUTMAX-Cut",
                    "--distpath", str(ROOT / "dist" / VERSION),
                    "--version-file", "tools/version_info.txt",
                    "--icon", "assets/icon.ico",
                    "--add-data", "ui;ui", "--add-data", "assets;assets",
                    "--add-data", "vendor/licenses;licenses",
                    "--add-binary", "vendor/bin/ffmpeg.exe;bin",
                    "--add-binary", "vendor/bin/ffprobe.exe;bin",
                    "--collect-all", "webview", "--collect-all", "clr_loader",
                    "--collect-submodules", "numpy._core",
                    "--hidden-import", "webview.platforms.edgechromium",
                    "--hidden-import", "clr", "--hidden-import", "pythonnet",
                    "--exclude-module", "matplotlib", "--exclude-module", "pandas",
                    "--exclude-module", "scipy", "--exclude-module", "IPython",
                    "launcher.py"], check=True)
    dest = ROOT / "dist" / VERSION / "OUTMAX-Cut"
    shutil.copy2(ROOT / "README.md", dest / "README.md")
    shutil.copy2(ROOT / "THIRD_PARTY.md", dest / "THIRD_PARTY.md")
    copy_notices(dest)
    if "--no-installer" not in sys.argv:
        subprocess.run([iscc, f"/DAppVersion={VERSION}", str(ROOT / "tools/installer.iss")], check=True)
        installer = ROOT / f"release/OUTMAX-Cut-Setup-{VERSION}.exe"
        with installer.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        (ROOT / "release/SHA256.txt").write_text(f"{digest}  {installer.name}\n", encoding="utf-8")
        print("Installer:", installer)


if __name__ == "__main__":
    main()
