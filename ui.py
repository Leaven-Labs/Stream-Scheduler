"""The look of the app: colours (light and dark), the style sheet, and the small widgets the pages share.

Nothing here knows about schedules or platforms. The pictures (the app's icon, the menu's icons, the
platform badges) are drawn in code, so they take the theme's colours and no image files are shipped.
"""
import os

from PySide6.QtCore import QObject, QPointF, QRectF, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFrame, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

import paths

# "Twilight": deep indigo with a violet accent, and a coral dot for "live".
LIGHT = dict(bg="#f5f5fa", side="#eeedf7", card="#ffffff", text="#1b1d2a", sub="#666b80", line="#e2e2ec",
             accent="#5b4be0", accent2="#4a3bc9", soft="#efedfd", softline="#b3abf3", sel="#e7e4fb",
             hover="#f0f0f6", ok="#17805a", okbg="#e1f5ec", warn="#96590a", warnbg="#fdf1dc", no="#b42335",
             nobg="#fde8ea", off="#9aa0b2", disabled="#b6bac6", live="#f0486a", track="#d2d4de",
             knob="#ffffff", youtube="#ff0033", facebook="#1877f2")
DARK = dict(bg="#0f1117", side="#131622", card="#1a1e2b", text="#eceef5", sub="#9299ad", line="#2a2f40",
            accent="#8b7cf8", accent2="#7566ea", soft="#1f1d3a", softline="#4a4391", sel="#262347",
            hover="#232838", ok="#4fd1a1", okbg="#12322a", warn="#f5b85c", warnbg="#3a2c12", no="#ff8a8a",
            nobg="#40191c", off="#6a7186", disabled="#555b6c", live="#ff6b81", track="#3a4052",
            knob="#c9cde0", youtube="#ff3355", facebook="#4a94f7")
THEMES = ("auto", "light", "dark")
colors = dict(DARK)   # the colours in use; apply_theme() fills it


def _chevron(color):
    """The little arrow of the drop-down lists, drawn once per colour into the data folder."""
    folder = os.path.join(paths.data_dir(), "cache")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"chevron-{color.lstrip('#')}.png")
    if not os.path.isfile(path):
        pm = QPixmap(24, 24)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(color), 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(6, 9), QPointF(12, 15), QPointF(18, 9)])
        p.end()
        pm.save(path)
    return path.replace("\\", "/")


