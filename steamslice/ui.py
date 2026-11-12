"""메인 창, 작업 스레드, 중복 실행 방지."""
import os
import sys
import threading

from PyQt6.QtCore import QEvent, QMimeData, QPointF, QRectF, QSize, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QDrag, QFont, QIcon, QImage, QMovie, QPainter, QPalette, QPixmap
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
                             QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QScrollArea,
                             QSizePolicy, QSpinBox, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from steamslice import REPO_URL, __version__, core, settings, steam, updater, video
from steamslice.instance import InstanceLock

APP_NAME = core.APP_ID
SERVER_NAME = core.APP_ID + ".single-instance"
TAGLINE = "GIF나 동영상의 한 구간을 스팀 프로필 전시대의 다섯 조각으로"
DEFAULT_CLIP_SECONDS = 6.0   # 동영상을 넣었을 때 처음 선택되는 구간의 길이
UNOFFICIAL = "Valve 및 Steam과 관련이 없는 비공식 도구입니다."
BRAND_FROM = "#4fd1ff"   # 강조색(시안). 로고의 색은 assets/steamslice.svg에 정의되어 있다.

QSS = """
* { font-family: 'Malgun Gothic', 'Segoe UI'; font-size: 13px; color: #d6dee8; }
#root, QDialog, QMessageBox, QMenu { background: #12161d; }
QToolTip { color: #d6dee8; background: #1a2230; border: 1px solid #3d4f63; padding: 6px; }
QMenu { border: 1px solid #263447; padding: 6px; }
QMenu::item { padding: 9px 28px 9px 12px; border-radius: 4px; }
QMenu::item:selected { background: #33475f; }
QMenu::separator { height: 1px; background: #263447; margin: 5px; }
QCheckBox { spacing: 10px; padding: 6px 0; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #3d4f63; background: #202a38; }
QCheckBox::indicator:checked { image: url("@CHECK@"); background: #4fd1ff; border-color: #4fd1ff; }
QComboBox QAbstractItemView { background: #202a38; selection-background-color: #33475f; }
QPushButton:focus-visible { border: 1px solid #4fd1ff; }
#toolbar { padding: 7px 10px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #1a2230; width: 8px; }
QScrollBar::handle:vertical { background: #263447; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
#title { font-size: 22px; font-weight: 700; color: #ffffff; }
#sub, #hint { color: #8a95a3; }
#panel { background: #1a2230; border: 1px solid #263447; border-radius: 10px; }
#section { font-size: 15px; font-weight: 600; color: #ffffff; }
#status { color: #8a95a3; background: #1a2230; border-radius: 6px; padding: 6px 12px; }
#status[error="true"] { color: #ff7b72; }
#notice { color: #9bd64a; }
QPushButton { background: #263447; border: none; border-radius: 6px; padding: 9px 14px; }
QPushButton:hover { background: #33475f; }
QPushButton:disabled { background: #202a38; color: #5c6670; }
#primary { background: #4fd1ff; color: #0b1220; font-size: 15px; font-weight: 600; padding: 10px; }
#primary:hover { background: #8be2ff; }
#primary:disabled { background: #223042; color: #5c6670; }
#link { background: transparent; color: #8a95a3; padding: 4px; text-align: left; }
#link:hover { color: #ffffff; }
#chip { background: #202a38; border-radius: 6px; padding: 8px 4px; color: #d6dee8; }
#chip:hover { background: #2a3850; }
#chip:disabled { color: #8a95a3; }
#done { font-weight: 600; color: #8a95a3; }
#done[ready="true"] { color: #9bd64a; }
#path { color: #ffffff; }
#rule { background: #263447; max-height: 1px; }
QSpinBox, QDoubleSpinBox, QComboBox { background: #202a38; border: 1px solid #263447; border-radius: 4px; padding: 4px; }
QSpinBox, QDoubleSpinBox { padding-right: 26px; min-height: 24px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 24px; height: 16px; border-left: 1px solid #3d4f63; border-bottom: 1px solid #3d4f63; background: #263447; border-top-right-radius: 4px; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; height: 16px; border-left: 1px solid #3d4f63; background: #263447; border-bottom-right-radius: 4px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover { background: #33475f; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("@SPIN_UP@"); width: 10px; height: 7px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("@SPIN_DOWN@"); width: 10px; height: 7px; }
"""


