"""확인한 Fluent SVG 원본으로 앱용 컬러 PNG를 만든다. 새 런타임 의존성은 없다."""
import os
from pathlib import Path
import re
import sys

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
ICONS = {"settings": ("#bca6ff", "#7654bd"), "info": ("#66cbf4", "#0078a6"),
         "minimize": ("#9cacc2", "#596d83"), "restore": ("#66cbf4", "#0078a6"),
         "update": ("#a3db72", "#397b18"), "exit": ("#ff8f87", "#c32d3d"),
         "file": ("#66cbf4", "#0078a6"), "folder": ("#f4c96b", "#956500"),
         "copy": ("#bca6ff", "#7654bd"), "upload": ("#a3db72", "#397b18"),
         "cut": ("#0b1220", "#ffffff"), "github": ("#d6dee8", "#25354a"),
         "check": ("#0b1220", "#ffffff"), "caret-up": ("#d6dee8", "#25354a"),
         "caret-down": ("#d6dee8", "#25354a")}


def main():
    app = QApplication(sys.argv)
    target = ROOT / "assets" / "icons"
    for name, colors in ICONS.items():
        svg = (target / f"{name}.svg").read_text(encoding="utf-8")
        for theme, color in zip(("dark", "light"), colors):
            colored = re.sub(r'fill="(?!none)[^"]+"', f'fill="{color}"', svg)
            if 'fill="' not in colored:
                colored = colored.replace("<svg ", f'<svg fill="{color}" ', 1)
            image = QImage(48, 48, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            QSvgRenderer(QByteArray(colored.encode())).render(painter)
            painter.end()
            if not image.save(os.fspath(target / f"{name}-{theme}.png")):
                raise OSError("아이콘 저장 실패")
    app.quit()


if __name__ == "__main__":
    main()
