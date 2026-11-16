"""GIF를 스팀 창작마당 전시대용 5조각으로 자르는 핵심 로직. Qt에 의존하지 않는다."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass

APP_ID = "SteamSlice"       # 프로그램명. 임시 폴더와 중복 실행 방지 이름에 사용한다.

N = 5                      # 조각 수
GAP = 4                    # 조각 사이 간격(px)
SLICE_W = 188              # 조각 폭(px)
TOTAL_W = N * SLICE_W + (N - 1) * GAP   # 956
SIZE_LIMIT = 5_000_000     # 조각당 용량 한도(바이트)
LOSSY_START, LOSSY_STEP, LOSSY_MAX = 80, 20, 200
COLOR_STEPS = (128, 64, 32)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class SliceError(Exception):
    """사용자에게 그대로 보여줄 수 있는 오류."""


class Cancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled()


@dataclass
class Plan:
    total_w: int
    total_h: int
    lefts: list[int]
    upscaled: bool


@dataclass
class Result:
    files: list[str]       # files[0]이 1번(가장 왼쪽) 조각
    sizes: list[int]
    lossy: int
    seconds: float
    frames: int
    total_ms: int
    upscaled: bool
    out_dir: str
    stem: str              # 결과 파일 이름과 업로드 제목의 앞부분
    colors: int | None = None
    frame_step: int = 1
    source_frames: int = 0


def plan(width, height):
    total_h = max(1, height * TOTAL_W // width)
    lefts = [i * (SLICE_W + GAP) for i in range(N)]
    return Plan(TOTAL_W, total_h, lefts, width < TOTAL_W)


def gifsicle_path():
    base = getattr(sys, "_MEIPASS", None)
    candidates = [os.path.join(base, "gifsicle.exe")] if base else []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(root, "tools", "gifsicle.exe"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    raise SliceError("gifsicle.exe를 찾을 수 없습니다. 프로그램을 다시 설치해 주세요.")


def temp_root():
    """프로그램이 실행 중에 쓰는 임시 작업 폴더의 상위 경로.

    기본값은 시스템의 임시 폴더 아래의 <프로그램명> 폴더이다(운영체제의 일반적인 규칙).
    환경 변수 STEAMSLICE_TEMP가 있으면 그 경로를 쓴다. 개발용 PC처럼 위치를 강제해야 하는 경우에 사용한다.
    """
    for root in (os.environ.get("STEAMSLICE_TEMP"), os.path.join(tempfile.gettempdir(), APP_ID)):
        if not root:
            continue
        try:
            os.makedirs(root, exist_ok=True)
            return root
        except OSError:
            continue
    return tempfile.gettempdir()


class _Job:
    """gifsicle 프로세스 하나. 입력과 출력을 파이썬이 연 파일로 넘겨서 한글 경로에서도 동작하게 한다."""

    def __init__(self, args, src, dst=None):
        self.err = None
        try:
            with ExitStack() as stack:
                fin = stack.enter_context(open(src, "rb"))
                fout = stack.enter_context(open(dst, "wb")) if dst else None
                # 경고가 많아도 파이프가 차서 멈추지 않도록 파일로 받는다.
                self.err = open(dst + ".err", "w+b") if dst else None
                self.proc = subprocess.Popen([gifsicle_path(), *args], stdin=fin,
                                             stdout=fout if fout else subprocess.PIPE,
                                             stderr=self.err if self.err else subprocess.PIPE,
                                             creationflags=_NO_WINDOW)
        except OSError as e:
            if self.err:
                self.err.close()
            raise SliceError("gifsicle을 실행할 수 없습니다: " + str(e))

    def error_text(self):
        if not self.err:
            return ""
        self.err.seek(0)
        return self.err.read().decode("utf-8", "replace").strip()

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        for stream in (self.proc.stdout, self.proc.stderr, self.err):
            if stream:
                stream.close()


def _wait(jobs, cancel):
    """모든 작업이 끝날 때까지 기다린다. 취소되거나 실패하면 전부 종료한다."""
    try:
        while any(j.proc.poll() is None for j in jobs):
            if cancel.is_set():
                raise Cancelled()
            time.sleep(0.05)
        for j in jobs:
            if j.proc.returncode != 0:
                err = j.error_text()
                raise SliceError("GIF 처리에 실패했습니다: " + (err.splitlines()[-1] if err else "원인 불명"))
    finally:
        for j in jobs:
            j.close()


def _info_text(path, cancel=None):
    if not os.path.isfile(path):
        raise SliceError("파일을 찾을 수 없습니다: " + path)
    job = _Job(["--info"], path)
    try:
        deadline = time.monotonic() + 30
        while True:
            check_cancel(cancel)
            try:
                out, _ = job.proc.communicate(timeout=0.05)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    raise SliceError("GIF 검사 시간이 너무 오래 걸려서 중단했습니다.") from None
    finally:
        job.close()
    if job.proc.returncode != 0:
        raise SliceError("GIF 파일이 아니거나 손상된 파일입니다. 다른 파일을 선택해 주세요.")
    return out.decode("utf-8", "replace")


def probe(path, cancel=None):
    """(폭, 높이, 프레임 수, 총 재생 시간 ms)을 반환한다."""
    text = _info_text(path, cancel)
    m_n = re.search(r"(\d+) images?", text)
    m_s = re.search(r"logical screen (\d+)x(\d+)", text)
    if not m_n or not m_s:
        raise SliceError("GIF 파일이 아니거나 손상된 파일입니다. 다른 파일을 선택해 주세요.")
    total = sum(round(float(d) * 1000) for d in re.findall(r"delay ([\d.]+)s", text))
    return int(m_s.group(1)), int(m_s.group(2)), int(m_n.group(1)), total


def frame_delays(path, cancel=None) -> list[int]:
    """Gifsicle이 읽은 프레임별 간격을 1/100초 단위로 반환한다. 간격이 없으면 0이다."""
    images = re.split(r"\+ image #\d+\b", _info_text(path, cancel))[1:]
    return [round(float(m.group(1)) * 100) if (m := re.search(r"delay ([\d.]+)s", image)) else 0
            for image in images]


def thin_frames(expanded, delays: list[int], step: int, dst, cancel):
    """합성된 전체 프레임에서 일부를 고르고 생략 구간의 시간을 합친다."""
    selections: list[tuple[int, int]] = []
    start = 0
    while start < len(delays):
        end, delay = start, 0
        while end < min(start + step, len(delays)):
            if delay + delays[end] > 65535:
                break   # GIF 간격 필드의 16비트 한도 안에서만 합친다.
            delay += delays[end]
            end += 1
        selections.append((start, delay))
        start = end
    chunks = []
    # Windows 명령줄 길이 제한을 피한다. 긴 GIF도 동일한 프레임 선택 규칙을 사용한다.
    for offset in range(0, len(selections), 256):
        check_cancel(cancel)
        args = []
        for index, delay in selections[offset:offset + 256]:
            args.extend([f"--delay={delay}", f"#{index}"])
        chunk = f"{dst}.{offset}.gif"
        _wait([_Job(args, expanded, chunk)], cancel)
        chunks.append(chunk)
    if len(chunks) == 1:
        os.replace(chunks[0], dst)
    else:
        joined = dst + ".multi"
        with open(joined, "wb") as out:
            for chunk in chunks:
                check_cancel(cancel)
                with open(chunk, "rb") as source:
                    shutil.copyfileobj(source, out)
        _wait([_Job(["--multifile"], joined, dst)], cancel)


def compression_summary(result: Result) -> str:
    details = [f"압축 {result.lossy}"]
    if result.colors is not None:
        details.append(f"{result.colors}색")
    if result.frame_step > 1:
        details.append(f"프레임 {result.source_frames} → {result.frames} (재생 시간 유지)")
    return " · ".join(details)


def patch_trailer(path):
    """마지막 바이트가 3B이면 21로 바꾼다. 조각 양쪽의 검은 테두리를 막기 위한 처리이다."""
    with open(path, "r+b") as f:
        f.seek(-1, os.SEEK_END)
        if f.read(1) == b"\x3B":
            f.seek(-1, os.SEEK_END)
            f.write(b"\x21")


def stem_for(src, clip=None):
    """결과 파일 이름의 앞부분. 동영상은 구간(밀리초)을 붙여서 구간마다 다른 이름이 되게 한다."""
    stem = os.path.splitext(os.path.basename(src))[0]
    if clip:
        stem += f"_{round(clip[0] * 1000)}_{round(clip[1] * 1000)}"
    return stem


def app_dir():
    """배포본은 실행 파일 옆, 소스 실행은 프로젝트 루트를 기준으로 한다."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def output_root():
    return os.path.join(app_dir(), "output")


