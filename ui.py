"""The look of the app: colours (light and dark), the style sheet, and the small widgets the pages share.

Nothing here knows about schedules or platforms. The pictures (the app's icon, the menu's icons, the
platform badges) are drawn in code, so they take the theme's colours and no image files are shipped.

The look is the website's (docs/index.html): its gradient of indigo, violet and coral, its heading
typeface (fraunces.py), a glow under what matters, and a few small animations. The animations run only
while the window is shown, and Settings can turn them off (`motion`).
"""
import math
import os

from PySide6.QtCore import (QByteArray, QEasingCurve, QElapsedTimer, QEvent, QObject, QPointF, QRectF, QRunnable,
                            QSize, Qt, QThreadPool, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget)

import paths

# "Twilight": deep indigo with a violet accent, and a coral dot for "live".
LIGHT = dict(bg="#f5f5fa", side="#eeedf7", card="#ffffff", text="#1b1d2a", sub="#666b80", line="#e2e2ec",
             accent="#5b4be0", accent2="#4a3bc9", soft="#efedfd", softline="#b3abf3", sel="#e7e4fb",
             hover="#f0f0f6", ok="#17805a", okbg="#e1f5ec", warn="#96590a", warnbg="#fdf1dc", no="#b42335",
             nobg="#fde8ea", off="#9aa0b2", disabled="#b6bac6", live="#f0486a", track="#d2d4de",
             knob="#ffffff", youtube="#ff0033", facebook="#1877f2",
             # the website's gradient (g1 to g3), its gradient words (t1, t2), and the buttons' own gradient
             g1="#4534c9", g2="#8b7cf8", g3="#ff6b81", t1="#5b4be0", t2="#f0486a", glint="#ffc2cb",
             btn1="#4a3bc9", btn2="#7a5cf0", glow=0.7)
DARK = dict(bg="#0f1117", side="#131622", card="#1a1e2b", text="#eceef5", sub="#9299ad", line="#2a2f40",
            accent="#8b7cf8", accent2="#7566ea", soft="#1f1d3a", softline="#4a4391", sel="#262347",
            hover="#232838", ok="#4fd1a1", okbg="#12322a", warn="#f5b85c", warnbg="#3a2c12", no="#ff8a8a",
            nobg="#40191c", off="#6a7186", disabled="#555b6c", live="#ff6b81", track="#3a4052",
            knob="#c9cde0", youtube="#ff3355", facebook="#4a94f7",
            g1="#4534c9", g2="#8b7cf8", g3="#ff6b81", t1="#a69bfa", t2="#ff6b81", glint="#ffffff",
            btn1="#6f5ff0", btn2="#9a7cf8", glow=0.9)
THEMES = ("auto", "light", "dark")
colors = dict(DARK)   # the colours in use; apply_theme() fills it
DISPLAY = "Fraunces"  # the headings' typeface (fraunces.py); without it Qt takes the system's
motion = True         # the small animations; set_motion() changes it


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
QFrame#card[tone="next"] {{ border-color: {c['softline']}; }}
QFrame#callout {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c['soft']}, stop:1 {c['card']});
    border: 1px solid {c['softline']}; border-radius: 10px; }}
QFrame#callout[kind="warn"] {{ background: {c['warnbg']}; border-color: {c['warn']}; }}
QFrame#rule {{ background: {c['line']}; max-height: 1px; min-height: 1px; border: none; }}
QScrollArea, QWidget#scrollbody {{ background: transparent; border: none; }}
QLabel {{ background: transparent; }}
QLabel#appname {{ font-family: "{DISPLAY}"; font-size: 17px; font-weight: 600; }}
QLabel#pagetitle {{ font-family: "{DISPLAY}"; font-size: 27px; font-weight: 600; }}
QLabel#heading {{ font-family: "{DISPLAY}"; font-size: 19px; font-weight: 600; }}
QLabel#big {{ font-size: 15px; font-weight: 600; }}
QLabel#caps {{ font-size: 11px; font-weight: 700; color: {c['sub']}; }}
QLabel#small {{ font-size: 12px; color: {c['sub']}; }}
QLabel#sub, QLabel#hint {{ color: {c['sub']}; }}
QLabel#strong {{ font-weight: 600; }}
QLabel#error {{ color: {c['no']}; }}
QLabel#good {{ color: {c['ok']}; font-weight: 600; }}
QLabel#stepnum {{ background: {c['line']}; color: {c['sub']}; border-radius: 11px; font-weight: 700;
    min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; }}