def style_sheet(c):
    return f"""
QWidget {{ font-size: 13px; color: {c['text']}; }}
QMainWindow, QDialog, QWidget#root {{ background: {c['bg']}; }}
QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['line']}; padding: 4px; }}
QFrame#card {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 12px; }}
QFrame#card[tone="off"] {{ background: {c['bg']}; }}
QFrame#side {{ background: {c['side']}; border: none; border-right: 1px solid {c['line']}; }}
QFrame#callout {{ background: {c['soft']}; border: 1px solid {c['softline']}; border-radius: 10px; }}
QFrame#callout[kind="warn"] {{ background: {c['warnbg']}; border-color: {c['warn']}; }}
QFrame#rule {{ background: {c['line']}; max-height: 1px; min-height: 1px; border: none; }}
QScrollArea, QWidget#scrollbody {{ background: transparent; border: none; }}
QLabel {{ background: transparent; }}
QLabel#appname {{ font-size: 15px; font-weight: 700; }}
QLabel#pagetitle {{ font-size: 22px; font-weight: 700; }}
QLabel#heading {{ font-size: 16px; font-weight: 600; }}
QLabel#big {{ font-size: 15px; font-weight: 600; }}
QLabel#caps {{ font-size: 11px; font-weight: 700; color: {c['sub']}; }}
QLabel#small {{ font-size: 12px; color: {c['sub']}; }}
QLabel#sub, QLabel#hint {{ color: {c['sub']}; }}
QLabel#strong {{ font-weight: 600; }}
QLabel#error {{ color: {c['no']}; }}
QLabel#good {{ color: {c['ok']}; font-weight: 600; }}
QLabel#stepnum {{ background: {c['line']}; color: {c['sub']}; border-radius: 11px; font-weight: 700;
    min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; }}
QLabel#stepnum[state="now"] {{ background: {c['accent']}; color: white; }}
QLabel#stepnum[state="done"] {{ background: {c['okbg']}; color: {c['ok']}; }}
QLabel#stepname {{ color: {c['sub']}; }}
QLabel#stepname[state="now"] {{ color: {c['text']}; font-weight: 600; }}
QPushButton {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 8px; padding: 7px 16px; }}
QPushButton:hover {{ background: {c['hover']}; }}
QPushButton:pressed {{ background: {c['sel']}; }}
QPushButton:focus {{ border-color: {c['softline']}; }}
QPushButton:disabled {{ color: {c['disabled']}; }}
QPushButton#primary {{ background: {c['accent']}; border: 1px solid {c['accent2']}; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: {c['accent2']}; }}
QPushButton#primary:disabled {{ background: {c['line']}; border-color: {c['line']}; color: {c['disabled']}; }}
QPushButton#danger {{ color: {c['no']}; }}
QPushButton#mini {{ padding: 4px 11px; font-size: 12px; border-radius: 6px; }}
QPushButton#chip {{ padding: 3px 11px; font-size: 12px; font-weight: 600; border-radius: 11px;
    background: {c['hover']}; border: 1px solid {c['line']}; color: {c['sub']}; }}
QPushButton#chip[kind="ok"] {{ background: {c['okbg']}; color: {c['ok']}; border-color: {c['okbg']}; }}
QPushButton#chip[kind="no"] {{ background: {c['nobg']}; color: {c['no']}; border-color: {c['nobg']}; }}
QPushButton#chip[kind="warn"] {{ background: {c['warnbg']}; color: {c['warn']}; border-color: {c['warnbg']}; }}
QPushButton#pick {{ padding: 6px 13px; border-radius: 15px; color: {c['sub']}; }}
QPushButton#pick:checked {{ background: {c['soft']}; border-color: {c['accent']}; color: {c['accent']}; }}
QPushButton#var {{ padding: 2px 8px; font-size: 12px; border-radius: 6px; color: {c['accent']};
    background: {c['soft']}; border: 1px solid {c['soft']}; }}
QPushButton#var:hover {{ border-color: {c['softline']}; }}
QFrame#segs {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 8px; }}
QPushButton#seg {{ background: transparent; border: none; border-radius: 6px; padding: 6px 14px; color: {c['sub']}; }}
QPushButton#seg:hover {{ color: {c['text']}; }}
QPushButton#seg:checked {{ background: {c['soft']}; color: {c['accent']}; font-weight: 600; }}
QMenu {{ background: {c['card']}; border: 1px solid {c['line']}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c['sel']}; }}
QMenu::separator {{ height: 1px; background: {c['line']}; margin: 4px 6px; }}
QLineEdit, QComboBox, QTimeEdit, QSpinBox {{ background: {c['card']}; border: 1px solid {c['line']};
    border-radius: 8px; padding: 6px 10px; selection-background-color: {c['accent']}; selection-color: white; }}
QLineEdit:focus, QComboBox:focus, QTimeEdit:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {c['accent']}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {c['disabled']}; }}
QTimeEdit::up-button, QTimeEdit::down-button, QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({_chevron(c['sub'])}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {c['card']}; border: 1px solid {c['line']};
    selection-background-color: {c['sel']}; selection-color: {c['text']}; outline: 0; }}
QPlainTextEdit {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 8px; padding: 6px;
    selection-background-color: {c['accent']}; selection-color: white; }}
QTableWidget {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 12px;
    selection-background-color: {c['sel']}; selection-color: {c['text']}; outline: 0; gridline-color: transparent; }}
QTableWidget::item {{ padding: 4px 10px; border-bottom: 1px solid {c['line']}; }}
QTableWidget::item:selected {{ background: {c['sel']}; color: {c['text']}; }}
QHeaderView::section {{ background: {c['card']}; color: {c['sub']}; font-weight: 600; border: none;
    border-bottom: 1px solid {c['line']}; padding: 10px 10px; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section:first {{ border-top-left-radius: 11px; }}
QHeaderView::section:last {{ border-top-right-radius: 11px; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {c['track']}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px 4px; }}
QScrollBar::handle:horizontal {{ background: {c['track']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QMessageBox QLabel {{ min-width: 280px; }}
"""


def system_is_dark():
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # an older Qt
        return False


def apply_theme(app, theme="auto"):
    """Set the app's colours: "auto" follows the system's light or dark setting."""
    theme = theme if theme in THEMES else "auto"
    hints = QGuiApplication.styleHints()
    if hasattr(hints, "setColorScheme"):  # the window title bars follow too (Qt 6.8+)
        hints.setColorScheme({"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(
            theme, Qt.ColorScheme.Unknown))
    dark = theme == "dark" or (theme == "auto" and system_is_dark())
    colors.clear()
    colors.update(DARK if dark else LIGHT)
    app.setStyleSheet(style_sheet(colors))