def default_out_dir(src, clip=None):
    return os.path.join(output_root(), stem_for(src, clip) + "_steam")


def save_parts(parts, out_dir, stem, cancel):
    """같은 드라이브에서 교체하고, 저장 실패 시 기존 결과 다섯 개를 복원한다."""
    staging = None
    installed = []
    backups = []
    files = [os.path.join(out_dir, f"{stem}_{i + 1}.gif") for i in range(N)]
    try:
        os.makedirs(out_dir, exist_ok=True)
        staging = tempfile.mkdtemp(prefix=".steamslice_", dir=out_dir)
        for i, part in enumerate(parts):
            check_cancel(cancel)
            shutil.copy2(part, os.path.join(staging, f"new_{i}.gif"))
        for i, dst in enumerate(files):
            check_cancel(cancel)
            if os.path.exists(dst):
                old = os.path.join(staging, f"old_{i}.gif")
                os.replace(dst, old)
                backups.append((dst, old))
            os.replace(os.path.join(staging, f"new_{i}.gif"), dst)
            installed.append(dst)
        return files
    except (OSError, Cancelled) as exc:
        try:
            for dst in reversed(installed):
                os.remove(dst)
            for dst, old in reversed(backups):
                os.replace(old, dst)
        except OSError as rollback_error:
            # 복원까지 실패하면 백업을 삭제하지 않아 수동으로 찾을 수 있게 한다.
            recovery = staging
            staging = None
            raise SliceError(f"저장에 실패했습니다. 기존 파일 백업을 확인해 주세요: {recovery} ({rollback_error})") from exc
        if isinstance(exc, Cancelled):
            raise
        raise SliceError(f"저장 위치에 파일을 쓸 수 없습니다. 저장 위치를 변경해 주세요: {out_dir} ({exc.strerror})") from exc
    finally:
        if staging:
            shutil.rmtree(staging, ignore_errors=True)


