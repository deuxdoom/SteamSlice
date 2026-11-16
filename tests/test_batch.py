"""Qt에서 여러 파일 처리, 파일별 구간, 실패/취소와 폴더 설정 복원을 검증한다."""
from pathlib import Path
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QEventLoop, QPoint, QTimer
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication, QMessageBox
from steamslice import core, ui, video


def wait(ms: int):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class BatchTests(unittest.TestCase):
    app: QApplication
    folder: tempfile.TemporaryDirectory[str]
    root: Path
    gif: Path
    other: Path
    mp4: Path

    @classmethod
    def setUpClass(cls):
        app = QApplication.instance()
        cls.app = app if isinstance(app, QApplication) else QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        # Windows offscreen 플러그인은 시스템 글꼴을 자동으로 열거하지 않는다.
        if cls.app.platformName() == "offscreen" and sys.platform == "win32":
            for name in ("malgun.ttf", "malgunbd.ttf", "segoeui.ttf"):
                font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
                if font.is_file():
                    QFontDatabase.addApplicationFont(str(font))
        ui.apply_theme("dark")
        cls.folder = tempfile.TemporaryDirectory(prefix="batch_ui_", dir=core.temp_root())
        cls.addClassCleanup(cls.folder.cleanup)
        cls.root = Path(cls.folder.name)
        cls.gif, cls.other, cls.mp4 = (cls.root / name for name in ("first.gif", "second.gif", "video.mp4"))
        code, _, err = video._run(["-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=96x54:rate=10:duration=0.6",
                                   "-y", str(cls.gif)])
        if code:
            raise RuntimeError(err)
        shutil.copy2(cls.gif, cls.other)
        code, _, err = video._run(["-loglevel", "error", "-i", str(cls.gif), "-pix_fmt", "yuv420p", "-y", str(cls.mp4)])
        if code:
            raise RuntimeError(err)

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="case_", dir=self.root))
        self.settings_patch = patch.object(ui.settings, "path", return_value=self.work / "settings.json")
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        self.revealed = []
        reveal = patch.object(ui.steam, "reveal", side_effect=self.revealed.append)
        reveal.start()
        self.addCleanup(reveal.stop)
        question = patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes)
        question.start()
        self.addCleanup(question.stop)
        self.window = ui.Window()
        self.window.out_parent = str(self.work / "output")
        self.window.resize(1120, 760)
        self.window.show()
        wait(50)

    def tearDown(self):
        self.window.cleanup()
        self.window._closed = True
        self.window.close()
        self.window.deleteLater()
        wait(10)

    def wait_for(self, predicate, seconds=30):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            wait(10)
        self.assertTrue(predicate(), self.window.status.text())

    def add(self, paths):
        self.window.add_files([str(p) for p in paths])
        self.wait_for(lambda: self.window.loader is None)

    def geometry(self):
        w = self.window
        widgets = (w.preview, w.clip_stack, w.queue, w.dest_btn, w.go, w.stop, w.done_label, w.status)
        return (w.width(), w.height(), [(x.mapTo(w, QPoint()).x(), x.mapTo(w, QPoint()).y(), x.width(), x.height()) for x in widgets])

    def test_mixed_batch_keeps_per_file_clip_and_results(self):
        w = self.window
        baseline = self.geometry()
        self.add([self.gif, self.mp4])
        self.assertEqual(self.geometry(), baseline)
        w.queue.setCurrentIndex(1)
        self.assertIsNotNone(w.vinfo)
        w.bar.set_range(0.6, 0.1, 0.4)
        w.fps.setCurrentIndex(w.fps.findData(10))
        w.sync_clip()
        w.queue.setCurrentIndex(0)
        self.assertIsNone(w.clip())
        w.queue.setCurrentIndex(1)
        self.assertEqual(w.clip(), (0.1, 0.4, 10))
        w.start()
        self.assertFalse(w.queue.isEnabled())
        self.wait_for(lambda: w.worker is None)
        self.assertEqual([item.state for item in w.items], ["완료", "완료"])
        self.assertEqual(self.geometry(), baseline)
        self.assertEqual(len(self.revealed), 1)
        self.assertIn("성공 2개", w.status.text())
        for index, ms in ((0, 600), (1, 300)):
            w.queue.setCurrentIndex(index)
            result = w.result
            self.assertIsNotNone(result)
            if result is None:
                self.fail("result missing")
            self.assertEqual(result.total_ms, ms)
            self.assertEqual(len(result.files), 5)
            self.assertTrue(all(Path(path).is_file() for path in result.files))
            self.assertEqual(w.path_label.full_text, result.out_dir)
            self.assertEqual(self.geometry(), baseline)
        # 완료한 영상의 구간을 바꾸면 이전 조각이 새 구간의 결과로 표시되지 않는다.
        w.queue.setCurrentIndex(1)
        w.s_start.setValue(0.2)
        self.assertIsNone(w.result)
        self.assertIsNone(w.items[1].result)
        self.assertEqual(w.items[1].state, "대기")
        self.assertIsNotNone(w.items[0].result)

    def test_batch_continues_after_one_source_disappears(self):
        w = self.window
        missing = self.work / "vanished.gif"
        shutil.copy2(self.gif, missing)
        self.add([missing, self.other])
        w.queue.setCurrentIndex(1)
        wait(20)  # Windows에서는 QMovie가 연 파일 핸들을 먼저 해제한다.
        missing.unlink()
        w.start()
        self.wait_for(lambda: w.worker is None)
        self.assertEqual([item.state for item in w.items], ["실패", "완료"])
        self.assertIn("실패 1개", w.status.text())
        self.assertTrue(w.items[0].error)
        self.assertIsNotNone(w.items[1].result)
        self.assertTrue(w.b_folder.isEnabled())

    def test_cancel_keeps_completed_result_and_pending_item(self):
        w = self.window
        self.add([self.gif, self.other])
        real_run = core.run
        calls = []
        def run(src, out_dir, **kwargs):
            calls.append(src)
            if len(calls) == 2:
                kwargs["cancel"].set()
                raise core.Cancelled()
            return real_run(src, out_dir, **kwargs)
        with patch.object(core, "run", side_effect=run):
            w.start()
            self.wait_for(lambda: w.worker is None)
        self.assertEqual([item.state for item in w.items], ["완료", "대기"])
        self.assertIn("완료한 1개", w.status.text())
        first = w.items[0].result
        self.assertIsNotNone(first)
        if first is not None:
            self.assertTrue(all(Path(path).is_file() for path in first.files))
        w.queue.setCurrentIndex(0)
        self.assertIs(w.result, first)

    def test_recent_input_and_output_folders_restore(self):
        w = self.window
        self.add([self.gif])
        w.save_preferences()
        restored = ui.Window()
        try:
            self.assertEqual(restored.out_parent, w.out_parent)
            self.assertEqual(restored.preferences["last_open_dir"], str(self.root))
            with patch.object(ui.QFileDialog, "getOpenFileNames", return_value=([], "")) as picker:
                restored.pick()
            self.assertEqual(picker.call_args.args[2], str(self.root))
        finally:
            restored.cleanup()
            restored._closed = True
            restored.close()
            restored.deleteLater()

    def test_duplicate_add_remove_and_output_collision(self):
        w = self.window
        self.add([self.gif, self.gif])
        self.assertEqual(len(w.items), 1)
        other_dir = self.work / "same-name"
        other_dir.mkdir()
        duplicate = other_dir / self.gif.name
        shutil.copy2(self.gif, duplicate)
        self.add([duplicate])
        w.start()
        self.assertIsNone(w.worker)
        self.assertIn("저장 폴더가 겹칩니다", w.status.text())
        w.remove_item()
        self.assertEqual(len(w.items), 1)
        w.remove_item()
        self.assertFalse(w.items)
        self.assertFalse(w.go.isEnabled())


if __name__ == "__main__":
    unittest.main()
