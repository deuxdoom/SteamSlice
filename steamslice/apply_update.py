"""검증해 둔 새 실행 파일이 기존 프로세스 종료 후 exe/bin을 교체한다."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Callable

from steamslice import updater
from steamslice.instance import InstanceLock


def wait_for_pid(pid: int, timeout: float = 60) -> None:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return
        raise OSError(ctypes.get_last_error(), "기존 프로세스를 확인하지 못했습니다.")
    try:
        if kernel.WaitForSingleObject(handle, int(timeout * 1000)) != 0:
            raise OSError("기존 프로그램이 종료되지 않아 교체를 중단했습니다.")
    finally:
        kernel.CloseHandle(handle)


def retry(operation: Callable[[], object]) -> None:
    for attempt in range(20):
        try:
            operation()
            return
        except OSError:
            if attempt == 19:
                raise
            time.sleep(0.25)


def replace_payload(app: Path, work: Path, launch: Callable[[Path], None]) -> dict:
    """두 항목만 교체하고, 실패한 단계까지 되돌린다. 설정과 결과 폴더는 보존한다."""
    backup = work / "backup"
    backup.mkdir(exist_ok=False)
    moved: list[str] = []
    installed: list[str] = []
    try:
        for name in (updater.EXE_NAME, "bin"):
            retry(lambda name=name: os.replace(app / name, backup / name))
            moved.append(name)
        for name in (updater.EXE_NAME, "bin"):
            installed.append(name)
            if name == "bin":
                shutil.copytree(work / "new" / name, app / name)
            else:
                shutil.copy2(work / "new" / name, app / name)
        result = {"ok": True}
        (work / "result.json").write_text(json.dumps(result), encoding="utf-8")
        launch(app / updater.EXE_NAME)
        return result
    except OSError as exc:
        for name in reversed(installed):
            target = app / name
            if target.is_dir():
                retry(lambda target=target: shutil.rmtree(target))
            else:
                retry(lambda target=target: target.unlink(missing_ok=True))
        for name in reversed(moved):
            retry(lambda name=name: os.replace(backup / name, app / name))
        result = {"ok": False, "error": str(exc)}
        (work / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        launch(app / updater.EXE_NAME)
        return result


def main(argv: list[str]) -> int:
    if not updater.supported() or len(argv) != 2:
        return 2
    app, current = Path(argv[1]).resolve(), Path(sys.executable).resolve()
    work = app / updater.WORK_NAME
    try:
        pid = int(argv[0])
        if (pid <= 0 or current != work / "new" / updater.EXE_NAME
                or not (app / updater.EXE_NAME).is_file() or not (app / "bin").is_dir()
                or app.is_symlink() or work.is_symlink()):
            return 2
        # 교체 중에는 일반 실행이 기존/부분 복사된 파일을 열지 않도록 별도 서버를 유지한다.
        from PyQt6.QtCore import QCoreApplication
        from PyQt6.QtNetwork import QLocalServer
        qt_app = QCoreApplication(sys.argv)
        guard = InstanceLock(updater.UPDATE_SERVER)
        if not guard.acquired:
            guard.close()
            return 3
        server = QLocalServer(qt_app)
        if not server.listen(updater.UPDATE_SERVER):
            return 3
        wait_for_pid(pid)

        def launch(exe: Path) -> None:
            server.close()
            subprocess.Popen([str(exe)], cwd=app, close_fds=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

        replace_payload(app, work, launch)
        return 0
    except (OSError, ValueError) as exc:
        # 복원도 실패하면 백업을 남기고, 콘솔 없는 배포본에서도 원인을 표시한다.
        ctypes.windll.user32.MessageBoxW(None, f"업데이트를 완료할 수 없습니다.\n{exc}\n백업: {work / 'backup'}", "SteamSlice", 0x10)
        return 1
