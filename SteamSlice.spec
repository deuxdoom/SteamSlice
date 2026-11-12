# -*- mode: python ; coding: utf-8 -*-
# 빌드 명령은 AGENTS.md를 따른다. 작업 폴더는 프로젝트 내부 .local/build를 사용한다.

a = Analysis(
    ['steamslice/__main__.py'],
    pathex=['.'],
    # ffmpeg.exe는 동영상 기능에 필요하다. 용량이 커서 저장소에는 넣지 않으므로, 빌드 전에 tools 폴더에 넣어 둔다.
    binaries=[('tools/gifsicle.exe', '.'), ('tools/ffmpeg.exe', '.')],
    datas=[('assets/steamslice.png', 'assets'), ('assets/icons/*.png', 'assets/icons'),
           ('THIRD_PARTY_NOTICES.md', '.'), ('assets/icons/*LICENSE*', 'licenses')],
    hiddenimports=[],
    excludes=['PIL', 'tkinter', 'numpy', 'PyQt6.QtPdf', 'PyQt6.QtSvg', 'PyQt6.QtQml', 'PyQt6.QtQuick',
              'PyQt6.QtOpenGL', 'PyQt6.QtSql', 'PyQt6.QtTest', 'PyQt6.QtMultimedia'],
    noarchive=False,
)
# 사용하지 않는 Qt 구성 요소를 제외하여 배포 용량을 줄인다. QtNetwork는 중복 실행 방지에, qjpeg는 동영상 화면 표시에 필요하므로 남긴다.
DROP = ('opengl32sw', 'Qt6Pdf', 'Qt6Svg', 'translations', 'qpdf', 'qsvg', 'qtiff', 'qwebp', 'qicns',
        'qtga', 'qwbmp', 'qtuiotouchplugin', 'qoffscreen', 'qminimal')
a.binaries = [b for b in a.binaries if not any(k in b[0] for k in DROP)]
a.datas = [d for d in a.datas if not any(k in d[0] for k in DROP)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SteamSlice',
    contents_directory='bin',
    icon='assets/steamslice.ico',
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name='SteamSlice')
