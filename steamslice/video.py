"""동영상에서 원하는 구간을 GIF로 추출한다. ffmpeg를 사용하며 Qt에 의존하지 않는다."""
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

from steamslice.core import Cancelled
from steamslice.core import SliceError as VideoError

VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".wmv", ".ts")
FPS_CHOICES = (25, 20, 10)   # GIF의 프레임 간격은 1/100초 단위이므로, 간격이 정확히 떨어지는 값만 쓴다
DEFAULT_FPS = 25
MAX_CLIP_SECONDS = 30.0      # 이보다 긴 구간은 5MB 한도를 맞추기 어려우므로 허용하지 않는다
MIN_CLIP_SECONDS = 0.2
# 한 번에 처리해도 메모리가 넉넉한 프레임 수 × 폭 × 높이의 한도. 넘으면 팔레트 생성과 변환을 나누어 실행한다.
ONE_PASS_MAX_PIXELS = 50_000_000

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float


def is_video(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def ffmpeg_path():
    """ffmpeg.exe를 찾는다: 실행 파일에 포함된 것 → tools 폴더 → 실행 파일 옆 → 시스템 PATH."""
    base = getattr(sys, "_MEIPASS", None)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [os.path.join(base, "ffmpeg.exe")] if base else []
    candidates.append(os.path.join(root, "tools", "ffmpeg.exe"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "ffmpeg.exe"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise VideoError("ffmpeg.exe를 찾을 수 없습니다. 동영상을 사용하려면 ffmpeg.exe를 프로그램 폴더에 넣어 주세요.")


def _run(args, cancel=None, timeout=600.0):
    """ffmpeg를 창 없이 실행하고 (종료 코드, 표준 출력, 오류 출력)을 반환한다. 취소되면 프로세스를 종료한다."""
    try:
        proc = subprocess.Popen([ffmpeg_path(), "-hide_banner", "-nostdin", *args],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=_NO_WINDOW)
    except OSError as e:
        raise VideoError("ffmpeg를 실행할 수 없습니다: " + str(e))
    deadline = time.monotonic() + timeout
    with proc:
        while True:
            try:
                out, err = proc.communicate(timeout=0.05)
                return proc.returncode, out, err.decode("utf-8", "replace")
            except subprocess.TimeoutExpired:
                cancelled = cancel is not None and cancel.is_set()
                if not cancelled and time.monotonic() < deadline:
                    continue
                proc.kill()
                proc.communicate()
                if cancelled:
                    raise Cancelled() from None
                raise VideoError("동영상 처리 시간이 너무 오래 걸려서 중단했습니다.") from None


def probe(path, cancel=None):
    """동영상의 길이, 크기, 프레임 레이트를 읽는다."""
    if not os.path.isfile(path):
        raise VideoError("파일을 찾을 수 없습니다: " + path)
    _, _, err = _run(["-i", path], cancel=cancel, timeout=30)
    m_d = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
    m_v = re.search(r"Stream #.*Video:.*?[ ,](\d{2,5})x(\d{2,5})[ ,\[]", err)
    if not m_d or not m_v:
        raise VideoError("동영상을 읽을 수 없습니다. 다른 파일을 선택해 주세요.")
    duration = int(m_d.group(1)) * 3600 + int(m_d.group(2)) * 60 + float(m_d.group(3))
    m_f = re.search(r"([\d.]+) fps", err)
    width, height = int(m_v.group(1)), int(m_v.group(2))
    if re.search(r"rotation of -?(90|270)", err):   # 세로로 촬영한 영상은 표시 크기가 반대이다
        width, height = height, width
    if duration <= 0:
        raise VideoError("동영상의 길이를 알 수 없습니다. 다른 파일을 선택해 주세요.")
    return VideoInfo(duration, width, height, float(m_f.group(1)) if m_f else 0.0)


def grab_frame(path, ts, max_w=960, cancel=None):
    """지정한 시각의 프레임을 JPEG 바이트로 반환한다. 끝부분에서 프레임이 없으면 조금 앞에서 다시 시도한다."""
    err = ""
    for t in (max(0.0, ts), max(0.0, ts - 0.5), max(0.0, ts - 2.0)):
        _, out, err = _run(["-loglevel", "error", "-ss", f"{t:.3f}", "-i", path, "-an", "-sn", "-dn",
                            "-frames:v", "1", "-vf", f"scale={max_w}:-2:flags=bilinear",
                            "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "3", "-"],
                           cancel=cancel, timeout=30)
        if out:
            return out
        if t == 0.0:
            break
    raise VideoError("해당 위치의 화면을 읽을 수 없습니다: " + (err.strip().splitlines()[-1] if err.strip() else ""))


def check_clip(info, start, end):
    """구간이 올바른지 확인한다. 올바르지 않으면 이유를 담은 VideoError를 발생시킨다."""
    if start < 0 or end > info.duration + 0.05 or end - start < MIN_CLIP_SECONDS:
        raise VideoError("구간이 올바르지 않습니다. 시작과 끝 시각을 다시 지정해 주세요.")
    if end - start > MAX_CLIP_SECONDS + 0.001:
        raise VideoError(f"구간이 너무 깁니다. {MAX_CLIP_SECONDS:.0f}초 이하로 지정해 주세요.")


def extract_gif(path, start, end, fps, width, height, out_gif, cancel=None):
    """[start, end) 구간을 width×height, fps의 GIF로 추출한다.

    구간 전체에서 256색 팔레트를 만든 뒤에 적용하므로 색이 깨지지 않는다.
    """
    length = end - start
    if fps not in FPS_CHOICES:
        raise VideoError("FPS는 25, 20, 10 중에서 선택해 주세요.")
    src = ["-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", path]
    frames = f"fps={fps},scale={width}:{height}:flags=lanczos,setsar=1"
    use = "paletteuse=dither=floyd_steinberg:diff_mode=rectangle"
    tail = ["-an", "-sn", "-dn", "-loop", "0", "-f", "gif", "-y", out_gif]
    if length * fps * width * height <= ONE_PASS_MAX_PIXELS:
        graph = f"{frames},split[a][b];[a]palettegen=stats_mode=full[p];[b][p]{use}"
        steps = [["-loglevel", "error", *src, "-lavfi", graph, *tail]]
    else:
        palette = out_gif + ".palette.png"
        steps = [["-loglevel", "error", *src, "-an", "-sn", "-dn",
                  "-vf", f"{frames},palettegen=stats_mode=full", "-frames:v", "1", "-update", "1", "-y", palette],
                 ["-loglevel", "error", *src, "-i", palette, "-lavfi", f"{frames}[x];[x][1:v]{use}", *tail]]
    for args in steps:
        code, _, err = _run(args, cancel=cancel)
        if code != 0:
            raise VideoError("GIF 추출에 실패했습니다: " + (err.strip().splitlines()[-1] if err.strip() else "원인 불명"))
    if not os.path.isfile(out_gif) or os.path.getsize(out_gif) == 0:
        raise VideoError("GIF 추출에 실패했습니다. 구간을 다시 지정해 주세요.")