QLabel#stepnum[state="now"] {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {c['btn1']},
    stop:1 {c['btn2']}); color: white; }}
QLabel#stepnum[state="done"] {{ background: {c['okbg']}; color: {c['ok']}; }}
QLabel#stepname {{ color: {c['sub']}; }}
QLabel#stepname[state="now"] {{ color: {c['text']}; font-weight: 600; }}
QPushButton {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 8px; padding: 7px 16px; }}
QPushButton:hover {{ background: {c['hover']}; }}
QPushButton:pressed {{ background: {c['sel']}; }}
QPushButton:focus {{ border-color: {c['softline']}; }}
QPushButton:disabled {{ color: {c['disabled']}; }}
QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {c['btn1']}, stop:1 {c['btn2']});
    border: 1px solid {c['btn1']}; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {c['btn2']}, stop:1 {c['btn1']}); }}
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
QLineEdit, QComboBox, QTimeEdit, QDateEdit, QSpinBox {{ background: {c['card']}; border: 1px solid {c['line']};
    border-radius: 8px; padding: 6px 10px; selection-background-color: {c['accent']}; selection-color: white; }}
QLineEdit:focus, QComboBox:focus, QTimeEdit:focus, QDateEdit:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {c['accent']}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {c['disabled']}; }}
QTimeEdit::up-button, QTimeEdit::down-button, QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 26px; }}
QCalendarWidget QWidget {{ alternate-background-color: {c['card']}; }}
QCalendarWidget QAbstractItemView {{ background: {c['card']}; selection-background-color: {c['accent']};
    selection-color: white; }}
QCalendarWidget QToolButton {{ color: {c['text']}; background: transparent; border: none; padding: 4px 8px; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {c['card']}; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url({_chevron(c['sub'])}); width: 12px; height: 12px; }}
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


def set_motion(on):
    """Turn the small animations on or off (the Settings page; what is already on screen stops by itself)."""
    global motion
    motion = bool(on)


def load_display_font():
    """Give Qt the headings' typeface. Without it (a broken install) the headings are in the system's."""
    if DISPLAY in QFontDatabase.families():
        return
    import fraunces
    QFontDatabase.addApplicationFontFromData(QByteArray(fraunces.TTF))


def start_app(argv, theme="auto"):
    """The QApplication, with the Fusion style (the same on every system), the icon and the theme."""
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(paths.APP_NAME)
    app.setStyle("Fusion")
    load_display_font()
    app.setWindowIcon(app_icon())
    apply_theme(app, theme)
    return app


# ---- small helpers -------------------------------------------------------------------------

def label(text="", kind="", wrap=False):
    """A QLabel; kind is its style: pagetitle, heading, big, caps, sub, small, strong, error or good."""
    lab = Title(text) if kind == "pagetitle" else QLabel(text)
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
    b = PrimaryButton(text) if kind == "primary" else QPushButton(text)
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