def run(src, out_dir=None, on_progress=None, cancel=None, lossy_start=LOSSY_START, clip=None):
    """src를 5조각으로 잘라 out_dir에 저장하고 Result를 반환한다.

    src가 동영상이면 clip=(시작 초, 끝 초, fps) 구간을 먼저 GIF로 추출한 뒤에 자른다.
    """
    from steamslice import video   # video가 이 모듈의 오류 클래스를 쓰므로, 순환 import를 피해서 여기서 불러온다

    say = on_progress or (lambda stage: None)
    cancel = cancel or threading.Event()
    started = time.time()

    say("검사")
    is_video = video.is_video(src)
    info = None
    if is_video:
        info = video.probe(src, cancel)
        clip = clip or (0.0, min(info.duration, video.MAX_CLIP_SECONDS), video.DEFAULT_FPS)
        video.check_clip(info, clip[0], clip[1])
        width, height, frames, total_ms = info.width, info.height, 0, 0
    else:
        clip = None
        width, height, frames, total_ms = probe(src, cancel)
    check_cancel(cancel)
    pl = plan(width, height)
    stem = stem_for(src, clip)
    out_dir = out_dir or default_out_dir(src, clip)

    tmp = tempfile.mkdtemp(prefix="job_", dir=temp_root())
    try:
        full = os.path.join(tmp, "full.gif")
        if clip:
            say("동영상에서 GIF 추출")
            video.extract_gif(src, clip[0], clip[1], clip[2], pl.total_w, pl.total_h, full, cancel, info=info)
            _, _, frames, total_ms = probe(full, cancel)
        else:
            say("축소")
            _wait([_Job(["--resize", f"{pl.total_w}x{pl.total_h}", "--resize-method", "lanczos3"],
                        src, full)], cancel)

        parts = [os.path.join(tmp, f"{i + 1}.gif") for i in range(N)]
        lossy = max(0, min(LOSSY_MAX, lossy_start))
        source_frames = frames
        colors = None
        frame_step = 1
        expanded = os.path.join(tmp, "expanded.gif")
        thinned = os.path.join(tmp, "thinned.gif")
        delays: list[int] = []
        input_gif = full
        attempt = 1
        while True:
            detail = f"압축 {lossy}" + (f", {colors}색" if colors else "")
            if frame_step > 1:
                detail += f", 프레임 {frames}/{source_frames}"
            say(f"자르기 ({attempt}회차, {detail})")
            jobs = []
            try:
                for x, part in zip(pl.lefts, parts):
                    check_cancel(cancel)
                    args = ["--crop", f"{x},0+{SLICE_W}x{pl.total_h}", "-O3", f"--lossy={lossy}"]
                    if colors is not None:
                        args.extend(["--colors", str(colors)])
                    jobs.append(_Job(args, input_gif, part))
                _wait(jobs, cancel)
            finally:
                for job in jobs:
                    job.close()
            sizes = [os.path.getsize(p) for p in parts]
            if max(sizes) <= SIZE_LIMIT:
                break
            if lossy < LOSSY_MAX:
                lossy = min(LOSSY_MAX, lossy + LOSSY_STEP)
            elif colors != COLOR_STEPS[-1]:
                colors = COLOR_STEPS[0] if colors is None else COLOR_STEPS[COLOR_STEPS.index(colors) + 1]
            elif frame_step < source_frames:
                if not delays:
                    say("프레임 감축 준비")
                    _wait([_Job(["--unoptimize"], full, expanded)], cancel)
                    delays = frame_delays(expanded, cancel)
                    if len(delays) != source_frames or sum(delays) * 10 != total_ms:
                        raise SliceError("프레임 간격을 읽을 수 없습니다. 더 짧은 파일을 사용해 주세요.")
                frame_step = min(source_frames, frame_step * 2)
                say(f"프레임 감축 (최대 {frame_step}개 간격 합치기, 재생 시간 유지)")
                thin_frames(expanded, delays, frame_step, thinned, cancel)
                _, _, frames, ms = probe(thinned, cancel)
                if ms != total_ms:
                    raise SliceError("프레임 감축 후 재생 시간 검사에 실패했습니다.")
                input_gif = thinned
            else:
                over = ", ".join(f"{i + 1}번 {s / 1e6:.1f}MB" for i, s in enumerate(sizes) if s > SIZE_LIMIT)
                advice = ("구간을 더 짧게 지정하거나 FPS를 낮춰 주세요." if clip
                          else "더 짧거나 움직임이 적은 GIF를 사용해 주세요.")
                raise SliceError(f"조각의 용량이 5MB를 넘습니다 (압축 {lossy} 기준: {over}). " + advice)
            attempt += 1

        say("마무리")
        for part in parts:
            w, h, n, ms = probe(part, cancel)
            # 조각 안에서 변화가 없는 프레임은 gifsicle이 하나로 합치므로 프레임 수는 줄어들 수 있다.
            # 재생 시간이 같으면 조각들의 재생이 서로 어긋나지 않는다.
            if (w, h, ms) != (SLICE_W, pl.total_h, total_ms) or not 0 < n <= frames:
                raise SliceError("결과물 검사에 실패했습니다. 다시 시도해 주세요.")
            patch_trailer(part)
        if cancel.is_set():
            raise Cancelled()

        files = save_parts(parts, out_dir, stem, cancel)
        return Result(files, sizes, lossy, time.time() - started, frames, total_ms, pl.upscaled, out_dir, stem,
                      colors, frame_step, source_frames)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