def start_app(argv, theme="auto"):
    """The QApplication, with the Fusion style (the same on every system), the icon and the theme."""
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(paths.APP_NAME)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    apply_theme(app, theme)
    return app


# ---- small helpers -------------------------------------------------------------------------

def label(text="", kind="", wrap=False):
    """A QLabel; kind is its style: pagetitle, heading, big, caps, sub, small, strong, error or good."""
    lab = QLabel(text)
    if kind:
        lab.setObjectName(kind)
    if kind == "caps":
        font = lab.font()
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        lab.setFont(font)
    lab.setWordWrap(wrap)
    return lab


def rich(html):
    """A paragraph with bold words and links that open in the browser."""
    lab = QLabel(html.replace("<a ", f"<a style='color:{colors['accent']}' "))
    lab.setTextFormat(Qt.RichText)
    lab.setWordWrap(True)
    lab.setOpenExternalLinks(True)
    lab.setTextInteractionFlags(Qt.TextBrowserInteraction)
    return lab


def card(tone=""):
    f = QFrame()
    f.setObjectName("card")
    if tone:
        f.setProperty("tone", tone)
    return f


def rule():
    f = QFrame()
    f.setObjectName("rule")
    return f


def button(text, kind="", clicked=None, tip=""):
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if clicked:
        b.clicked.connect(clicked)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return b


def chip(text, kind="", tip="", clicked=None):
    """A small rounded tag: "YouTube · Scheduled". It is a button so it can open a link."""
    b = button(text, "chip", clicked, tip)
    b.setProperty("kind", kind)
    if not clicked:
        b.setCursor(Qt.ArrowCursor)
        b.setFocusPolicy(Qt.NoFocus)
    return b


def callout(title, html, kind="", icon="shield"):
    """A tinted box for what matters: how a step keeps the account safe, or a warning."""
    box = QFrame()
    box.setObjectName("callout")
    box.setProperty("kind", kind)
    row = QHBoxLayout(box)
    row.setContentsMargins(14, 12, 14, 12)
    row.setSpacing(12)
    row.addWidget(Icon(icon, 22, "warn" if kind == "warn" else "accent"), 0, Qt.AlignTop)
    col = QVBoxLayout()
    col.setSpacing(3)
    col.addWidget(label(title, "strong"))
    col.addWidget(rich(html))
    row.addLayout(col, 1)
    return box


def ask(parent, title, text):
    return QMessageBox.question(parent, title, text) == QMessageBox.Yes


def tell(parent, title, text):
    QMessageBox.information(parent, title, text)


def set_prop(widget, name, value):
    """Set a property the style sheet looks at and restyle the widget."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def clear(layout):
    """Take everything out of a layout (before a page is filled again)."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout():
            clear(item.layout())


def fixed_font(size=9):
    f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    f.setPointSize(size)
    return f


# ---- work off the window's thread ----------------------------------------------------------

class _Signals(QObject):
    done = Signal(object, object)


class _Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn, self.signals = fn, _Signals()

    def run(self):
        try:
            result, error = self.fn(), None
        except Exception as exc:
            result, error = None, exc
        try:
            self.signals.done.emit(result, error)
        except RuntimeError:
            pass  # the window is gone


_jobs = set()


def run_async(fn, done):
    """Run fn() on another thread (network calls), then done(result, error) on the window's thread."""
    job = _Job(fn)
    job.setAutoDelete(False)
    _jobs.add(job)

    def finish(result, error):
        _jobs.discard(job)
        done(result, error)
    job.signals.done.connect(finish, Qt.QueuedConnection)
    QThreadPool.globalInstance().start(job)


# ---- drawings ------------------------------------------------------------------------------