def toggle_row(switch, text):
    """A switch with its words at the right, as one widget."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    row.addWidget(switch)
    row.addWidget(label(text, "strong"), 1)
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


# ---- gradients, glows and what moves --------------------------------------------------------

def mix(a, b, t):
    """The colour a part t (0 to 1) of the way from a to b."""
    a, b = QColor(a), QColor(b)
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def gradient(x1, x2, *names):
    """A left-to-right gradient from x1 to x2 through the named colours of the theme."""
    g = QLinearGradient(x1, 0, x2, 0)
    for i, name in enumerate(names):
        g.setColorAt(i / (len(names) - 1), QColor(colors[name]))
    return g


def glide(owner, change, ms=180):
    """An animation from 0 to 1 that calls change(value); start it with .setDirection() and .start()."""
    anim = QVariantAnimation(owner)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(ms)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.valueChanged.connect(change)
    return anim


class Moving(QWidget):
    """A widget with a clock: tick(seconds) is called 25 times a second while the widget is shown,
    wanted() is true and the animations are on. Hidden (the window is in the tray), nothing runs."""

    def __init__(self):
        super().__init__()
        self._clock = QTimer(self)
        self._clock.setInterval(40)
        self._clock.timeout.connect(self._step)
        self._since = QElapsedTimer()

    moving = property(lambda self: self._clock.isActive())

    def wanted(self):
        return True

    def wake(self):
        """Start or stop the clock, after something changed."""
        if motion and self.isVisible() and self.wanted():
            if not self._clock.isActive():
                self._since.start()
                self._clock.start()
        elif self._clock.isActive():
            self._clock.stop()
            self.update()

    def showEvent(self, event):
        self.wake()

    def hideEvent(self, event):
        self._clock.stop()

    def _step(self):
        if not (motion and self.wanted()):
            self._clock.stop()
        else:
            self.tick(self._since.elapsed() / 1000)
        self.update()

    def tick(self, seconds):
        pass


class Title(QLabel):
    """A page's title in the gradient of the website's headline. A band of light crosses it once each
    time the page is shown."""

    def __init__(self, text=""):
        super().__init__(text)
        self.shine = 2.0   # where the band is, 0 (left) to 1 (right); outside that there is none
        self.sweep = glide(self, self._move, 1100)
        self.sweep.setEasingCurve(QEasingCurve.InOutSine)

    def _move(self, t):
        self.shine = -0.2 + 1.4 * t
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if motion:
            self.sweep.stop()
            self.sweep.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.font())
        width = max(1, self.fontMetrics().horizontalAdvance(self.text()))
        left = self.contentsRect().left()
        g = QLinearGradient(left, 0, left + width, 0)
        g.setColorAt(0, QColor(colors["t1"]))
        g.setColorAt(1, QColor(colors["t2"]))
        for offset, light in ((-0.1, 0), (0, 0.85), (0.1, 0)):
            at = self.shine + offset
            if 0 < at < 1:
                g.setColorAt(at, mix(mix(colors["t1"], colors["t2"], at), colors["glint"], light))
        p.setPen(QPen(QBrush(g), 1))
        p.drawText(self.contentsRect(), Qt.AlignLeft | Qt.AlignVCenter, self.text())
        p.end()


class PrimaryButton(QPushButton):
    """The button of a page's main step: the gradient (in the style sheet) and a glow under it that
    grows while the pointer is on it."""

    def __init__(self, text=""):
        super().__init__(text)
        self.glow = QGraphicsDropShadowEffect(self)
        self.glow.setOffset(0, 4)
        self.setGraphicsEffect(self.glow)
        self.rise = glide(self, self._lift)
        self._lift(0.0)

    def _lift(self, t):
        color = QColor(colors["g2"])
        color.setAlpha(round((0.42 + 0.3 * t) * colors["glow"] * 255))
        self.glow.setColor(color)
        self.glow.setBlurRadius(16 + 12 * t)

    def _go(self, up):
        if motion and self.isEnabled():
            self.rise.setDirection(QVariantAnimation.Forward if up else QVariantAnimation.Backward)
            self.rise.start()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._go(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._go(False)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange and getattr(self, "glow", None):
            self.glow.setEnabled(self.isEnabled())


_strips = {}


def _glow_strip(width):
    """A soft band of the gradient, `width` wide when drawn: painted small and drawn large, which blurs it."""
    key = (max(8, width // 10), colors["g1"], colors["g2"], colors["g3"])
    if key not in _strips:
        if len(_strips) > 40:
            _strips.clear()
        w, h = key[0], 10
        image = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        p = QPainter(image)
        p.fillRect(0, 0, w, h, gradient(0, w, "g1", "g2", "g3"))
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        down = QLinearGradient(0, 0, 0, h)   # strongest in the middle, nothing at the top and bottom
        for at, alpha in ((0, 0), (0.5, 255), (1, 0)):
            down.setColorAt(at, QColor(0, 0, 0, alpha))
        p.fillRect(0, 0, w, h, down)
        across = QLinearGradient(0, 0, w, 0)  # and nothing at the two ends
        for at, alpha in ((0, 0), (0.18, 255), (0.82, 255), (1, 0)):
            across.setColorAt(at, QColor(0, 0, 0, alpha))
        p.fillRect(0, 0, w, h, across)
        p.end()
        _strips[key] = image
    return _strips[key]


class Underglow(Moving):
    """Holds one widget (a card) and lets the gradient glow under its lower edge, as under the website's
    buttons and screenshot. The glow breathes slowly."""
    ROOM, INSET = 14, 26

    def __init__(self, child):
        super().__init__()
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, self.ROOM)
        box.addWidget(child)
        self.level = 0.8

    def tick(self, seconds):
        self.level = 0.72 + 0.28 * math.sin(seconds * 2 * math.pi / 5)

    def paintEvent(self, event):
        width = self.width() - 2 * self.INSET
        if width < 40:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setOpacity(self.level * colors["glow"])
        p.drawImage(QRectF(self.INSET, self.height() - 2 * self.ROOM - 2, width, 2 * self.ROOM + 2), _glow_strip(width))
        p.end()


class Beam(Moving):
    """The gradient line along the top of the window. While the app is working (set_busy), a band of
    light runs along it."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(3)
        self.busy, self.at, self.lap = False, -1.0, 0

    def set_busy(self, on):
        self.busy = on
        self.wake()

    def wanted(self):
        return self.busy or self.at >= 0

    def tick(self, seconds):
        lap, part = divmod(seconds / 1.5, 1)
        if not self.busy and (self.at < 0 or lap != self.lap):   # the work is done: this run was the last
            self.at = -1.0
            return
        self.at, self.lap = part, lap

    def paintEvent(self, event):
        p = QPainter(self)
        w = self.width()
        p.fillRect(self.rect(), gradient(0, w, "g1", "g2", "g3"))
        if self.moving and self.at >= 0:
            mid = (-0.15 + 1.3 * self.at) * w
            light = QLinearGradient(mid - 0.12 * w, 0, mid + 0.12 * w, 0)
            for at, alpha in ((0, 0), (0.5, 235), (1, 0)):
                light.setColorAt(at, QColor(255, 255, 255, alpha))
            p.fillRect(self.rect(), light)
        p.end()


