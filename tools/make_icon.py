"""로고 원본(assets/steamslice.svg)에서 PNG와 ICO를 만든다. 로고를 수정한 뒤에 한 번 실행한다.

- assets/steamslice.png (512px): 프로그램이 창 아이콘과 화면 상단의 로고로 사용한다.
- assets/steamslice.ico (16~256px): 실행 파일의 아이콘으로 사용한다.
- assets/social-preview.png (1280×640): GitHub 저장소의 소셜 프리뷰 카드. 원본은 assets/social-preview.svg이다.
- assets/spin-up.png, spin-down.png: 시각/압축 입력의 위·아래 화살표.
"""
import os
import struct
import sys

from PyQt6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPolygonF
from PyQt6.QtSvg import QSvgRenderer

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
PNG_SIZE = 512


def render(renderer, width, height=0):
    height = height or width
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    return image


def png_bytes(image):
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data().data())


def make_spin_arrows():
    """Qt SVG 플러그인 없이도 배포본에 선명한 증감 화살표를 표시한다."""
    for name, points in (("spin-up.png", ((2, 10), (8, 3), (14, 10))),
                         ("spin-down.png", ((2, 2), (8, 9), (14, 2)))):
        image = QImage(16, 12, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#d6dee8"))
        painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
        painter.end()
        image.save(os.path.join(ASSETS, name), "PNG")


def main():
    app = QGuiApplication(sys.argv[:1])
    make_spin_arrows()
    renderer = QSvgRenderer(os.path.join(ASSETS, "steamslice.svg"))
    if not renderer.isValid():
        print("steamslice.svg를 읽을 수 없습니다.")
        return 1

    png = os.path.join(ASSETS, "steamslice.png")
    render(renderer, PNG_SIZE).save(png, "PNG")

    images = [png_bytes(render(renderer, s)) for s in ICO_SIZES]
    ico = os.path.join(ASSETS, "steamslice.ico")
    offset = 6 + 16 * len(ICO_SIZES)
    with open(ico, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(ICO_SIZES)))
        for size, data in zip(ICO_SIZES, images):
            f.write(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
            offset += len(data)
        for data in images:
            f.write(data)
    print(png)
    print(ico)

    card = QSvgRenderer(os.path.join(ASSETS, "social-preview.svg"))
    if card.isValid():
        out = os.path.join(ASSETS, "social-preview.png")
        render(card, 1280, 640).save(out, "PNG")
        print(out)
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
