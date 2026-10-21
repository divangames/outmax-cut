"""Capture startup failures even before the UI or processing imports are available."""
import os
from pathlib import Path
import sys
import traceback

if __name__ == "__main__":
    try:
        from app import main
        main()
    except Exception as exc:
        folder = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OutmaxCut"
        folder.mkdir(parents=True, exist_ok=True)
        log = folder / "startup-error.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        if sys.stderr:
            traceback.print_exc()
        elif os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, f"Не удалось запустить OUTMAX Cut.\n\n{type(exc).__name__}: {exc}\n\nПодробности:\n{log}\n\nНажмите Ctrl+C, чтобы скопировать это сообщение.",
                "OUTMAX Cut", 0x10)
        sys.exit(1)