class Curtain(QWidget):
    """Laid over the pages when another page is chosen, in the window's colour, and faded away at once:
    the new page seems to fade in. Nothing is put on the pages themselves."""

    def __init__(self, over):
        super().__init__(over)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.alpha = 0.0
        self.fade = glide(self, self._set, 220)
        self.fade.finished.connect(self.hide)
        self.hide()

    def _set(self, t):
        self.alpha = 1 - t
        self.update()

    def drop(self):
        over = self.parentWidget()
        if not (motion and over.isVisible()):
            return
        self.setGeometry(over.rect())
        self.alpha = 1.0
        self.raise_()
        self.show()
        self.fade.stop()
        self.fade.start()

    def paintEvent(self, event):
        p = QPainter(self)
        color = QColor(colors["bg"])
        color.setAlphaF(self.alpha)
        p.fillRect(self.rect(), color)
        p.end()


class Side(QFrame):
    """The menu's column at the left: its colour, with the gradient's violet glowing softly from the
    corner behind the app's name and a little coral from the bottom."""

    def __init__(self):
        super().__init__()
        self.setObjectName("side")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(colors["side"]))
        for name, center, radius, strength in (("g2", QPointF(20, 10), 300, 0.34),
                                               ("g3", QPointF(self.width() * 0.2, self.height() + 40), 260, 0.14)):
            color = QColor(colors[name])
            glow = QRadialGradient(center, radius)
            color.setAlphaF(strength * colors["glow"])
            glow.setColorAt(0, color)
            color.setAlphaF(0)
            glow.setColorAt(1, color)
            p.fillRect(self.rect(), glow)
        p.setPen(QColor(colors["line"]))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        p.end()


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
    """The app's icon (the same picture as assets/icon.svg): a calendar page that comes round by itself.
    At 40 pixels and smaller the lines are thicker, so that the arrows do not blur into a ring."""
    small = size <= 40
    line = 20 if small else 14
    page = QRectF(52, 72, 152, 132) if small else QRectF(56, 70, 144, 130)
    rule = 112 if small else 108                   # the line under the page's top edge
    rings = (50, 86) if small else (52, 84)
    radius, arrow = (27, 14) if small else (26, 9)
    cy = 158 if small else 154
    white = QColor("white")
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
    p.setPen(QPen(white, line, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawRoundedRect(page, 22, 22)
    p.drawLine(QPointF(page.left(), rule), QPointF(page.right(), rule))
    for x in (96, 160):
        p.drawLine(QPointF(x, rings[0]), QPointF(x, rings[1]))
    circle = QRectF(128 - radius, cy - radius, 2 * radius, 2 * radius)
    for start, end in ((200, 330), (20, 150)):     # two arrows, in degrees clockwise from 3 o'clock
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(white, arrow, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(circle, -start * 16, -(end - start) * 16)
        a = math.radians(end)
        ex, ey = 128 + radius * math.cos(a), cy + radius * math.sin(a)
        tx, ty, nx, ny = -math.sin(a), math.cos(a), math.cos(a), math.sin(a)
        ahead, wide = 1.25 * arrow, 1.05 * arrow
        p.setBrush(white)
        p.setPen(QPen(white, 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolygon(QPolygonF([QPointF(ex + ahead * tx, ey + ahead * ty),
                                 QPointF(ex + wide * nx, ey + wide * ny),
                                 QPointF(ex - wide * nx, ey - wide * ny)]))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ff6b81"))
    p.drawEllipse(QPointF(128, cy), 9, 9)
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
    elif name == "wix":  # a browser window that plays
        p.drawRoundedRect(QRectF(2.5, 4, 19, 16), 3, 3)
        p.drawLine(QPointF(2.5, 8.5), QPointF(21.5, 8.5))
        p.setBrush(col)
        p.drawPolygon([QPointF(10.2, 11.4), QPointF(14.6, 14.2), QPointF(10.2, 17)])
    elif name in ("alerts", "pushover"):  # a bell
        path = QPainterPath(QPointF(5, 17))
        path.cubicTo(7, 15, 6.5, 12, 6.5, 10.5)
        path.cubicTo(6.5, 6.8, 8.9, 4.5, 12, 4.5)
        path.cubicTo(15.1, 4.5, 17.5, 6.8, 17.5, 10.5)
        path.cubicTo(17.5, 12, 17, 15, 19, 17)
        path.closeSubpath()
        p.drawPath(path)
        p.drawArc(QRectF(10, 17.4, 4, 3.4), 180 * 16, 180 * 16)
        p.drawLine(QPointF(12, 3), QPointF(12, 4.5))
    elif name == "email":  # an envelope
        p.drawRoundedRect(QRectF(3, 5.5, 18, 13), 2.5, 2.5)
        p.drawPolyline([QPointF(3.6, 7), QPointF(12, 13), QPointF(20.4, 7)])
    elif name in ("discord", "slack"):  # a speech bubble
        path = QPainterPath(QPointF(6.5, 4.5))
        path.lineTo(17.5, 4.5)
        path.cubicTo(19.4, 4.5, 20.5, 5.6, 20.5, 7.5)
        path.lineTo(20.5, 13)
        path.cubicTo(20.5, 14.9, 19.4, 16, 17.5, 16)
        path.lineTo(11, 16)
        path.lineTo(7, 19.8)
        path.lineTo(7, 16)
        path.lineTo(6.5, 16)
        path.cubicTo(4.6, 16, 3.5, 14.9, 3.5, 13)
        path.lineTo(3.5, 7.5)
        path.cubicTo(3.5, 5.6, 4.6, 4.5, 6.5, 4.5)
        p.drawPath(path)
        p.setBrush(col)
        for x in (8.5, 12, 15.5):
            p.drawEllipse(QPointF(x, 10.3), 0.9, 0.9)
    elif name == "wordpress":  # a page with a video on it
        p.drawRoundedRect(QRectF(4.5, 2.5, 15, 19), 2.5, 2.5)
        p.drawLine(QPointF(8, 6.5), QPointF(16, 6.5))
        p.drawRoundedRect(QRectF(7.5, 10, 9, 7), 1.5, 1.5)
        p.setBrush(col)
        p.drawPolygon([QPointF(11, 11.9), QPointF(13.8, 13.5), QPointF(11, 15.1)])
    elif name == "webhook":  # two links of a chain
        p.drawArc(QRectF(3, 8, 10, 8), 60 * 16, 240 * 16)
        p.drawArc(QRectF(11, 8, 10, 8), 240 * 16, 240 * 16)
        p.drawLine(QPointF(9, 12), QPointF(15, 12))
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
        tinted = ("wix", "wordpress", "webhook", "email", "discord", "slack", "pushover")
        color = "accent" if self.name in tinted and self.color == "sub" else self.color
        draw_icon(p, self.name, QRectF(0, 0, self.width(), self.height()), colors[color])
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
    """A line of the menu at the left: an icon and a name. The chosen one is tinted, with a short line
    of the gradient at its left that grows when it is chosen."""

    def __init__(self, icon, text):
        super().__init__()
        self.icon_name = icon
        self.setText(text)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(38)
        self.on = 0.0   # how far it is chosen, 0 to 1
        self.slide = glide(self, self._set, 220)
        self.toggled.connect(self._choose)

    def _set(self, t):
        self.on = t
        self.update()

    def _choose(self, checked):
        if motion and self.isVisible():
            self.slide.setDirection(QVariantAnimation.Forward if checked else QVariantAnimation.Backward)
            self.slide.start()
        else:
            self.slide.stop()
            self._set(1.0 if checked else 0.0)

    def sizeHint(self):
        return QSize(190, 38)

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on, r = self.isChecked(), QRectF(self.rect())
        p.setPen(Qt.NoPen)
        if self.underMouse() and not on:
            p.setBrush(QColor(colors["hover"]))
            p.drawRoundedRect(r, 8, 8)
        if self.on > 0:
            p.setOpacity(self.on)
            p.setBrush(QColor(colors["sel"]))
            p.drawRoundedRect(r, 8, 8)
            p.setOpacity(1)
            tall = 18 * self.on
            line = QLinearGradient(0, r.center().y() - 9, 0, r.center().y() + 9)
            line.setColorAt(0, QColor(colors["g2"]))
            line.setColorAt(1, QColor(colors["g3"]))
            p.setBrush(line)
            p.drawRoundedRect(QRectF(0, r.center().y() - tall / 2, 3, tall), 1.5, 1.5)
        color = colors["accent" if on else "sub"]
        draw_icon(p, self.icon_name, QRectF(12, 9, 20, 20), color)
        font = self.font()
        font.setWeight(QFont.DemiBold if on else QFont.Normal)
        p.setFont(font)
        p.setPen(QColor(colors["text" if on else "sub"]))
        p.drawText(self.rect().adjusted(44, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()


class Switch(QAbstractButton):
    """An on / off switch. On, its track is the buttons' gradient; the knob slides across."""

    def __init__(self, on=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(on)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 22)
        self.at = 1.0 if on else 0.0   # where the knob is, 0 (off) to 1 (on)
        self.slide = glide(self, self._set, 150)
        self.toggled.connect(self._switch)

    def _set(self, t):
        self.at = t
        self.update()

    def _switch(self, checked):
        if motion and self.isVisible():
            self.slide.setDirection(QVariantAnimation.Forward if checked else QVariantAnimation.Backward)
            self.slide.start()
        else:
            self.slide.stop()
            self._set(1.0 if checked else 0.0)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(colors["track"]))
        p.drawRoundedRect(QRectF(0, 0, 40, 22), 11, 11)
        if self.at > 0:
            p.setOpacity(self.at)
            p.setBrush(gradient(0, 40, "btn1", "btn2"))
            p.drawRoundedRect(QRectF(0, 0, 40, 22), 11, 11)
            p.setOpacity(1)
        p.setBrush(mix(colors["knob"], "white", self.at))
        p.drawEllipse(QPointF(11 + 18 * self.at, 11), 8, 8)
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
        p.fillRect(QRectF(0, 0, self.width(), 20), QColor(colors["off"]) if self.dim
                   else gradient(0, self.width(), "btn1", "btn2"))
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


class Dot(Moving):
    """A small round light: green when the app is watching, grey when not. While it is green a ring
    spreads from it now and then, like the light of something that is on."""

    def __init__(self, color="ok"):
        super().__init__()
        self.color, self.ring = color, 0.0
        self.setFixedSize(18, 18)

    def set_color(self, color):
        self.color = color
        self.wake()
        self.update()

    def wanted(self):
        return self.color == "ok"

    def tick(self, seconds):
        self.ring = (seconds % 2.8) / 2.8

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        color = QColor(colors[self.color])
        if self.moving and self.ring < 0.6:
            part = self.ring / 0.6
            ring = QColor(color)
            ring.setAlphaF(0.45 * (1 - part))
            p.setBrush(ring)
            p.drawEllipse(QPointF(9, 9), 4 + 5 * part, 4 + 5 * part)
        p.setBrush(color)
        p.drawEllipse(QPointF(9, 9), 4, 4)
        p.end()
