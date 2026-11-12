"""핵심 기능 검증. 실패한 항목만 출력하고 종료 코드로 결과를 알린다."""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from steamslice import core, video  # noqa: E402

fails = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


SRC = os.path.join(ROOT, "GIFs", "output3.gif")
TEMP = core.temp_root()
check(core.default_out_dir(SRC) == os.path.join(ROOT, "output", "output3_steam"), "기본 저장 위치가 프로그램 옆 output/이 아님")
check(core.default_out_dir(SRC, (1.0, 4.0, 25)) == os.path.join(ROOT, "output", "output3_1000_4000_steam"), "구간별 기본 저장 위치가 다름")
tmp = tempfile.mkdtemp(prefix="verify_", dir=TEMP)
try:
    out = os.path.join(tmp, "out")
    t = time.time()
    r = core.run(SRC, out)
    elapsed = time.time() - t
    check(len(r.files) == 5, "조각이 5개가 아님")
    for i, f in enumerate(r.files, 1):
        with open(f, "rb") as fh:
            data = fh.read()
        w, h = struct.unpack("<HH", data[6:10])
        check((w, h) == (188, 537), f"{i}번 크기 {w}x{h}")
        check(data[-1] == 0x21, f"{i}번 마지막 바이트 {data[-1]:02X}")
        check(len(data) <= 5_000_000, f"{i}번 용량 {len(data)}")
    check(r.frames == 168, f"프레임 수 {r.frames}")
    check(r.total_ms == 7000, f"재생 시간 {r.total_ms}")
    check(elapsed <= 40, f"소요 시간 {elapsed:.1f}초")
    check(not any(n.startswith("job_") for n in os.listdir(TEMP)), "임시 폴더가 남음")

    # 동영상: GIF로 시험용 MP4를 만든 뒤, 1초~4초 구간을 25fps로 추출하여 자른다.
    mp4 = os.path.join(tmp, "clip.mp4")
    subprocess.run([video.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-i", SRC,
                    "-pix_fmt", "yuv420p", "-vf", "scale=1280:720", mp4], check=True)
    info = video.probe(mp4)
    check((info.width, info.height) == (1280, 720) and abs(info.duration - 7.0) < 0.2,
          f"동영상 정보 {info}")
    check(video.grab_frame(mp4, 6.9)[:2] == bytes([0xFF, 0xD8]), "프레임 추출 결과가 JPEG가 아님")
    v = core.run(mp4, os.path.join(tmp, "vout"), clip=(1.0, 4.0, 25))
    check((v.frames, v.total_ms) == (75, 3000), f"동영상 구간 {v.frames}프레임 {v.total_ms}ms")
    check(v.stem == "clip_1000_4000", f"동영상 결과 이름 {v.stem}")
    for i, f in enumerate(v.files, 1):
        with open(f, "rb") as fh:
            data = fh.read()
        check(struct.unpack("<HH", data[6:10]) == (188, 537), f"동영상 {i}번 크기")
        check(data[-1] == 0x21 and len(data) <= 5_000_000, f"동영상 {i}번 끝 바이트 또는 용량 {len(data)}")
    try:
        core.run(mp4, os.path.join(tmp, "vbad"), clip=(5.0, 3.0, 25))
        check(False, "잘못된 구간이 통과됨")
    except core.SliceError:
        pass
    check(not any(n.startswith("job_") for n in os.listdir(TEMP)), "동영상 처리 후 임시 폴더가 남음")

    missing = os.path.join(tmp, "없는파일.gif")
    p = subprocess.run([sys.executable, "-m", "steamslice", missing], cwd=ROOT, capture_output=True)
    check(p.returncode == 1, f"없는 파일의 종료 코드 {p.returncode}")
    check(not os.path.exists(core.default_out_dir(missing)), "실패했는데 출력 폴더가 생성됨")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

for m in fails:
    print("FAIL:", m)
print("OK" if not fails else f"{len(fails)}건 실패", f"({elapsed:.1f}초)")
sys.exit(1 if fails else 0)
