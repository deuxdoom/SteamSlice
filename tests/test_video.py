"""실제 FFmpeg로 HDR 색상, SDR 보존과 팔레트 처리 두 경로를 검증한다."""
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from steamslice import core, video


class VideoColorTests(unittest.TestCase):
    folder: tempfile.TemporaryDirectory[str]
    root: Path
    sources: dict[str, Path]
    levels = (0.0, 1.0, 10.0, 50.0, 100.0, 200.0, 400.0, 1000.0)

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="video_color_", dir=core.temp_root())
        cls.root = Path(cls.folder.name)
        cls.sources = {}
        cls.addClassCleanup(cls.folder.cleanup)
        for transfer in ("smpte2084", "arib-std-b67", "bt709"):
            samples = []
            for nits in cls.levels:
                if transfer == "smpte2084":
                    # SMPTE ST 2084 EOTF의 역함수. 무채색 0~1000nit 패치를 만든다.
                    v = (nits / 10000) ** (2610 / 16384)
                    code = ((3424 / 4096 + 2413 / 128 * v) / (1 + 2392 / 128 * v)) ** (2523 / 32)
                elif transfer == "arib-std-b67":
                    v = nits / 1000
                    code = math.sqrt(3 * v) if v <= 1 / 12 else 0.17883277 * math.log(12 * v - 0.28466892) + 0.55991073
                else:
                    code = min(nits / 100, 1.0)
                samples.append(round(64 + 876 * code))
            row = b"".join(struct.pack("<H", code) * 40 for code in samples)
            raw = cls.root / f"{transfer}.yuv"
            raw.write_bytes(row * 180 + struct.pack("<H", 512) * (320 * 180 // 2))
            path = cls.root / f"{transfer}.mkv"
            primaries = "bt709" if transfer == "bt709" else "bt2020"
            matrix = "bt709" if transfer == "bt709" else "bt2020nc"
            code, _, err = video._run([
                "-loglevel", "error", "-stream_loop", "9", "-f", "rawvideo", "-pixel_format", "yuv420p10le",
                "-video_size", "320x180", "-framerate", "10", "-i", str(raw),
                "-vf", f"setparams=range=limited:color_primaries={primaries}:color_trc={transfer}:colorspace={matrix}",
                "-c:v", "ffv1", "-y", str(path)])
            if code:
                raise RuntimeError(err)
            cls.sources[transfer] = path

    def decode(self, data: bytes) -> bytes:
        image = self.root / "decode-image"
        image.write_bytes(data)
        code, pixels, err = video._run(["-loglevel", "error", "-i", str(image), "-frames:v", "1",
                                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        self.assertEqual(code, 0, err)
        return pixels

    def levels_at(self, data: bytes, width: int, height: int) -> list[int]:
        return [data[(height // 2 * width + (2 * i + 1) * width // 16) * 3] for i in range(8)]

    def test_hdr_metadata_and_color_levels(self):
        for transfer in ("smpte2084", "arib-std-b67"):
            with self.subTest(transfer=transfer):
                path = str(self.sources[transfer])
                info = video.probe(path)
                self.assertTrue(info.is_hdr)
                self.assertEqual((info.color_space, info.color_primaries, info.color_transfer, info.color_range),
                                 ("bt2020nc", "bt2020", transfer, "tv"))
                preview = self.decode(video.grab_frame(path, 0, max_w=320))
                levels = self.levels_at(preview, 320, 180)
                self.assertLessEqual(levels[0], 3)
                self.assertTrue(all(a < b for a, b in zip(levels, levels[1:])), levels)
                self.assertGreaterEqual(levels[4], 175, levels)  # 중간 밝기를 보존한다.
                self.assertLess(levels[6], 253, levels)  # 400nit와 1000nit를 구분한다.
                for two_pass in (False, True):
                    with self.subTest(two_pass=two_pass):
                        gif = self.root / f"{transfer}_{two_pass}.gif"
                        with patch.object(video, "ONE_PASS_MAX_PIXELS", 0 if two_pass else 50_000_000):
                            video.extract_gif(path, 0, 1, 10, 956, 537, str(gif))
                        self.assertEqual(core.probe(str(gif)), (956, 537, 10, 1000))
                        pixels = self.decode(gif.read_bytes())
                        gif_levels = self.levels_at(pixels, 956, 537)
                        self.assertLessEqual(max(abs(a - b) for a, b in zip(levels, gif_levels)), 5)

    def test_ten_bit_sdr_matches_previous_processing(self):
        path = str(self.sources["bt709"])
        self.assertFalse(video.probe(path).is_hdr)
        code, original, err = video._run(["-loglevel", "error", "-ss", "0.000", "-i", path,
                                         "-an", "-sn", "-dn", "-frames:v", "1", "-vf", "scale=320:-2:flags=bilinear",
                                         "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "3", "-"])
        self.assertEqual(code, 0, err)
        self.assertEqual(video.grab_frame(path, 0, max_w=320), original)
        gif = self.root / "sdr.gif"
        video.extract_gif(path, 0, 1, 10, 956, 537, str(gif))
        code, _, err = video._run([
            "-loglevel", "error", "-ss", "0.000", "-t", "1.000", "-i", path, "-lavfi",
            "fps=10,scale=956:537:flags=lanczos,setsar=1,split[a][b];[a]palettegen=stats_mode=full[p];"
            "[b][p]paletteuse=dither=floyd_steinberg:diff_mode=rectangle",
            "-an", "-sn", "-dn", "-loop", "0", "-f", "gif", "-y", str(self.root / "sdr-original.gif")])
        self.assertEqual(code, 0, err)
        self.assertEqual(gif.read_bytes(), (self.root / "sdr-original.gif").read_bytes())

    def test_hdr_core_output(self):
        result = core.run(str(self.sources["smpte2084"]), str(self.root / "parts"), clip=(0, 1, 10))
        self.assertEqual((result.frames, result.total_ms), (10, 1000))
        self.assertEqual(len(result.files), 5)
        for filename in result.files:
            data = Path(filename).read_bytes()
            self.assertEqual(struct.unpack("<HH", data[6:10]), (188, 537))
            self.assertEqual(data[-1], 0x21)
            self.assertLessEqual(len(data), core.SIZE_LIMIT)
        self.assertFalse(list((self.root / "parts").glob(".steamslice_*")))


if __name__ == "__main__":
    unittest.main()