def draw_app_icon(p, size):
    """The app's icon (the same picture as assets/icon.svg): a calendar page that goes live."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 256, size / 256)
    grad = QLinearGradient(8, 8, 248, 248)
    grad.setColorAt(0, QColor("#8b7cf8"))
    grad.setColorAt(1, QColor("#4534c9"))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(8, 8, 240, 240), 56, 56)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor("white"), 14, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawRoundedRect(QRectF(56, 70, 144, 130), 22, 22)
    p.drawLine(QPointF(56, 108), QPointF(200, 108))
    p.drawLine(QPointF(96, 52), QPointF(96, 84))
    p.drawLine(QPointF(160, 52), QPointF(160, 84))
    p.setPen(QPen(QColor("white"), 9, Qt.SolidLine, Qt.RoundCap))
    ring = QRectF(128 - 33, 154 - 33, 66, 66)
    p.drawArc(ring, -40 * 16, 80 * 16)
    p.drawArc(ring, 140 * 16, 80 * 16)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ff6b81"))
    p.drawEllipse(QPointF(128, 154), 15, 15)
    p.restore()


def app_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        draw_app_icon(p, size)
        p.end()
        icon.addPixmap(pm)
    return icon


def draw_icon(p, name, rect, color):
    """A small line drawing in `rect`: upcoming, schedules, destinations, history, settings, shield,
    warn, youtube or facebook."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(rect.x(), rect.y())
    p.scale(rect.width() / 24, rect.height() / 24)
    col = QColor(color)
    pen = QPen(col, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if name == "upcoming":  # a calendar
        p.drawRoundedRect(QRectF(3.5, 5, 17, 15.5), 3, 3)
        p.drawLine(QPointF(3.5, 9.5), QPointF(20.5, 9.5))
        p.drawLine(QPointF(8, 3), QPointF(8, 6.5))
        p.drawLine(QPointF(16, 3), QPointF(16, 6.5))
        p.setBrush(col)
        p.drawEllipse(QPointF(12, 14.8), 1.6, 1.6)
    elif name == "schedules":  # two arrows in a circle: it repeats
        p.drawArc(QRectF(4, 4, 16, 16), 30 * 16, 150 * 16)
        p.drawArc(QRectF(4, 4, 16, 16), 210 * 16, 150 * 16)
        p.drawPolyline([QPointF(16.2, 4.2), QPointF(19.2, 7.6), QPointF(14.8, 8.6)])
        p.drawPolyline([QPointF(7.8, 19.8), QPointF(4.8, 16.4), QPointF(9.2, 15.4)])
    elif name == "destinations":  # a dot that sends
        p.drawArc(QRectF(6.5, 6.5, 11, 11), -45 * 16, 90 * 16)
        p.drawArc(QRectF(6.5, 6.5, 11, 11), 135 * 16, 90 * 16)
        p.drawArc(QRectF(2.5, 2.5, 19, 19), -45 * 16, 90 * 16)
        p.drawArc(QRectF(2.5, 2.5, 19, 19), 135 * 16, 90 * 16)
        p.setBrush(col)
        p.drawEllipse(QPointF(12, 12), 2, 2)
    elif name == "history":  # a clock
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        p.drawPolyline([QPointF(12, 7.5), QPointF(12, 12), QPointF(15.2, 14)])
    elif name == "settings":  # three sliders
        for y, x in ((6.5, 15), (12, 9), (17.5, 14)):
            p.drawLine(QPointF(4, y), QPointF(20, y))
            p.setBrush(QColor(colors["side"]))
            p.drawEllipse(QPointF(x, y), 2.2, 2.2)
            p.setBrush(Qt.NoBrush)
    elif name == "shield":
        path = QPainterPath(QPointF(12, 3))
        path.lineTo(19, 5.8)
        path.lineTo(19, 11.5)
        path.cubicTo(19, 16, 16, 19.3, 12, 21)
        path.cubicTo(8, 19.3, 5, 16, 5, 11.5)
        path.lineTo(5, 5.8)
        path.closeSubpath()
        p.drawPath(path)
        p.drawPolyline([QPointF(9, 12), QPointF(11.2, 14.2), QPointF(15.2, 9.8)])
    elif name == "warn":
        p.drawPolygon([QPointF(12, 3.5), QPointF(21, 19.5), QPointF(3, 19.5)])
        p.drawLine(QPointF(12, 10), QPointF(12, 14))
        p.setBrush(col)
        p.drawEllipse(QPointF(12, 16.8), 0.6, 0.6)
    elif name == "youtube":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(colors["youtube"]))
        p.drawRoundedRect(QRectF(1.5, 4.5, 21, 15), 4.5, 4.5)
        p.setBrush(QColor("white"))
        p.drawPolygon([QPointF(9.8, 8.6), QPointF(15.6, 12), QPointF(9.8, 15.4)])
    elif name == "facebook":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(colors["facebook"]))
        p.drawEllipse(QPointF(12, 12), 10.5, 10.5)
        p.setPen(QPen(QColor("white"), 2.4, Qt.SolidLine, Qt.FlatCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(15.6, 6.6))
        path.lineTo(14.2, 6.6)
        path.cubicTo(12.6, 6.6, 12, 7.6, 12, 9)
        path.lineTo(12, 22)
        p.setClipRect(QRectF(0, 0, 24, 22.2))
        p.drawPath(path)
        p.drawLine(QPointF(9, 12.4), QPointF(15.2, 12.4))
    p.restore()


class Icon(QWidget):
    """One of draw_icon's drawings as a widget. `color` is a key of the theme's colours."""

    def __init__(self, name, size=20, color="sub"):
        super().__init__()
        self.name, self.color = name, color
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        p = QPainter(self)
        draw_icon(p, self.name, QRectF(0, 0, self.width(), self.height()), colors[self.color])
        p.end()


class Logo(QWidget):
    def __init__(self, size=34):
        super().__init__()
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        p = QPainter(self)
        draw_app_icon(p, self.width())
        p.end()


class NavButton(QAbstractButton):
    """A line of the menu at the left: an icon and a name; the chosen one is tinted."""

    def __init__(self, icon, text):
        super().__init__()
        self.icon_name = icon
        self.setText(text)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(38)

    def sizeHint(self):
        return QSize(190, 38)

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        if on or self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(colors["sel" if on else "hover"]))
            p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        color = colors["accent" if on else "sub"]
        draw_icon(p, self.icon_name, QRectF(12, 9, 20, 20), color)
        font = self.font()
        font.setWeight(QFont.DemiBold if on else QFont.Normal)
        p.setFont(font)
        p.setPen(QColor(colors["text" if on else "sub"]))
        p.drawText(self.rect().adjusted(44, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()


class Switch(QAbstractButton):
    """An on / off switch."""

    def __init__(self, on=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(on)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 22)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(colors["accent" if self.isChecked() else "track"]))
        p.drawRoundedRect(QRectF(0, 0, 40, 22), 11, 11)
        p.setBrush(QColor("white" if self.isChecked() else colors["knob"]))
        p.drawEllipse(QPointF(29 if self.isChecked() else 11, 11), 8, 8)
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(colors["softline"]), 1.5))
            p.drawRoundedRect(QRectF(0.75, 0.75, 38.5, 20.5), 10, 10)
        p.end()