def asset_path(name):
    """assets 폴더의 파일 경로. 빌드된 실행 파일에서는 포함된 자료 폴더에서 찾는다."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


QSS = QSS.replace("@SPIN_UP@", asset_path("icons/caret-up-dark.png").replace("\\", "/")).replace(
    "@SPIN_DOWN@", asset_path("icons/caret-down-dark.png").replace("\\", "/")).replace(
    "@CHECK@", asset_path("icons/check-dark.png").replace("\\", "/"))

LIGHT_COLORS = {"#d6dee8": "#25354a", "#12161d": "#f4f7fb", "#1a2230": "#ffffff",
                "#263447": "#dce5ef", "#ffffff": "#172b43", "#8a95a3": "#596d83",
                "#ff7b72": "#c32d3d", "#9bd64a": "#397b18", "#33475f": "#cbdceb",
                "#202a38": "#eaf0f7", "#5c6670": "#65758a", "#4fd1ff": "#0078a6",
                "#0b1220": "#ffffff", "#8be2ff": "#00688f", "#223042": "#dde6ef",
                "#2a3850": "#d7e7f3", "#3d4f63": "#8c9fb3"}


def theme_color(color: str) -> QColor:
    app = QApplication.instance()
    return QColor(LIGHT_COLORS.get(color, color) if app and app.property("theme") == "light" else color)


def apply_theme(theme: str) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    app.setProperty("theme", theme)
    light = theme == "light"
    import re
    qss = re.sub(r"#[0-9a-fA-F]{6}", lambda m: LIGHT_COLORS.get(m[0], m[0]), QSS) if light else QSS
    if light:
        for name in ("check", "caret-up", "caret-down"):
            qss = qss.replace(f"{name}-dark.png", f"{name}-light.png")
    app.setStyleSheet(qss)
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, "#12161d"), (QPalette.ColorRole.WindowText, "#d6dee8"),
                        (QPalette.ColorRole.Base, "#202a38"), (QPalette.ColorRole.Text, "#d6dee8"),
                        (QPalette.ColorRole.Button, "#263447"), (QPalette.ColorRole.ButtonText, "#d6dee8"),
                        (QPalette.ColorRole.Highlight, BRAND_FROM), (QPalette.ColorRole.HighlightedText, "#0b1220")):
        palette.setColor(role, theme_color(color))
    app.setPalette(palette)
    hints = app.styleHints()
    if hints:
        hints.setColorScheme(Qt.ColorScheme.Light if light else Qt.ColorScheme.Dark)
    for widget in app.allWidgets():
        widget.update()


def icon(name: str) -> QIcon:
    app = QApplication.instance()
    theme = "light" if app and app.property("theme") == "light" else "dark"
    return QIcon(asset_path(f"icons/{name}-{theme}.png"))


class UpdateTask(QThread):
    stage = pyqtSignal(str)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, release: updater.Release | None = None):
        super().__init__()
        self.release = release
        self.cancel = threading.Event()

    def run(self):
        try:
            result = (updater.prepare(self.release, self.cancel, self.stage.emit) if self.release
                      else updater.fetch_latest())
            if not self.cancel.is_set():
                self.done.emit(result)
        except core.Cancelled:
            pass
        except Exception as exc:
            self.failed.emit(str(exc))


class MediaLoader(QThread):
    done = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.cancel = threading.Event()

    def run(self):
        try:
            info = video.probe(self.path, self.cancel) if video.is_video(self.path) else core.probe(self.path, self.cancel)
            self.done.emit(self.path, info)
        except core.Cancelled:
            pass
        except Exception as exc:
            self.failed.emit(str(exc))


def logo_pixmap(size):
    """로고 이미지(assets/steamslice.png)를 지정한 크기로 반환한다. 원본은 assets/steamslice.svg이다."""
    return QPixmap(asset_path("steamslice.png")).scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def repolish(widget):
    """동적 속성을 바꾼 뒤에 스타일을 다시 적용한다."""
    style = widget.style()
    if style:
        style.unpolish(widget)
        style.polish(widget)


class PathLabel(QLabel):
    """긴 경로는 폭에 맞춰 줄이고, 전체 값은 도움말과 복사로 확인한다."""

    def __init__(self):
        super().__init__()
        self.full_text = ""
        self.setObjectName("path")
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setMinimumWidth(0)
        self.setFixedHeight(self.fontMetrics().height() + 4)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def setText(self, a0):
        self.full_text = a0 or ""
        self.setToolTip(self.full_text)
        self.elide()

    def elide(self):
        super().setText(self.fontMetrics().elidedText(
            self.full_text, Qt.TextElideMode.ElideMiddle, max(0, self.width())))

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self.elide()


class Worker(QThread):
    stage = pyqtSignal(str)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, src, out_dir, lossy, clip):
        super().__init__()
        self.src, self.out_dir, self.lossy, self.clip = src, out_dir, lossy, clip
        self.cancel = threading.Event()

    def run(self):
        try:
            self.done.emit(core.run(self.src, self.out_dir, on_progress=self.stage.emit,
                                    cancel=self.cancel, lossy_start=self.lossy, clip=self.clip))
        except core.Cancelled:
            self.cancelled.emit()
        except core.SliceError as e:
            self.failed.emit(str(e))
        except Exception as e:  # 예상하지 못한 오류도 화면에 표시한다
            self.failed.emit(f"예상하지 못한 오류가 발생했습니다: {e}")


class FrameGrabber(QThread):
    """동영상의 특정 시각의 화면을 백그라운드에서 읽는다. 요청이 밀리면 가장 최근의 요청만 처리한다."""
    frame = pyqtSignal(str, bytes)   # (동영상 경로, JPEG 바이트)

    def __init__(self):
        super().__init__()
        self.cond = threading.Condition()
        self.request: tuple[str, float, threading.Event] | None = None
        self.cancel = threading.Event()
        self.closing = False

    def ask(self, path, ts):
        with self.cond:
            self.cancel.set()
            self.cancel = threading.Event()
            self.request = (path, ts, self.cancel)
            self.cond.notify()
        if not self.isRunning() and not self.closing:
            self.start()

    def stop(self):
        with self.cond:
            self.closing = True
            self.cancel.set()
            self.request = None
            self.cond.notify()

    def close(self):
        self.stop()
        self.wait()

    def run(self):
        while True:
            with self.cond:
                while self.request is None and not self.closing:
                    self.cond.wait()
                if self.closing:
                    return
                req, self.request = self.request, None
            if req is None:
                continue
            try:
                data = video.grab_frame(req[0], req[1], cancel=req[2])
                if not req[2].is_set():
                    self.frame.emit(req[0], data)
            except (core.SliceError, core.Cancelled):
                pass   # 화면을 읽지 못하면 이전 화면을 그대로 둔다


class RangeBar(QWidget):
    """시작은 위, 끝은 아래 손잡이로 조절하고 가운데 선택 영역을 끌어 이동한다."""
    changed = pyqtSignal(float)   # 방금 움직인 손잡이의 시각(초)
    PAD = 24

    def __init__(self):
        super().__init__()
        self.duration, self.start, self.end = 1.0, 0.0, 1.0
        self.active = ""
        self.grab_offset = 0.0
        self.drag_x, self.drag_start, self.drag_end = 0.0, 0.0, 1.0
        self.setFixedHeight(62)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setToolTip("위쪽 '시작'과 아래쪽 '끝' 손잡이로 구간을 조절합니다. 가운데 선택 막대를 끌면 길이를 유지하며 이동합니다.")

    def set_range(self, duration, start, end):
        self.duration, self.start, self.end = max(duration, 0.001), start, end
        self.update()

    def _x(self, t):
        return self.PAD + (self.width() - 2 * self.PAD) * t / self.duration

    def handle_rect(self, which):
        t = self.start if which == "start" else self.end
        return QRectF(self._x(t) - 20, 0 if which == "start" else 40, 40, 22)

    def in_selection(self, x, y):
        return self._x(self.start) - 6 <= x <= self._x(self.end) + 6 and abs(y - self.height() / 2) <= 9

    def _move(self, x):
        if self.active == "range":
            delta = (x - self.drag_x) / max(1, self.width() - 2 * self.PAD) * self.duration
            delta = max(-self.drag_start, min(self.duration - self.drag_end, delta))
            self.start, self.end = self.drag_start + delta, self.drag_end + delta
            self.update()
            self.changed.emit(self.start)
            return
        t = (x - self.PAD) / max(1, self.width() - 2 * self.PAD) * self.duration
        t = max(0.0, min(self.duration, t))
        lo, hi = video.MIN_CLIP_SECONDS, video.MAX_CLIP_SECONDS
        if self.active == "start":
            self.start = min(t, self.end - lo)
            self.end = min(self.end, self.start + hi)
        else:
            self.end = max(t, self.start + lo)
            self.start = max(self.start, self.end - hi)
        self.update()
        self.changed.emit(self.start if self.active == "start" else self.end)

    def mousePressEvent(self, a0):
        if a0 is None or a0.button() != Qt.MouseButton.LeftButton:
            return
        point = a0.position()
        x, y = point.x(), point.y()
        self.grab_offset = 0.0
        for which in ("start", "end"):
            if self.handle_rect(which).contains(point):
                self.active = which
                self.grab_offset = x - self._x(self.start if which == "start" else self.end)
                self.update()
                return
        if self.in_selection(x, y):
            self.active = "range"
            self.drag_x, self.drag_start, self.drag_end = x, self.start, self.end
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        self.active = "start" if abs(x - self._x(self.start)) <= abs(x - self._x(self.end)) else "end"
        self._move(x)

    def mouseMoveEvent(self, a0):
        if a0 is None:
            return
        if self.active:
            self._move(a0.position().x() - self.grab_offset)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor if self.in_selection(
                a0.position().x(), a0.position().y()) else Qt.CursorShape.SizeHorCursor)

    def mouseReleaseEvent(self, a0):
        self.active = ""
        self.grab_offset = 0.0
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.update()

    def paintEvent(self, a0):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        mid = self.height() / 2
        p.setBrush(theme_color("#202a38"))
        p.drawRoundedRect(QRectF(self.PAD, mid - 4, self.width() - 2 * self.PAD, 8), 4, 4)
        x0, x1 = self._x(self.start), self._x(self.end)
        p.setBrush(theme_color(BRAND_FROM))
        p.drawRoundedRect(QRectF(x0, mid - 4, max(1.0, x1 - x0), 8), 4, 4)
        p.setPen(theme_color(BRAND_FROM))
        p.drawLine(QPointF(x0, 22), QPointF(x0, mid))
        p.drawLine(QPointF(x1, mid), QPointF(x1, 40))
        for which, text in (("start", "시작"), ("end", "끝")):
            p.setBrush(theme_color(BRAND_FROM) if self.active == which else theme_color("#263447"))
            p.setPen(theme_color(BRAND_FROM))
            p.drawRoundedRect(self.handle_rect(which).adjusted(1, 1, -1, -1), 4, 4)
            p.setPen(theme_color("#0b1220") if self.active == which else theme_color("#ffffff"))
            p.drawText(self.handle_rect(which), Qt.AlignmentFlag.AlignCenter, text)


class Preview(QWidget):
    """GIF를 재생하면서 5분할 경계와 조각 번호를 겹쳐 그린다. 누르면 파일 선택 창을 연다."""
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.movie: QMovie | None = None
        self.still: QImage | None = None    # 동영상의 한 장면
        self.setMinimumHeight(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_still(self, image):
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        self.still = image
        self.update()

    def load(self, path, width=960, height=540):
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
        self.still = None
        self.movie = QMovie(path, parent=self)
        if width > 960:
            self.movie.setScaledSize(QSize(960, max(1, height * 960 // width)))
        self.movie.setCacheMode(QMovie.CacheMode.CacheNone)
        self.movie.frameChanged.connect(self.update)
        self.movie.start()

    def mouseReleaseEvent(self, a0):
        self.clicked.emit()

    def paintEvent(self, a0):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        img = self.movie.currentImage() if self.movie else self.still
        if img is None or img.isNull():
            p.setPen(theme_color("#3d4f63"))
            p.setBrush(theme_color("#1a2230"))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 10, 10)
            p.setPen(theme_color("#8a95a3"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "GIF 또는 동영상을 끌어다 놓으세요\n누르면 파일을 선택할 수 있습니다")
            return
        scale = min(r.width() / img.width(), r.height() / img.height())
        w, h = img.width() * scale, img.height() * scale
        x0, y0 = (r.width() - w) / 2, (r.height() - h) / 2
        p.drawImage(QRectF(x0, y0, w, h), img)
        unit = w / core.TOTAL_W
        f = QFont(self.font())
        f.setBold(True)
        p.setFont(f)
        for i in range(core.N):
            left = x0 + i * (core.SLICE_W + core.GAP) * unit
            if i:
                p.fillRect(QRectF(left - core.GAP * unit, y0, core.GAP * unit, h), QColor(0, 0, 0, 220))
            tag = QRectF(left + 6, y0 + 6, 24, 22)
            p.fillRect(tag, QColor(0, 0, 0, 150))
            p.setPen(QColor("#ffffff"))
            p.drawText(tag, Qt.AlignmentFlag.AlignCenter, str(i + 1))


class DragLabel(QLabel):
    """조각 파일 하나를 나타내는 칸. 누르면 탐색기에서 파일을 보여주고, 끌면 다른 창에 파일을 놓을 수 있다."""
    clicked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.path = ""
        self.dragged = False
        self.setObjectName("chip")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(48)
        self.setToolTip("누르면 탐색기에서 파일을 보여줍니다. 끌어서 브라우저의 파일 선택 칸에 놓을 수도 있습니다.")

    def mousePressEvent(self, ev):
        self.dragged = False

    def mouseMoveEvent(self, ev):
        if self.path and ev and ev.buttons() & Qt.MouseButton.LeftButton and not self.dragged:
            self.dragged = True
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(self.path)])
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.CopyAction)

    def mouseReleaseEvent(self, ev):
        if self.path and not self.dragged:
            self.clicked.emit(self.path)


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.src = ""
        self.worker: Worker | None = None
        self.loader: MediaLoader | None = None
        self.update_task: UpdateTask | None = None
        self.pending_update = None
        self._closing = False
        self._closed = False
        self._tray_notice = False
        self.preferences = settings.load()
        self.icon_widgets: list[tuple[QPushButton | QAction, str]] = []
        self.settings_dialog: QDialog | None = None
        self.about_dialog: QDialog | None = None
        self.result: core.Result | None = None
        self.vinfo: video.VideoInfo | None = None   # 동영상을 넣었을 때만 값이 있다
        self.grabber = FrameGrabber()
        self.grabber.frame.connect(self.on_frame)
        self.out_parent = str(self.preferences.get("out_parent", ""))
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(asset_path("steamslice.png")))
        self.setAcceptDrops(True)
        screen = self.screen()
        available = screen.availableGeometry() if screen else None
        self.setMinimumSize(min(920, available.width() - 48) if available is not None else 920,
                            min(540, available.height() - 64) if available is not None else 540)
        self.resize(min(1120, available.width() - 48) if available is not None else 1120,
                    min(760, available.height() - 64) if available is not None else 760)
        self.build()
        self.build_tray()
        self.shutdown_timer = QTimer(self)
        self.shutdown_timer.setInterval(50)
        self.shutdown_timer.timeout.connect(self.poll_shutdown)
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(lambda: self.check_update(automatic=True))
        self.update_dest()
        self.refresh()

    def decorate(self, widget: QPushButton | QAction, name: str):
        widget.setIcon(icon(name))
        self.icon_widgets.append((widget, name))
        return widget

    def save_preferences(self):
        self.preferences["out_parent"] = self.out_parent
        try:
            settings.save(self.preferences)
        except OSError:
            self.say("설정을 저장할 수 없습니다. 프로그램 폴더의 쓰기 권한을 확인해 주세요.", error=True)

    def set_preference(self, key: str, value):
        self.preferences[key] = value
        if key == "theme":
            apply_theme(value)
            self.title_label.setText(f'Steam<span style="color:{theme_color(BRAND_FROM).name()}">Slice</span>')
            for widget, name in self.icon_widgets:
                widget.setIcon(icon(name))
        self.save_preferences()

    def build_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(f"SteamSlice {__version__}")
        self.tray_menu = QMenu(self)
        for text, name, callback in (("메인 창 복원", "restore", self.bring_to_front),
                                     ("설정", "settings", self.show_settings),
                                     ("프로그램 정보", "info", self.show_about),
                                     ("업데이트 확인", "update", self.check_update),
                                     ("GitHub 저장소", "github", self.open_repository)):
            action = QAction(text, self)
            self.decorate(action, name)
            action.triggered.connect(callback)
            self.tray_menu.addAction(action)
        self.tray_menu.addSeparator()
        self.quit_action = QAction("종료", self)
        self.decorate(self.quit_action, "exit")
        self.quit_action.triggered.connect(self.request_quit)
        self.tray_menu.addAction(self.quit_action)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.messageClicked.connect(self.bring_to_front)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.bring_to_front()

    def minimize_to_tray(self):
        if self.tray.isVisible() and not self._closing:
            self.hide()
            if not self._tray_notice:
                self.tray.showMessage(APP_NAME, "트레이에서 계속 실행합니다. 아이콘을 더블 클릭하면 복원됩니다.")
                self._tray_notice = True

    def changeEvent(self, a0):
        super().changeEvent(a0)
        if (a0 and a0.type() == QEvent.Type.WindowStateChange and self.isMinimized()
                and self.preferences.get("minimize_to_tray", True)):
            QTimer.singleShot(0, self.minimize_to_tray)

    def hideEvent(self, a0):
        super().hideEvent(a0)
        if self.preview.movie:
            self.preview.movie.setPaused(True)

    def showEvent(self, a0):
        super().showEvent(a0)
        if self.preview.movie:
            self.preview.movie.setPaused(False)

    @staticmethod
    def open_repository():
        QDesktopServices.openUrl(QUrl(REPO_URL))

    def show_settings(self):
        self.bring_to_front()
        if self.settings_dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("SteamSlice 설정")
            dialog.setMinimumWidth(420)
            lay = QVBoxLayout(dialog)
            lay.setContentsMargins(24, 24, 24, 24)
            lay.setSpacing(14)
            heading = QLabel("나에게 맞게 설정")
            heading.setObjectName("section")
            lay.addWidget(heading)
            row = QHBoxLayout()
            row.addWidget(QLabel("화면 테마"), 1)
            self.theme_combo = QComboBox()
            self.theme_combo.addItem("어두운 테마", "dark")
            self.theme_combo.addItem("밝은 테마", "light")
            self.theme_combo.setCurrentIndex(1 if self.preferences.get("theme") == "light" else 0)
            self.theme_combo.currentIndexChanged.connect(lambda: self.set_preference("theme", self.theme_combo.currentData()))
            row.addWidget(self.theme_combo)
            lay.addLayout(row)
            for text, key in (("최소화하면 트레이로 보내기", "minimize_to_tray"),
                              ("실행할 때 새 버전 자동 확인", "auto_update")):
                check = QCheckBox(text)
                check.setChecked(bool(self.preferences.get(key, True)))
                check.toggled.connect(lambda checked, key=key: self.set_preference(key, checked))
                lay.addWidget(check)
            hint = QLabel("설정은 바로 적용됩니다. 업데이트 설치는 확인 후 진행합니다.")
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            lay.addWidget(hint)
            self.update_button = QPushButton("업데이트 확인")
            self.decorate(self.update_button, "update")
            self.update_button.clicked.connect(self.check_update)
            lay.addWidget(self.update_button)
            self.update_label = QLabel(f"현재 버전 {__version__}")
            self.update_label.setObjectName("hint")
            self.update_label.setWordWrap(True)
            self.update_label.setTextFormat(Qt.TextFormat.PlainText)
            lay.addWidget(self.update_label)
            close = QPushButton("닫기")
            close.clicked.connect(dialog.close)
            lay.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
            self.settings_dialog = dialog
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def show_about(self):
        self.bring_to_front()
        if self.about_dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("SteamSlice 정보")
            dialog.setMinimumWidth(420)
            lay = QVBoxLayout(dialog)
            lay.setContentsMargins(24, 24, 24, 24)
            lay.setSpacing(14)
            mark = QLabel()
            mark.setPixmap(logo_pixmap(64))
            lay.addWidget(mark, alignment=Qt.AlignmentFlag.AlignCenter)
            title = QLabel(f"SteamSlice {__version__}")
            title.setObjectName("title")
            lay.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
            for text in (TAGLINE, UNOFFICIAL, "제작: deuxdoom\nPython · PyQt6 · Gifsicle · FFmpeg\n아이콘: Microsoft Fluent UI System Icons · GitHub Octicons"):
                label = QLabel(text)
                label.setWordWrap(True)
                label.setObjectName("hint")
                lay.addWidget(label)
            repository = QPushButton("GitHub 저장소")
            self.decorate(repository, "github")
            repository.clicked.connect(self.open_repository)
            lay.addWidget(repository)
            close = QPushButton("닫기")
            close.clicked.connect(dialog.close)
            lay.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
            self.about_dialog = dialog
        self.about_dialog.show()
        self.about_dialog.raise_()
        self.about_dialog.activateWindow()

    def check_update(self, checked=False, automatic=False):
        if self.update_task or self._closing:
            return
        if self.worker or self.loader:
            if not automatic:
                self.say("현재 작업이 끝난 뒤 업데이트를 확인해 주세요.")
            return
        self._automatic_update = automatic
        self.update_task = UpdateTask()
        self.update_task.done.connect(self.on_release)
        self.update_task.failed.connect(self.update_failed)
        self.update_task.start()
        if self.settings_dialog:
            self.update_label.setText("새 버전을 확인하는 중...")
        self.refresh()

    def clear_update_task(self):
        if self.update_task:
            self.update_task.wait()
            self.update_task.deleteLater()
            self.update_task = None
        self.refresh()

    def update_failed(self, message):
        self.clear_update_task()
        if self._closing:
            return
        if self.settings_dialog:
            self.update_label.setText(message)
        if not self._automatic_update:
            self.say(message, error=True)

    def on_release(self, release: updater.Release):
        self.clear_update_task()
        if self._closing:
            return
        if updater.version_tuple(release.version) <= updater.version_tuple(__version__):
            if self.settings_dialog:
                self.update_label.setText(f"최신 버전입니다 ({__version__}).")
            if not self._automatic_update:
                self.say(f"최신 버전입니다 ({__version__}).")
            return
        # 시작 자동 확인은 작업/트레이를 방해하지 않고 설정에서 설치하도록 알린다.
        if self._automatic_update:
            self.say(f"새 버전 {release.version}이 있습니다. 설정에서 업데이트할 수 있습니다.")
            if self.tray.isVisible():
                self.tray.showMessage(APP_NAME, f"새 버전 {release.version}이 있습니다. 설정에서 업데이트해 주세요.")
            return
        if not updater.supported():
            self.say(f"새 버전 {release.version}이 있습니다. 소스 실행은 GitHub에서 직접 업데이트해 주세요.")
            return
        if self.busy():
            self.say("현재 작업이 끝난 뒤 업데이트를 다시 확인해 주세요.")
            return
        answer = QMessageBox.question(self, "SteamSlice 업데이트", f"{__version__} → {release.version}\n새 버전을 받아 SHA-256 검사 후 설치하고 다시 실행할까요?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._automatic_update = False
        self.update_task = UpdateTask(release)
        self.update_task.stage.connect(self.say)
        self.update_task.done.connect(self.update_prepared)
        self.update_task.failed.connect(self.update_failed)
        self.update_task.start()
        self.refresh()

    def update_prepared(self, work):
        self.clear_update_task()
        if self._closing:
            return
        self.pending_update = work
        self.request_quit()

    # ---------- 화면 구성 ----------
    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(44))
        logo.setToolTip(UNOFFICIAL)
        title = QLabel(f'Steam<span style="color:{theme_color(BRAND_FROM).name()}">Slice</span>')
        self.title_label = title
        title.setObjectName("title")
        sub = QLabel(TAGLINE)
        sub.setObjectName("sub")
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(title)
        names.addWidget(sub)
        head.addWidget(logo)
        head.addLayout(names, 1)
        for text, name, callback in (("트레이", "minimize", self.minimize_to_tray),
                                     ("설정", "settings", self.show_settings),
                                     ("정보", "info", self.show_about)):
            button = QPushButton(text)
            button.setObjectName("toolbar")
            button.setToolTip(text)
            button.setAccessibleName(text)
            button.setIconSize(QSize(20, 20))
            button.clicked.connect(callback)
            self.decorate(button, name)
            head.addWidget(button)
        root.addLayout(head)

        # 두 작업 영역은 상태와 무관하게 자리를 유지한다. 작은 화면에서는 각 영역만 스크롤한다.
        columns = QHBoxLayout()
        columns.setSpacing(16)
        self.source_panel = QFrame()
        self.source_panel.setObjectName("panel")
        source = QVBoxLayout(self.source_panel)
        source.setContentsMargins(14, 12, 14, 12)
        source.setSpacing(8)
        source_head = QHBoxLayout()
        source_title = QLabel("01  원본 · 구간 설정")
        source_title.setObjectName("section")
        self.pick_btn = QPushButton("파일 선택")
        self.decorate(self.pick_btn, "file")
        self.pick_btn.clicked.connect(self.pick)
        source_head.addWidget(source_title, 1)
        source_head.addWidget(self.pick_btn)
        source.addLayout(source_head)

        self.preview = Preview()
        self.preview.clicked.connect(self.pick)
        source.addWidget(self.preview, 1)

        self.info = PathLabel()
        self.info.setObjectName("hint")
        self.info.setText("파일을 선택하면 크기와 재생 정보를 표시합니다.")
        source.addWidget(self.info)

        self.clip_stack = QStackedWidget()
        self.clip_stack.setFixedHeight(154)
        self.clip_hint = QLabel("GIF는 원본의 재생 시간을 그대로 사용합니다.\n동영상을 넣으면 여기에서 구간과 FPS를 정합니다.")
        self.clip_hint.setObjectName("hint")
        self.clip_hint.setWordWrap(True)
        self.clip_stack.addWidget(self.clip_hint)
        self.clip_stack.addWidget(self.build_clip())
        source.addWidget(self.clip_stack)

        adv = QHBoxLayout()
        advanced = QLabel("고급 설정")
        advanced.setObjectName("hint")
        self.adv_label = QLabel("압축 시작값")
        self.adv_label.setObjectName("hint")
        self.lossy = QSpinBox()
        self.lossy.setRange(0, core.LOSSY_MAX)
        self.lossy.setSingleStep(core.LOSSY_STEP)
        self.lossy.setValue(core.LOSSY_START)
        self.lossy.setToolTip("높을수록 용량이 작고 화질이 낮습니다. 5MB를 넘으면 자동으로 올립니다.")
        adv.addWidget(advanced)
        adv.addStretch(1)
        adv.addWidget(self.adv_label)
        adv.addWidget(self.lossy)
        source.addLayout(adv)
        columns.addWidget(self.scroll_panel(self.source_panel), 1)
        columns.addWidget(self.scroll_panel(self.build_upload()), 1)
        root.addLayout(columns, 1)

        self.status = QLabel("GIF 또는 동영상 파일을 선택하세요.")
        self.status.setObjectName("status")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setFixedHeight(48)
        root.addWidget(self.status)

    @staticmethod
    def scroll_panel(panel):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(panel)
        return scroll

    def build_actions(self, lay):
        """저장 위치와 생성 조작은 결과 유무와 관계없이 같은 위치에 둔다."""
        self.dest_label = PathLabel()
        self.dest_label.setObjectName("hint")
        self.dest_btn = QPushButton("저장 위치 변경")
        self.decorate(self.dest_btn, "folder")
        self.dest_btn.clicked.connect(self.pick_dest)
        dest = QHBoxLayout()
        dest.addWidget(QLabel("저장 위치"), 1)
        dest.addWidget(self.dest_btn)
        lay.addLayout(dest)
        lay.addWidget(self.dest_label)
        row = QHBoxLayout()
        self.go = QPushButton("5조각 만들기")
        self.decorate(self.go, "cut")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self.start)
        self.stop = QPushButton("취소")
        self.stop.clicked.connect(self.cancel)
        self.stop.setFixedWidth(70)
        row.addWidget(self.go, 1)
        row.addWidget(self.stop)
        lay.addLayout(row)

    def build_clip(self):
        """동영상 구간 선택 영역. 동영상을 넣었을 때만 표시한다."""
        self.clip_box = QWidget()
        lay = QVBoxLayout(self.clip_box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.bar = RangeBar()
        self.bar.changed.connect(self.on_bar)
        lay.addWidget(self.bar)
        hint = QLabel("선택 막대를 끌어 구간 이동 · 위쪽은 시작, 아래쪽은 끝")
        hint.setObjectName("hint")
        lay.addWidget(hint)

        row = QHBoxLayout()
        self.s_start = QDoubleSpinBox()
        self.s_end = QDoubleSpinBox()
        for spin, name in ((self.s_start, "시작"), (self.s_end, "끝")):
            spin.setDecimals(2)
            spin.setSingleStep(0.1)
            spin.setSuffix(" 초")
            spin.setFixedWidth(112)
            spin.valueChanged.connect(self.on_spin)
            row.addWidget(QLabel(name))
            row.addWidget(spin)
        self.clip_label = QLabel("")
        self.clip_label.setObjectName("hint")
        lay.addWidget(self.clip_label)
        row.addStretch(1)
        row.addWidget(QLabel("FPS"))
        self.fps = QComboBox()
        for f in video.FPS_CHOICES:
            self.fps.addItem(str(f), f)
        self.fps.currentIndexChanged.connect(self.sync_clip)
        row.addWidget(self.fps)
        lay.addLayout(row)
        return self.clip_box

    def dest(self):
        """조각을 저장할 폴더. 사용자가 위치를 고르지 않았으면 프로그램 옆 output 아래에 만든다."""
        clip = self.clip()
        if self.out_parent:
            return os.path.join(self.out_parent, core.stem_for(self.src, clip) + "_steam")
        return core.default_out_dir(self.src, clip)

    def update_dest(self):
        self.dest_label.setText(self.dest() if self.src else "파일을 선택하면 저장 위치가 표시됩니다.")

    def pick_dest(self):
        start = self.out_parent or core.output_root()
        if not os.path.isdir(start):
            start = core.app_dir()
        folder = QFileDialog.getExistingDirectory(self, "조각을 저장할 위치 선택", start)
        if folder:
            self.out_parent = os.path.normpath(folder)
            self.update_dest()
            self.save_preferences()

    def clip(self):
        """(시작 초, 끝 초, fps). 동영상이 아니면 None이다."""
        if self.vinfo is None:
            return None
        return (round(self.bar.start, 3), round(self.bar.end, 3), int(self.fps.currentData()))

    def sync_clip(self):
        """구간 막대의 값을 입력 칸과 안내 문구에 반영한다."""
        for spin, value in ((self.s_start, self.bar.start), (self.s_end, self.bar.end)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        length = self.bar.end - self.bar.start
        frames = round(length * int(self.fps.currentData()))
        self.clip_label.setText(f"길이 {length:.2f}초 · 약 {frames}프레임 (최대 {video.MAX_CLIP_SECONDS:.0f}초)")
        self.update_dest()   # 동영상은 구간이 결과 폴더의 이름에 들어간다

    def on_bar(self, moved):
        self.sync_clip()
        self.grabber.ask(self.src, moved)

    def on_spin(self):
        if self.vinfo is None:
            return
        lo, hi = video.MIN_CLIP_SECONDS, video.MAX_CLIP_SECONDS
        start, end = self.s_start.value(), self.s_end.value()
        if self.sender() is self.s_start:
            start = min(start, self.vinfo.duration - lo)
            end = min(max(end, start + lo), start + hi)
            moved = start
        else:
            end = max(end, lo)
            start = max(min(start, end - lo), end - hi)
            moved = end
        self.bar.set_range(self.vinfo.duration, start, end)
        self.on_bar(moved)

    def on_frame(self, path, data):
        if not self._closing and self.vinfo is not None and path == self.src:
            self.preview.set_still(QImage.fromData(data))

    def build_upload(self):
        """저장·생성, 결과, 등록 안내가 항상 같은 위치에 있는 영역."""
        self.panel = QFrame()
        self.panel.setObjectName("panel")
        lay = QVBoxLayout(self.panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        heading = QLabel("02  저장 · 만들기")
        heading.setObjectName("section")
        lay.addWidget(heading)
        self.build_actions(lay)

        top = QHBoxLayout()
        self.done_label = QLabel("생성한 조각이 여기에 표시됩니다.")
        self.done_label.setObjectName("done")
        self.b_folder = QPushButton("폴더 열기")
        self.decorate(self.b_folder, "folder")
        self.b_folder.clicked.connect(self.open_folder)
        top.addWidget(self.done_label, 1)
        top.addWidget(self.b_folder)
        lay.addLayout(top)

        where = QHBoxLayout()
        self.path_label = PathLabel()
        self.path_label.setText("완료 후 저장 폴더가 자동으로 열립니다.")
        self.b_path = QPushButton("경로 복사")
        self.decorate(self.b_path, "copy")
        self.b_path.clicked.connect(lambda: self.copy(self.result.out_dir if self.result else "",
                                                      "저장 위치의 경로를 복사했습니다."))
        where.addWidget(self.path_label, 1)
        where.addWidget(self.b_path)
        lay.addLayout(where)

        self.chips: list[DragLabel] = []
        chips = QHBoxLayout()
        for i in range(core.N):
            c = DragLabel()
            c.setText(f"{i + 1}번\n대기")
            c.clicked.connect(steam.reveal)
            self.chips.append(c)
            chips.addWidget(c, 1)
        lay.addLayout(chips)

        rule = QFrame()
        rule.setObjectName("rule")
        lay.addWidget(rule)

        heading = QLabel("03  스팀 등록 안내")
        heading.setObjectName("section")
        lay.addWidget(heading)
        howto = QVBoxLayout()
        howto.setSpacing(6)
        for line in steam.HOWTO[1:]:
            guide = QLabel(line)
            guide.setObjectName("hint")
            guide.setWordWrap(True)
            guide.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            howto.addWidget(guide)
        lay.addLayout(howto)

        foot = QHBoxLayout()
        self.b_page = QPushButton("업로드 페이지 열기")
        self.decorate(self.b_page, "upload")
        self.b_page.clicked.connect(steam.open_upload_page)
        self.b_snip = QPushButton("명령어 복사")
        self.decorate(self.b_snip, "copy")
        self.b_snip.clicked.connect(lambda: self.copy(steam.CONSOLE_SNIPPET, "명령어를 복사했습니다. 업로드 페이지의 "
                                                      "Console 창에 붙여 넣고 Enter를 누르세요."))
        self.notice = QLabel(steam.NOTICE)
        self.notice.setObjectName("notice")
        self.notice.setWordWrap(True)
        foot.addWidget(self.b_page)
        foot.addWidget(self.b_snip)
        foot.addStretch(1)
        lay.addLayout(foot)
        lay.addWidget(self.notice)
        lay.addStretch(1)
        return self.panel

    # ---------- 상태 표시 ----------
    def say(self, text, error=False):
        self.status.setText(text)
        self.status.setToolTip(text)
        self.status.setProperty("error", "true" if error else "false")
        repolish(self.status)

    def refresh(self):
        busy = self.busy()
        self.go.setEnabled(bool(self.src) and not busy)
        self.go.setText("만드는 중..." if busy else "5조각 만들기")
        self.stop.setEnabled(self.worker is not None or self.loader is not None)
        self.pick_btn.setEnabled(not busy)
        self.preview.setEnabled(not busy)
        self.lossy.setEnabled(not busy)
        self.clip_stack.setCurrentIndex(1 if self.vinfo is not None else 0)
        self.clip_box.setEnabled(not busy)
        self.dest_btn.setEnabled(bool(self.src) and not busy)
        if self.settings_dialog:
            self.update_button.setEnabled(self.update_task is None and not busy)
        ready = self.result is not None and not busy
        self.done_label.setProperty("ready", "true" if ready else "false")
        repolish(self.done_label)
        for widget in (self.b_folder, self.b_path, *self.chips):
            widget.setEnabled(ready)
        if self.result is None:
            self.done_label.setText("조각을 만드는 중입니다." if busy else "생성한 조각이 여기에 표시됩니다.")
            self.path_label.setText("완료 후 저장 폴더가 자동으로 열립니다.")
            for i, chip in enumerate(self.chips):
                chip.path = ""
                chip.setText(f"{i + 1}번\n대기")
            return
        r = self.result
        self.done_label.setText(f"조각 5개 생성 완료 · {r.seconds:.0f}초")
        self.path_label.setText(r.out_dir)
        for i, chip in enumerate(self.chips):
            chip.path = r.files[i]
            chip.setText(f"{i + 1}번\n{r.sizes[i] / 1e6:.2f}MB")
            chip.setToolTip(r.files[i] + "\n누르면 탐색기에서 표시 · 끌어서 파일 전달")

    # ---------- 파일 넣기 ----------
    def busy(self):
        return bool(self._closing or self.worker or self.loader or (self.update_task and self.update_task.release))

    def pick(self):
        if self.busy():
            return
        exts = " ".join("*" + e for e in (".gif", *video.VIDEO_EXTS))
        path, _ = QFileDialog.getOpenFileName(self, "GIF 또는 동영상 선택", os.path.dirname(self.src),
                                              f"GIF 또는 동영상 ({exts})")
        if path:
            self.load(path)

    def dragEnterEvent(self, a0):
        mime = a0.mimeData() if a0 else None
        if a0 and mime and mime.hasUrls() and not self.busy():
            a0.acceptProposedAction()

    def dropEvent(self, a0):
        mime = a0.mimeData() if a0 else None
        urls = mime.urls() if mime else []
        if urls and not self.busy():
            self.load(urls[0].toLocalFile())

    def load(self, path):
        if self.busy():
            return
        self.loader = MediaLoader(path)
        self.loader.done.connect(self.on_loaded)
        self.loader.failed.connect(self.load_failed)
        self.loader.finished.connect(self.load_finished)
        self.loader.start()
        self.say("파일 정보를 읽는 중...")
        self.refresh()

    def load_finished(self):
        if self.loader:
            self.loader.wait()
            self.loader.deleteLater()
            self.loader = None
        if not self._closing:
            self.refresh()

    def load_failed(self, message):
        if not self._closing:
            self.say(message, error=True)

    def on_loaded(self, path, media):
        if self._closing:
            return
        if isinstance(media, video.VideoInfo):
            info = media
            w, h = info.width, info.height
            detail = f"{info.duration:.1f}초 · {info.fps:g}fps"
        else:
            info = None
            w, h, n, ms = media
            detail = f"{n}프레임 · {ms / 1000:.1f}초"
        self.src = path
        self.result = None
        self.vinfo = info
        pl = core.plan(w, h)
        if info is None:
            self.preview.load(path, w, h)
        else:
            self.preview.set_still(None)
            for spin in (self.s_start, self.s_end):
                spin.blockSignals(True)
                spin.setRange(0.0, info.duration)
                spin.blockSignals(False)
            self.bar.set_range(info.duration, 0.0, min(info.duration, DEFAULT_CLIP_SECONDS))
            self.sync_clip()
            self.grabber.ask(path, 0.0)
        self.info.setText(f"{os.path.basename(path)}  ·  {w}×{h}  ·  {detail}  →  "
                          f"조각 {core.SLICE_W}×{pl.total_h} × {core.N}개")
        self.update_dest()
        if info is not None:
            self.say("막대의 손잡이를 끌거나 시각을 입력해서 사용할 구간을 정한 뒤 '5조각 만들기'를 누르세요.")
        else:
            self.say("원본이 작아서 확대됩니다. 화질이 떨어질 수 있습니다." if pl.upscaled else "")
        self.refresh()

    # ---------- 만들기 ----------
    def start(self):
        if not self.src or self.busy():
            return
        clip = self.clip()
        out = self.dest()
        if os.path.isdir(out) and os.listdir(out):
            a = QMessageBox.question(self, APP_NAME, "이미 만든 조각이 있습니다. 덮어쓸까요?\n" + out)
            if a != QMessageBox.StandardButton.Yes:
                return
        self.result = None
        self.worker = Worker(self.src, out, self.lossy.value(), clip)
        self.worker.stage.connect(lambda s: self.say("진행 중: " + s))
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(lambda m: self.finish(m, error=True))
        self.worker.cancelled.connect(lambda: self.finish("취소했습니다."))
        self.worker.start()
        self.refresh()

    def cancel(self):
        if self.loader:
            self.loader.cancel.set()
            self.say("파일 열기를 취소했습니다.")
        if self.worker:
            self.worker.cancel.set()
            self.say("취소하는 중...")

    def on_done(self, result):
        if self._closing:
            return
        self.result = result
        self.finish(f"완료했습니다 (압축 {result.lossy}). 저장한 폴더를 탐색기로 열었습니다.")
        self.open_folder()

    def finish(self, text, error=False):
        if self.worker:
            self.worker.wait()
            self.worker.deleteLater()
            self.worker = None
        if self._closing:
            return
        self.say(text, error)
        self.refresh()

    # ---------- 완료 화면 ----------
    def open_folder(self):
        """탐색기에서 저장 폴더를 열고 1번 조각을 선택해서 보여준다."""
        if self.result:
            steam.reveal(self.result.files[0])

    def copy(self, text, message):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        self.say(message)

    def closeEvent(self, a0):
        if a0 is None:
            return
        if self._closed:
            a0.accept()
            return
        a0.ignore()
        if self._closing:
            return
        message = "SteamSlice를 종료할까요?"
        if self.worker or self.loader or (self.update_task and self.update_task.release):
            message += "\n진행 중인 작업은 취소하고 관련 프로세스를 정리합니다."
        answer = QMessageBox.question(self, APP_NAME, message,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.request_quit()

    def request_quit(self):
        if self._closing:
            return
        self._closing = True
        self.update_timer.stop()
        if self.worker:
            self.worker.cancel.set()
        if self.loader:
            self.loader.cancel.set()
        if self.update_task:
            self.update_task.cancel.set()
        self.grabber.stop()
        if self.preview.movie:
            self.preview.movie.stop()
        for dialog in (self.settings_dialog, self.about_dialog):
            if dialog:
                dialog.close()
        self.quit_action.setEnabled(False)
        self.say("작업과 관련 프로세스를 정리하는 중...")
        self.refresh()
        self.shutdown_timer.start()

    def cleanup(self):
        """세션 종료 등 Qt의 직접 종료 경로에서도 하위 작업을 남기지 않는다."""
        self._closing = True
        self.grabber.stop()
        for thread in (self.worker, self.loader, self.update_task):
            if thread:
                thread.cancel.set()
        for thread in (self.worker, self.loader, self.update_task, self.grabber):
            if thread:
                thread.wait()
        self.tray.hide()

    def poll_shutdown(self):
        threads = (self.worker, self.loader, self.update_task, self.grabber)
        if any(thread is not None and thread.isRunning() for thread in threads):
            return
        self.shutdown_timer.stop()
        if self.pending_update:
            try:
                updater.launch_apply(self.pending_update)
            except OSError as exc:
                self.pending_update = None
                self._closing = False
                self.grabber = FrameGrabber()
                self.grabber.frame.connect(self.on_frame)
                self.quit_action.setEnabled(True)
                self.say(f"업데이트를 시작할 수 없습니다: {exc}", error=True)
                self.refresh()
                return
        self._closed = True
        self.tray.hide()
        self.close()
        app = QApplication.instance()
        if app:
            app.quit()

    def bring_to_front(self):
        if self._closing:
            return
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()
        QApplication.alert(self)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(asset_path("steamslice.png")))

    updating = QLocalSocket()
    updating.connectToServer(updater.UPDATE_SERVER)
    if updating.waitForConnected(100):
        updating.disconnectFromServer()
        QMessageBox.information(None, APP_NAME, "업데이트를 적용하는 중입니다. 완료되면 자동으로 다시 실행됩니다.")
        return 0

    # 중복 실행 방지: 이미 실행 중이면 기존 창을 앞으로 가져오게 하고 종료한다.
    guard = InstanceLock(SERVER_NAME)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    # 먼저 서버 소유권을 얻는다. 동시 실행 시 다른 인스턴스의 서버를 지우지 않는다.
    if not guard.acquired:
        sock = QLocalSocket()
        try:
            for _ in range(30):
                sock.connectToServer(SERVER_NAME)
                if sock.waitForConnected(100):
                    sock.write(b"raise")
                    sock.waitForBytesWritten(1000)
                    sock.disconnectFromServer()
                    return 0
                sock.abort()
                QThread.msleep(50)
            QMessageBox.warning(None, APP_NAME, "실행 중인 SteamSlice에 연결하지 못했습니다. 잠시 후 다시 실행해 주세요.")
            return 1
        finally:
            guard.close()
    if not server.listen(SERVER_NAME):
        guard.close()
        QMessageBox.warning(None, APP_NAME, "실행 통신 서버를 열 수 없습니다.")
        return 1

    apply_theme("light" if settings.load().get("theme") == "light" else "dark")
    win = Window()
    app.aboutToQuit.connect(win.cleanup)

    def on_connect():
        c = server.nextPendingConnection()
        if c:
            c.disconnected.connect(c.deleteLater)
        win.bring_to_front()

    server.newConnection.connect(on_connect)
    win.show()
    result = updater.previous_result()
    if result:
        win.say(result)
    if win.preferences.get("auto_update", True):
        win.update_timer.start(1500)
    try:
        return app.exec()
    finally:
        server.close()
        guard.close()
