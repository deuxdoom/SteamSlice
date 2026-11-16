"""실제 Gifsicle로 용량 맞춤, 가변 간격과 합성 프레임의 보존을 검증한다."""
from pathlib import Path
import random
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from steamslice import core, video


def tiny_gif(path: Path, delays: list[int]):
    data = bytearray(b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff")
    data.extend(b"!\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00")
    for index, delay in enumerate(delays):
        data.extend(b"!\xf9\x04\x04" + struct.pack("<H", delay) + b"\x00\x00")
        data.extend(b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02")
        data.extend(bytes((0x4c if index % 2 else 0x44, 1, 0)))
    path.write_bytes(data + b";")


class CapacityTests(unittest.TestCase):
    folder: tempfile.TemporaryDirectory[str]
    root: Path
    source: Path

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="capacity_", dir=core.temp_root())
        cls.addClassCleanup(cls.folder.cleanup)
        cls.root = Path(cls.folder.name)
        raw = cls.root / "noise.rgb"
        raw.write_bytes(random.Random(123).randbytes(956 * 64 * 3 * 12))
        cls.source = cls.root / "noise.gif"
        code, _, err = video._run([
            "-loglevel", "error", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "956x64",
            "-framerate", "10", "-i", str(raw), "-lavfi", "split[a][b];[a]palettegen[p];[b][p]paletteuse",
            "-y", str(cls.source)])
        if code:
            raise RuntimeError(err)

    def test_color_reduction_before_frame_reduction(self):
        stages = []
        with patch.object(core, "SIZE_LIMIT", 160_000):
            result = core.run(str(self.source), str(self.root / "colors"), lossy_start=180, on_progress=stages.append)
        self.assertEqual((result.lossy, result.colors, result.frame_step), (200, 128, 1))
        self.assertEqual((result.frames, result.total_ms), (12, 1200))
        self.assertLess(stages.index("자르기 (2회차, 압축 200)"), stages.index("자르기 (3회차, 압축 200, 128색)"))
        self.assertTrue(all(size <= 160_000 for size in result.sizes))

    def test_frame_reduction_keeps_all_slice_durations(self):
        with patch.object(core, "SIZE_LIMIT", 30_000):
            result = core.run(str(self.source), str(self.root / "frames"), lossy_start=200)
        self.assertEqual(result.colors, 32)
        self.assertGreater(result.frame_step, 1)
        self.assertLess(result.frames, result.source_frames)
        self.assertEqual(result.total_ms, 1200)
        for filename, size in zip(result.files, result.sizes):
            self.assertLessEqual(size, 30_000)
            self.assertEqual(core.probe(filename)[3], 1200)
            self.assertEqual(Path(filename).read_bytes()[-1], 0x21)

    def test_selected_frames_are_composited_before_skipping(self):
        expanded = str(self.root / "expanded.gif")
        # FFmpeg가 생성한 GIF는 부분 프레임과 투명 배경을 사용한다.
        animated = self.root / "delta.gif"
        code, _, err = video._run(["-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=96x54:rate=10:duration=1",
                                   "-lavfi", "split[a][b];[a]palettegen[p];[b][p]paletteuse", "-y", str(animated)])
        self.assertEqual(code, 0, err)
        core._wait([core._Job(["--unoptimize"], str(animated), expanded)], threading.Event())
        output = str(self.root / "selected.gif")
        core.thin_frames(expanded, core.frame_delays(expanded), 2, output, threading.Event())
        for original_index, selected_index in zip(range(0, 10, 2), range(5)):
            pixels = []
            for path, index in ((str(animated), original_index), (output, selected_index)):
                code, raw, err = video._run(["-loglevel", "error", "-i", path, "-vf", f"select=eq(n\\,{index})",
                                             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
                self.assertEqual(code, 0, err)
                pixels.append(raw)
            self.assertEqual(pixels[0], pixels[1])

    def test_variable_delays_and_gif_delay_limit(self):
        source = self.root / "variable.gif"
        delays = [4, 5, 65535, 2, 9, 3, 1]
        tiny_gif(source, delays)
        self.assertEqual(core.frame_delays(str(source)), delays)
        target = str(self.root / "variable-thin.gif")
        core.thin_frames(str(source), delays, 4, target, threading.Event())
        self.assertEqual(core.frame_delays(target), [9, 65535, 15])
        self.assertEqual(core.probe(target)[3], sum(delays) * 10)

    def test_long_selection_uses_multiple_chunks(self):
        source = self.root / "long.gif"
        tiny_gif(source, [4, 5] * 260)
        target = str(self.root / "long-thin.gif")
        core.thin_frames(str(source), core.frame_delays(str(source)), 2, target, threading.Event())
        self.assertEqual(core.probe(target), (1, 1, 260, 23400))
        self.assertEqual(core.frame_delays(target), [9] * 260)

    def test_cancel_during_fallback_preserves_previous_files(self):
        output = self.root / "cancel"
        output.mkdir()
        old = output / "noise_1.gif"
        old.write_bytes(b"previous result")
        cancel = threading.Event()
        def stage(text):
            if text.startswith("프레임 감축"):
                cancel.set()
        with patch.object(core, "SIZE_LIMIT", 30_000):
            with self.assertRaises(core.Cancelled):
                core.run(str(self.source), str(output), cancel=cancel, lossy_start=200, on_progress=stage)
        self.assertEqual(old.read_bytes(), b"previous result")
        self.assertFalse(list(output.glob(".steamslice_*")))


if __name__ == "__main__":
    unittest.main()
