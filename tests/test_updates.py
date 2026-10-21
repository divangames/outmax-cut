import hashlib
import io
import pathlib
import tempfile
import unittest
from unittest.mock import patch, Mock
import types

from app import app, TOKEN, validate_settings
from updater import Updater, release_info, version_tuple, RELEASES_URL


def release(payload=b"installer", version="1.4.0"):
    name = f"OUTMAX-Cut-Setup-{version}.exe"
    return {"tag_name": "v" + version, "draft": False, "prerelease": False,
            "assets": [{"name": name, "browser_download_url": f"{RELEASES_URL}/download/v{version}/{name}",
                        "size": len(payload), "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}]}


class UpdateTests(unittest.TestCase):
    def test_bitrate_defaults_and_bounds(self):
        self.assertEqual(validate_settings({})["bitrate_kbps"], 2500)
        for value in (500, 1065, 1500, 2500):
            self.assertEqual(validate_settings({"bitrate_kbps": value})["bitrate_kbps"], value)
        for value in (None, True, "2500", 0, 499, 2501, 2.5, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_settings({"bitrate_kbps": value})

    def test_version_order_and_release_selection(self):
        self.assertGreater(version_tuple("v1.10.0"), version_tuple("1.9.9"))
        self.assertIsNone(release_info(release(version="1.3.0"), "1.3.0"))
        self.assertIsNone(release_info(release(version="1.2.1"), "1.3.0"))
        self.assertIsNone(release_info(release() | {"prerelease": True}, "1.3.0"))
        self.assertEqual(release_info(release(), "1.3.0")["version"], "1.4.0")
        for value in ("v1.4.0-beta", "../setup", None):
            with self.assertRaises(ValueError):
                version_tuple(value)

    def test_reject_missing_or_untrusted_installer(self):
        data = release()
        for changes in ({"digest": None}, {"size": 0}, {"browser_download_url": "https://example.com/setup.exe"}):
            with self.assertRaises(ValueError):
                release_info(data | {"assets": [data["assets"][0] | changes]}, "1.3.0")
        with self.assertRaises(ValueError):
            release_info(data | {"assets": []}, "1.3.0")

    def test_download_integrity_and_tampering(self):
        payload = b"test-installer"
        with tempfile.TemporaryDirectory() as folder:
            updater = Updater(folder)
            updater.release = release_info(release(payload), "1.3.0")
            with patch("updater.open_url", return_value=io.BytesIO(payload)):
                updater._download(updater.release)
            self.assertEqual(updater.snapshot()["status"], "ready")
            path = updater.installer()
            path.write_bytes(b"modified")
            with self.assertRaises(ValueError):
                updater.installer()
            with patch("updater.open_url", return_value=io.BytesIO(b"bad")):
                updater._download(updater.release)
            self.assertEqual(updater.snapshot()["status"], "available")
            self.assertFalse(list(pathlib.Path(folder).glob("*.part")))

    def test_update_endpoints_require_session_and_packaged_app(self):
        with app.test_client() as client:
            for action in ("check", "download", "install"):
                self.assertEqual(client.post("/api/updates/" + action, json={}).status_code, 403)
            self.assertEqual(client.post("/api/updates/install", json={}, headers={"X-Outmax-Token": TOKEN}).status_code, 409)

    def test_window_creation_failure_opens_browser(self):
        import app as server
        http = Mock(effective_port=12345)
        broken_webview = types.SimpleNamespace(create_window=Mock(side_effect=RuntimeError("WebView2 missing")))
        with patch.dict("sys.modules", webview=broken_webview), \
             patch("sys.argv", ["OUTMAX-Cut"]), \
             patch("shell_bridge.claim_instance", return_value=None), \
             patch.object(server, "create_server", return_value=http), \
             patch.object(server.threading, "Thread"), \
             patch.object(server.threading, "Event"), \
             patch.object(server.webbrowser, "open") as browser, \
             patch.object(server, "cleanup"):
            server.main()
            browser.assert_called_once_with("http://127.0.0.1:12345")
            self.assertIsNone(server.window)


if __name__ == "__main__":
    unittest.main()
