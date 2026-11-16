"""진입점: 인자가 있으면 CLI로, 없으면 GUI로 실행한다."""
import argparse
import sys


def cli(argv):
    from steamslice import core
    ap = argparse.ArgumentParser(prog="python -m steamslice", description="GIF 또는 동영상의 구간을 스팀 전시대용 5조각으로 자릅니다.")
    ap.add_argument("src")
    ap.add_argument("--out")
    ap.add_argument("--start", type=float, help="동영상 구간의 시작(초)")
    ap.add_argument("--end", type=float, help="동영상 구간의 끝(초)")
    ap.add_argument("--fps", type=int, default=25, choices=[25, 20, 10])
    a = ap.parse_args(argv)
    clip = (a.start or 0.0, a.end, a.fps) if a.end is not None else None
    try:
        r = core.run(a.src, a.out, on_progress=lambda s: print("[" + s + "]", flush=True), clip=clip)
    except core.SliceError as e:
        print("오류: " + str(e))
        return 1
    for i, (f, s) in enumerate(zip(r.files, r.sizes), 1):
        print(f"{i}번 {s / 1e6:.2f}MB  {f}")
    print(f"완료: {r.frames}프레임, {r.total_ms}ms, {core.compression_summary(r)}, {r.seconds:.1f}초")
    return 0


def main():
    if sys.argv[1:2] == ["--apply-update"]:
        from steamslice import apply_update
        return apply_update.main(sys.argv[2:])
    if sys.argv[1:2] == ["--version"]:
        from steamslice import __version__
        print(__version__)
        return 0
    if len(sys.argv) > 1:
        return cli(sys.argv[1:])
    from steamslice import ui
    return ui.main()


if __name__ == "__main__":
    sys.exit(main())
