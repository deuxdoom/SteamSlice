"""bin 구조 빌드 후 배포 ZIP, SHA-256 및 로컬 릴리스 본문을 갱신한다."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from steamslice import __version__, updater


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-only", action="store_true")
    args = parser.parse_args()
    if not args.package_only:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--workpath", ".local/build",
                        "--distpath", "dist", "SteamSlice.spec"], cwd=ROOT, check=True)
    app = ROOT / "dist" / "SteamSlice"
    if not (app / updater.EXE_NAME).is_file() or not (app / "bin").is_dir() or (app / "_internal").exists():
        raise RuntimeError("SteamSlice.exe + bin 구조로 먼저 빌드해 주세요.")
    name = updater.asset_name(__version__)
    target = ROOT / "dist" / name
    # 사용자 설정·결과·시험 로그가 배포 파일에 들어가지 않도록 exe와 bin만 포장한다.
    files = [app / updater.EXE_NAME, *sorted(p for p in (app / "bin").rglob("*") if p.is_file())]
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, "SteamSlice/" + path.relative_to(app).as_posix())
    with target.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest().upper()
    (target.parent / (name + ".sha256")).write_text(f"{digest}  {name}\n", encoding="utf-8")
    release_path = ROOT / "Release.md"
    if release_path.exists():
        body = release_path.read_text(encoding="utf-8")
        body = re.sub(r"(?<=\n)[0-9A-Fa-f]{64}(?=\n)|SHA256_PLACEHOLDER", digest, body)
        release_path.write_text(body, encoding="utf-8")
    print(f"{target}\nSHA-256: {digest}")


if __name__ == "__main__":
    main()
