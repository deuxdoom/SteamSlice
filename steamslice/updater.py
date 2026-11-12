"""GitHub 릴리스 조회, SHA-256 검증과 ZIP 준비. 참고: APEXGIFMAKER 업데이트 흐름."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit

from steamslice import REPOSITORY, REPO_URL, __version__, core

API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
DOWNLOAD_PREFIX = f"{REPO_URL}/releases/download/"
EXE_NAME = "SteamSlice.exe"
WORK_NAME = "update-workspace"
UPDATE_SERVER = "SteamSlice.update"
MAX_PACKAGE = 500 * 1024 * 1024
MAX_UNPACKED = 1500 * 1024 * 1024
HEADERS = {"User-Agent": f"SteamSlice/{__version__}", "Accept": "application/vnd.github+json"}


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    name: str
    url: str
    size: int
    sha256: str
    body: str


def version_tuple(text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text)
    if match is None:
        raise UpdateError("릴리스 버전 형식이 올바르지 않습니다.")
    return int(match[1]), int(match[2]), int(match[3])


def asset_name(version: str) -> str:
    return f"SteamSlice_v{version.replace('.', '')}.zip"


def parse_release(payload: object) -> Release:
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        raise UpdateError("정식 릴리스를 찾을 수 없습니다.")
    tag = str(payload.get("tag_name", ""))
    version_tuple(tag)
    version = tag.removeprefix("v")
    name = asset_name(version)
    body = str(payload.get("body") or "")
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        raise UpdateError("릴리스 파일 목록을 읽을 수 없습니다.")
    for item in assets:
        if not isinstance(item, dict) or item.get("name") != name or item.get("state") != "uploaded":
            continue
        size = item.get("size")
        sha = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", str(item.get("digest", "")))
        url = f"{DOWNLOAD_PREFIX}{tag}/{name}"
        if (isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_PACKAGE
                or sha is None or item.get("browser_download_url") != url):
            raise UpdateError("크기 또는 GitHub SHA-256 정보가 없어 자동 업데이트할 수 없습니다.")
        written = ""
        lines = body.splitlines()
        for i, line in enumerate(lines):
            if name in line:
                match = re.search(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])", "\n".join(lines[i:i + 5]))
                if match:
                    written = match[0].lower()
                    break
        if written != sha[1].lower():
            raise UpdateError("릴리스 본문의 SHA-256과 GitHub 확인값이 일치하지 않습니다.")
        return Release(version, tag, name, url, size, written, body)
    raise UpdateError("이 버전의 Windows ZIP을 찾을 수 없습니다.")


def fetch_latest() -> Release:
    request = urllib.request.Request(API_URL, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise UpdateError("릴리스 응답이 너무 큽니다.")
        return parse_release(json.loads(data))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("아직 공개된 릴리스가 없습니다.") from None
        if exc.code in (403, 429):
            raise UpdateError("GitHub 조회 한도에 도달했습니다. 잠시 후 다시 확인해 주세요.") from None
        raise UpdateError(f"업데이트 서버 오류: HTTP {exc.code}") from None
    except (OSError, ValueError) as exc:
        raise UpdateError(f"업데이트를 확인할 수 없습니다. 인터넷 연결을 확인해 주세요. ({exc})") from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download(release: Release, target: Path, cancel: threading.Event,
             progress: Callable[[str], None]) -> None:
    opener = urllib.request.build_opener(_NoRedirect)
    url, received = release.url, 0
    digest = hashlib.sha256()
    try:
        with target.open("wb") as out:
            for hop in range(6):
                core.check_cancel(cancel)
                parts = urlsplit(url)
                allowed = {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
                if (parts.scheme != "https" or parts.hostname not in allowed or parts.username
                        or parts.password or parts.port or (hop == 0 and not url.startswith(DOWNLOAD_PREFIX))):
                    raise UpdateError("허용되지 않은 다운로드 주소입니다.")
                try:
                    response = opener.open(urllib.request.Request(url, headers=HEADERS), timeout=5)
                except urllib.error.HTTPError as exc:
                    location = exc.headers.get("Location")
                    if exc.code not in (301, 302, 303, 307, 308) or not location:
                        raise
                    url = urljoin(url, location)
                    exc.close()
                    continue
                with response:
                    while True:
                        core.check_cancel(cancel)
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        received += len(chunk)
                        if received > release.size:
                            raise UpdateError("다운로드 크기가 릴리스 정보와 다릅니다.")
                        digest.update(chunk)
                        out.write(chunk)
                        progress(f"업데이트 다운로드 {received * 100 // release.size}%")
                break
            else:
                raise UpdateError("다운로드 주소가 너무 많이 변경되었습니다.")
        if received != release.size or digest.hexdigest() != release.sha256:
            raise UpdateError("SHA-256 또는 파일 크기가 일치하지 않습니다. 받은 파일을 폐기했습니다.")
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def extract(package: Path, destination: Path, cancel: threading.Event) -> None:
    """정해진 exe/bin만 추출한다. Windows 경로 탈출·링크·중복·과도한 압축은 거부한다."""
    with zipfile.ZipFile(package) as archive:
        infos = archive.infolist()
        if len(infos) > 15000 or sum(info.file_size for info in infos) > MAX_UNPACKED:
            raise UpdateError("압축을 푼 크기가 허용 범위를 넘습니다.")
        seen: set[str] = set()
        for info in infos:
            name = info.filename.replace("\\", "/")
            parts = name.rstrip("/").split("/")
            if (not name or name.startswith("/") or any(p in ("", ".", "..") or ":" in p
                    or p.endswith((" ", ".")) for p in parts)
                    or stat.S_ISLNK(info.external_attr >> 16) or name.lower() in seen):
                raise UpdateError("안전하지 않은 ZIP 경로입니다.")
            seen.add(name.lower())
        roots = ["", "SteamSlice/"]
        root = next((r for r in roots if r + EXE_NAME in seen
                     or (r + EXE_NAME).lower() in seen), None)
        if root is None:
            raise UpdateError("ZIP에 SteamSlice.exe가 없습니다.")
        selected = [(info, info.filename.replace("\\", "/")[len(root):]) for info in infos
                    if info.filename.replace("\\", "/").startswith(root)]
        members = {name.lower() for _, name in selected}
        required = {"bin/gifsicle.exe", "bin/ffmpeg.exe"}
        if not required.issubset(members) or not any(re.fullmatch(r"bin/python3\d+\.dll", name) for name in members):
            raise UpdateError("ZIP에 필요한 실행 라이브러리가 없습니다.")
        for info, relative in selected:
            core.check_cancel(cancel)
            if relative != EXE_NAME and not relative.startswith("bin/"):
                continue
            target = destination / relative
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, target.open("wb") as out:
                    while chunk := src.read(1024 * 1024):
                        core.check_cancel(cancel)
                        out.write(chunk)
        if (destination / EXE_NAME).stat().st_size == 0:
            raise UpdateError("실행 파일이 비어 있습니다.")


def supported() -> bool:
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"


def prepare(release: Release, cancel: threading.Event, progress: Callable[[str], None]) -> Path:
    if not supported():
        raise UpdateError("소스 실행에서는 자동 교체 대신 릴리스 ZIP을 이용해 주세요.")
    work = Path(core.app_dir()) / WORK_NAME
    if work.exists():
        raise UpdateError("이전 업데이트 작업 폴더가 남아 있습니다. 앱을 다시 실행한 뒤 시도해 주세요.")
    work.mkdir()
    try:
        package = work / "package.zip"
        download(release, package, cancel, progress)
        progress("SHA-256 확인 완료 · 압축 검사 중")
        extract(package, work / "new", cancel)
        core.check_cancel(cancel)
        return work
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise


def launch_apply(work: Path) -> None:
    proc = subprocess.Popen([str(work / "new" / EXE_NAME), "--apply-update", str(os.getpid()),
                             str(Path(core.app_dir()).resolve())], cwd=work / "new",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
    # 업데이터가 실행 차단 서버를 확보한 뒤에만 부모를 끝내어 교체 중 재실행 경쟁을 막는다.
    from PyQt6.QtNetwork import QLocalSocket
    for _ in range(30):
        sock = QLocalSocket()
        sock.connectToServer(UPDATE_SERVER)
        if sock.waitForConnected(100):
            sock.disconnectFromServer()
            return
        if proc.poll() is not None:
            break
        threading.Event().wait(0.1)
    if proc.poll() is None:
        proc.terminate()
        proc.wait()
    raise OSError("업데이트 적용 프로세스가 응답하지 않습니다.")


def previous_result() -> str:
    """교체 결과를 전달한다. 실행 중인 업데이터의 파일은 다음 실행 때 정리된다."""
    if not supported():
        return ""
    work = Path(core.app_dir()) / WORK_NAME
    if not work.exists():
        return ""
    try:
        result = json.loads((work / "result.json").read_text(encoding="utf-8"))
        message = "업데이트를 완료했습니다." if result.get("ok") else "업데이트를 적용하지 못해 이전 버전으로 복원했습니다. " + str(result.get("error", ""))
        shutil.rmtree(work, ignore_errors=True)
        return message
    except (OSError, ValueError):
        if not (work / "backup").exists():
            shutil.rmtree(work, ignore_errors=True)
            return "이전 업데이트 준비가 중단되어 임시 파일을 정리했습니다. 다시 시도해 주세요."
        return "이전 업데이트가 중단되었습니다. update-workspace/backup의 기존 파일을 확인해 주세요."
