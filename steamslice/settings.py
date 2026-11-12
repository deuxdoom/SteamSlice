"""레지스트리 없이 프로그램 옆에 저장하는 사용자 설정."""
import json
import os
import sys
from pathlib import Path

from steamslice import core


def path() -> Path:
    base = Path(core.app_dir())
    return base / "settings.json" if getattr(sys, "frozen", False) else base / ".local" / "settings.json"


def load() -> dict:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict) -> None:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)