class Segments(QFrame):
    """A few choices in one row, one chosen: [Auto | Light | Dark]. `changed` gives the chosen key."""
    changed = Signal(str)

    def __init__(self, choices, current):
        super().__init__()
        self.setObjectName("segs")
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self.buttons = {}
        for key, text in choices:
            b = button(text, "seg")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setChecked(key == current)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            row.addWidget(b)
            self.buttons[key] = b


class DateBlock(QWidget):
    """A calendar leaf: the month above, the day large, the weekday below."""

    def __init__(self, when, dim=False):
        super().__init__()
        self.when, self.dim = when, dim
        self.setFixedSize(62, 68)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        p.setClipPath(path)
        p.fillRect(r, QColor(colors["soft"] if not self.dim else colors["hover"]))
        p.fillRect(QRectF(0, 0, self.width(), 20), QColor(colors["accent"] if not self.dim else colors["off"]))
        font = self.font()
        font.setPixelSize(11)
        font.setWeight(QFont.Bold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1)
        p.setFont(font)
        p.setPen(QColor("white"))
        p.drawText(QRectF(0, 0, self.width(), 20), Qt.AlignCenter, self.when.strftime("%b").upper())
        font.setPixelSize(22)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 0)
        p.setFont(font)
        p.setPen(QColor(colors["text"] if not self.dim else colors["sub"]))
        p.drawText(QRectF(0, 20, self.width(), 30), Qt.AlignCenter, str(self.when.day))
        font.setPixelSize(11)
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        p.setPen(QColor(colors["sub"]))
        p.drawText(QRectF(0, 46, self.width(), 18), Qt.AlignCenter, self.when.strftime("%a"))
        p.end()


class Dot(QWidget):
    """A small round light: green when the app is watching, grey when not."""

    def __init__(self, color="ok"):
        super().__init__()
        self.color = color
        self.setFixedSize(10, 10)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(colors[self.color]))
        p.drawEllipse(QRectF(1, 1, 8, 8))
        p.end()
