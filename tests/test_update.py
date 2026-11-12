"""업데이트 검증, 경로 검사와 교체 실패 복원을 독립적으로 확인한다."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from steamslice import apply_update, core, updater
from steamslice.instance import InstanceLock


class UpdateTests(unittest.TestCase):
    def test_save_failure_restores_existing_results(self):
        with tempfile.TemporaryDirectory(dir=core.temp_root()) as folder:
            root = Path(folder)
            parts = []
            output = root / "output"
            output.mkdir()
            for i in range(5):
                src = root / f"{i}.gif"
                src.write_bytes(b"new")
                parts.append(str(src))
                (output / f"test_{i + 1}.gif").write_bytes(b"old")
            original_replace = core.os.replace

            def replace(src, dst):
                if Path(src).name == "new_2.gif":
                    raise OSError("disk full")
                original_replace(src, dst)

            with patch.object(core.os, "replace", side_effect=replace):
                with self.assertRaises(core.SliceError):
                    core.save_parts(parts, str(output), "test", threading.Event())
            self.assertEqual(len(list(output.iterdir())), 5)
            self.assertTrue(all(p.read_bytes() == b"old" for p in output.iterdir()))

    def test_interrupted_download_can_retry_after_restart(self):
        with tempfile.TemporaryDirectory(dir=core.temp_root()) as folder:
            root = Path(folder)
            work = root / updater.WORK_NAME
            work.mkdir()
            (work / "package.zip").write_bytes(b"partial")
            with patch.object(updater, "supported", return_value=True), patch.object(core, "app_dir", return_value=str(root)):
                self.assertIn("정리", updater.previous_result())
            self.assertFalse(work.exists())

    @unittest.skipUnless(sys.platform == "win32", "Windows mutex")
    def test_mutex_keeps_first_owner(self):
        first = InstanceLock("SteamSlice.tests.lock")
        second = InstanceLock("SteamSlice.tests.lock")
        try:
            self.assertTrue(first.acquired)
            self.assertFalse(second.acquired)
            second.close()
            third = InstanceLock("SteamSlice.tests.lock")
            self.assertFalse(third.acquired)
            third.close()
        finally:
            first.close()
            second.close()
        last = InstanceLock("SteamSlice.tests.lock")
        self.assertTrue(last.acquired)
        last.close()

    def payload(self):
        name = updater.asset_name("1.2.3")
        sha = "a" * 64
        return {"tag_name": "v1.2.3", "body": f"SHA-256 `{name}`\n```text\n{sha}\n```",
                "assets": [{"name": name, "size": 1234, "state": "uploaded", "digest": "sha256:" + sha,
                            "browser_download_url": updater.DOWNLOAD_PREFIX + "v1.2.3/" + name}]}

    def test_release_requires_matching_body_digest_and_asset(self):
        payload = self.payload()
        self.assertEqual(updater.parse_release(payload).version, "1.2.3")
        payload["body"] = "b" * 64
        with self.assertRaises(updater.UpdateError):
            updater.parse_release(payload)
        payload = self.payload()
        payload["assets"][0]["browser_download_url"] = "https://evil.example/package.zip"
        with self.assertRaises(updater.UpdateError):
            updater.parse_release(payload)
        for version in ("v1.0.1-beta", "v1.0", "v1.0.0/../x"):
            with self.assertRaises(updater.UpdateError):
                updater.version_tuple(version)

    def package(self, path: Path, extra: str = ""):
        with zipfile.ZipFile(path, "w") as archive:
            for name in ("SteamSlice.exe", "bin/python314.dll", "bin/ffmpeg.exe", "bin/gifsicle.exe"):
                archive.writestr("SteamSlice/" + name, b"payload")
            archive.writestr("SteamSlice/settings.json", b"must not overwrite")
            if extra:
                archive.writestr(extra, b"unsafe")

    def test_zip_rejects_windows_path_escape(self):
        with tempfile.TemporaryDirectory(dir=core.temp_root()) as folder:
            root = Path(folder)
            for entry in ("../outside", "SteamSlice/bin/../../outside", "C:/outside", "SteamSlice/bin/x:ads", "SteamSlice/bin/a./x"):
                self.package(root / "bad.zip", entry)
                with self.assertRaises(updater.UpdateError):
                    updater.extract(root / "bad.zip", root / "bad", threading.Event())
            self.package(root / "good.zip")
            updater.extract(root / "good.zip", root / "new", threading.Event())
            self.assertTrue((root / "new/bin/ffmpeg.exe").is_file())
            self.assertFalse((root / "new/settings.json").exists())

    def test_cancelled_extract_stops_before_install(self):
        with tempfile.TemporaryDirectory(dir=core.temp_root()) as folder:
            root = Path(folder)
            self.package(root / "good.zip")
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(core.Cancelled):
                updater.extract(root / "good.zip", root / "new", cancel)

    def tree(self, root: Path, content: str):
        (root / "bin").mkdir(parents=True)
        (root / updater.EXE_NAME).write_text(content)
        (root / "bin/library.dll").write_text(content)

    def test_success_preserves_user_data(self):
        with tempfile.TemporaryDirectory(dir=core.temp_root()) as folder:
            root = Path(folder)
            self.tree(root, "old")
            work = root / updater.WORK_NAME
            self.tree(work / "new", "new")
            (root / "settings.json").write_text("settings")
            (root / "output").mkdir()
            (root / "output/result.gif").write_bytes(b"GIF89a")
            launched = []
            self.assertTrue(apply_update.replace_payload(root, work, launched.append)["ok"])
            self.assertEqual((root / updater.EXE_NAME).read_text(), "new")
            self.assertEqual((root / "settings.json").read_text(), "settings")
            self.assertEqual((root / "output/result.gif").read_bytes(), b"GIF89a")
            self.assertEqual(launched, [root / updater.EXE_NAME])

    def test_partial_install_rolls_back(self):
        with tempfile.TemporaryDirectory(dir=core.temp_root()) as folder:
            root = Path(folder)
            self.tree(root, "old")
            work = root / updater.WORK_NAME
            self.tree(work / "new", "new")
            with patch.object(apply_update.shutil, "copytree", side_effect=OSError("disk full")):
                result = apply_update.replace_payload(root, work, lambda exe: None)
            self.assertFalse(result["ok"])
            self.assertEqual((root / updater.EXE_NAME).read_text(), "old")
            self.assertEqual((root / "bin/library.dll").read_text(), "old")
            self.assertFalse(json.loads((work / "result.json").read_text())["ok"])

    def test_download_hash_mismatch_removes_file(self):
        class Response:
            def __init__(self):
                self.chunks = iter([b"payload", b""])
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, size):
                return next(self.chunks)

        release = updater.Release("1.2.3", "v1.2.3", "test.zip", updater.DOWNLOAD_PREFIX + "v1.2.3/test.zip", 7, "a" * 64, "")
        with tempfile.TemporaryDirectory(dir=core.temp_root()) as folder:
            target = Path(folder) / "package.zip"
            with patch.object(updater.urllib.request.OpenerDirector, "open", return_value=Response()):
                with self.assertRaises(updater.UpdateError):
                    updater.download(release, target, threading.Event(), lambda text: None)
            self.assertFalse(target.exists())
            self.assertNotEqual(hashlib.sha256(b"payload").hexdigest(), release.sha256)


if __name__ == "__main__":
    unittest.main()
