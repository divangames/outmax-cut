"""Collect Explorer's individual launches in one local editor instance."""
import atexit
import json
import os
import time
import urllib.request

_lease = None


def claim_instance(base, paths):
    global _lease
    if os.name != "nt":
        return None
    import msvcrt
    lease = (base / "shell.lock").open("a+b")
    if os.fstat(lease.fileno()).st_size == 0:
        lease.write(b"0")
        lease.flush()
    for _ in range(100):
        lease.seek(0)
        try:
            msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
            _lease = lease
            atexit.register(lease.close)
            return True
        except OSError:
            if not paths:
                lease.close()
                return None
            try:
                data = json.loads((base / "shell.json").read_text(encoding="utf-8"))
                url = data["url"]
                if not url.startswith("http://127.0.0.1:") or not url.rsplit(":", 1)[-1].isdigit():
                    raise ValueError("Invalid local instance")
                req = urllib.request.Request(url + "/api/shell/enqueue",
                    json.dumps({"paths": paths}).encode(),
                    {"Content-Type": "application/json", "X-Outmax-Token": data["token"]})
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.status == 200:
                        lease.close()
                        return False
            except (OSError, ValueError, KeyError):
                time.sleep(.2)
    lease.close()
    raise RuntimeError("Открытый редактор не отвечает. Закройте его и повторите открытие файлов.")


def publish_instance(base, url, token):
    temporary = base / "shell.json.tmp"
    temporary.write_text(json.dumps({"url": url, "token": token}), encoding="utf-8")
    temporary.replace(base / "shell.json")
