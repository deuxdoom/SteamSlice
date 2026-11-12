"""Windows의 이름 있는 mutex로 프로세스 시작 경쟁을 막는다."""
import ctypes
from ctypes import wintypes
import os


class InstanceLock:
    def __init__(self, name: str):
        self.handle = None
        self.acquired = True
        if os.name == "nt":
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            self.kernel.CreateMutexW.restype = wintypes.HANDLE
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = self.kernel.CreateMutexW(None, False, "Local\\" + name)
            error = ctypes.get_last_error()
            if not self.handle:
                raise OSError(error, "실행 소유권을 확인할 수 없습니다.")
            self.acquired = error != 183

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
