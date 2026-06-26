#  hud.py Copyright (c) 2026 Nikki Cooper
#
#  This program and the accompanying materials are made available under the
#  terms of the GNU Lesser General Public License, version 3.0 which is available at
#  https://www.gnu.org/licenses/gpl-3.0.html#license-text
#
"""
HUD - Fullscreen On-Screen Controller
Icon layout mirrors pyVid2's VideoPlayBar. Icons loaded from
~/.local/share/pyVid2-qt/Resources/, fonts from ~/.local/share/pyVid2-qt/fonts/
"""

import os

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
                                QSlider, QToolTip, QApplication, QStackedWidget)
from PySide6.QtCore import Qt, QTimer, QPoint, QSize, QObject, QEvent
from PySide6.QtGui import (QPainter, QColor, QLinearGradient, QBrush,
                            QPixmap, QIcon, QFontDatabase, QPen,
                            QPainterPath, QFont, QFontMetrics)

# ── Resource paths ─────────────────────────────────────────────────────────
RESOURCES_DIR = os.path.expanduser("~/.local/share/pyVid2-qt/Resources/")
FONT_DIR      = os.path.expanduser("~/.local/share/pyVid2-qt/fonts/")

# ── Palette ─────────────────────────────────────────────────────────────────
DODGERBLUE  = QColor(30, 144, 255)    # HUD border + icon hover
DODGERBLUE4 = QColor(16,  78, 139)    # tooltip background

HIDE_DELAY_MS    = 1125
HUD_HEIGHT_RATIO = 0.065    # 6.5 % of screen height  (~140 px 4K, ~70 px 1080p)

# ── Font families ─────────────────────────────────────────────────────────
FF_CONDENSED  = "'Roboto Condensed','RobotoCondensed','Roboto',sans-serif"
FF_BOLD       = "'Roboto Bold','Roboto',sans-serif"
FF_MONTSERRAT = "'Montserrat',sans-serif"

# ── pyVid2 colour palette (from displayVideoInfo) ─────────────────────────
C_STATUS_PLAY   = "rgb(255,255,255)"   # white   — Playing
C_STATUS_PAUSE  = "rgb(255,255,0)"     # yellow  — Paused
C_FILENUM       = "rgb(255,0,255)"     # magenta — "N of Total:"
C_FILENAME_NORM = "rgb(255,170,0)"     # orange-amber — not looping
C_FILENAME_LOOP = "rgb(0,255,255)"     # aqua    — looping
C_ORG_DUR       = "rgb(255,0,255)"     # magenta — original duration
C_ARROW         = "rgb(0,255,255)"     # cyan    — "→" separator
C_EFF_DUR       = "rgb(255,130,71)"    # sienna1 — effective duration
C_SPEED_1X      = "rgb(255,255,0)"     # yellow  — [1X]
C_SPEED_NX      = "rgb(255,0,0)"       # red     — [NX] when N ≠ 1
C_POSITION      = "rgb(0,210,0)"       # green   — wall-clock position

_fonts_registered = False
_tooltip_styled   = False


# ── Tooltip event filter ───────────────────────────────────────────────────

class _AboveToolTipFilter(QObject):
    """
    Shows tooltip above the widget on mouse enter, no window focus required.

    Qt only generates QEvent.ToolTip when the application has input focus,
    which means tooltips silently break on a non-active window (even though
    hover highlighting works fine).  We use QEvent.Enter instead — that event
    fires regardless of focus, as evidenced by icon hover-highlights working.

    Position: reference point is placed one button-height above the widget
    top-centre.  Qt renders the tooltip near that point, keeping it clear of
    the icon itself.
    """

    def eventFilter(self, obj, event):
        t = event.type()
        if t in (QEvent.Type.Enter, QEvent.Type.ToolTip):
            tip = obj.toolTip() if hasattr(obj, 'toolTip') else ""
            if tip:
                # One full button-height above the widget top-centre
                pos = obj.mapToGlobal(QPoint(obj.width() // 2, -obj.height()))
                QToolTip.showText(pos, tip, obj)
            return t == QEvent.Type.ToolTip   # consume ToolTip; pass Enter through
        elif t == QEvent.Type.Leave:
            QToolTip.hideText()
        return super().eventFilter(obj, event)


# ── Module-level helpers ───────────────────────────────────────────────────

def _register_fonts():
    for fname in ('RobotoCondensed-Regular.ttf', 'RobotoCondensed-Italic.ttf',
                  'Roboto-Bold.ttf', 'Roboto-BoldItalic.ttf', 'Montserrat-Bold.ttf'):
        path = FONT_DIR + fname
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)


def _apply_tooltip_style(screen_h):
    global _tooltip_styled
    if _tooltip_styled:
        return
    tooltip_fs = max(11, int(screen_h * 0.010))
    app = QApplication.instance()
    if app:
        app.setStyleSheet(app.styleSheet() + f"""
            QToolTip {{
                background-color: rgb(16, 78, 139);        
                color: white;
                border: 2px solid rgb(30, 144, 255);        
                border-radius: 8px;
                font-family: {FF_MONTSERRAT};
                font-weight: bold;
                font-size: {tooltip_fs}px;
                padding: 2px 6px;
            }}
        """)
    _tooltip_styled = True


def _load_icon(filename, size):
    """Load icon from RESOURCES_DIR scaled to size×size. Returns None if file missing."""
    path = RESOURCES_DIR + filename
    if not os.path.exists(path):
        return None
    if filename.lower().endswith('.svg'):
        pm = QIcon(path).pixmap(QSize(size, size))
        return pm if not pm.isNull() else None
    return QPixmap(path).scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation
    )


def _format_time(ms):
    """HH:MM:SS — H portion omitted when zero."""
    total_s = max(0, int(ms) // 1000)
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def _duration_html(duration_ms, speed):
    """
    Rich-text HTML for the duration+speed field, matching pyVid2 colours.
      1X:  '10:00 [1X]'             magenta + yellow
      NX:  '10:00→05:00 [2X]'       magenta + cyan arrow + sienna1 + red
    """
    if duration_ms <= 0:
        return ""
    dur = _format_time(duration_ms)
    spd = int(speed) if float(speed).is_integer() else speed
    speed_color = C_SPEED_1X if abs(speed - 1.0) < 0.01 else C_SPEED_NX
    speed_html  = f' <span style="color:{speed_color}">[{spd}X]</span>'
    if abs(speed - 1.0) < 0.01:
        return f'<span style="color:{C_ORG_DUR}">{dur}</span>{speed_html}'
    eff = _format_time(int(duration_ms / speed))
    return (f'<span style="color:{C_ORG_DUR}">{dur}</span>'
            f'<span style="color:{C_ARROW}">→</span>'
            f'<span style="color:{C_EFF_DUR}">{eff}</span>'
            f'{speed_html}')


# ── Help overlay ──────────────────────────────────────────────────────────

_HELP_KEYS = [
    ("Esc / Q",    "Quit"),
    ("Space",      "Play / Pause"),
    ("N",          "Next Video"),
    ("P",          "Previous Video"),
    ("+ / =",      "Speed Up"),
    ("-",          "Speed Down"),
    ("←",          "Seek Back 10 sec"),
    ("→",          "Seek Forward 10 sec"),
    ("↑",          "Increase Volume by 5%"),
    ("↓",          "Decrease Volume by 5%"),
    ("M",          "Mute / Unmute"),
    ("L",          "Repeat Video On / Off"),
    ("R",          "Restart Video"),
    ("S",          "Screenshot"),
    ("H",          "This Help Window"),
    ("O",          "Toggle OSD"),
    ("J",          "shuffle playlist"),
    ("G",          "Greyscale On / Off"),
    ("T",          "Toggle Video Title"),
    ("(,)",        "Print master playlist to console"),
    ("(.)",        "Save master playlist to file"),
    ("INS",        "Show Metadata Info"),
]


class HelpOverlay(QWidget):
    """
    Semi-transparent keyboard-shortcut reference overlay.
    Painted with the same navy/DodgerBlue palette as HUD/OSD.
    Click anywhere or press H/Esc to close.
    """

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        screen_h = main_window.screen().geometry().height()
        title_fs = max(16, int(screen_h * 0.018))
        row_fs   = max(13, int(screen_h * 0.014))

        # Build rich-text HTML table
        key_col  = "rgb(30,144,255)"    # DodgerBlue for hotkeys
        desc_col = "rgb(255,255,255)"   # white for descriptions
        pad      = "padding: 2px 18px 2px 4px;"
        ff       = FF_CONDENSED

        rows_html = "".join(
            f'<tr>'
            f'<td style="color:{key_col}; font-family:{ff}; font-size:{row_fs}px; '
            f'font-weight:bold; {pad}">{key}</td>'
            f'<td style="color:{desc_col}; font-family:{ff}; font-size:{row_fs}px; '
            f'{pad}">{desc}</td>'
            f'</tr>'
            for key, desc in _HELP_KEYS
        )

        title_html = (
            f'<div style="font-family:{FF_MONTSERRAT}; font-size:{title_fs}px; '
            f'color:rgb(255,255,255); font-weight:bold; text-align:center; '
            f'margin-bottom:10px;">Keyboard Shortcuts</div>'
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 30, 50, 30)

        lbl = QLabel()
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        lbl.setStyleSheet("background: transparent;")
        lbl.setText(
            f'<html><body>{title_html}'
            f'<table cellspacing="0" cellpadding="0">{rows_html}</table>'
            f'</body></html>'
        )
        layout.addWidget(lbl)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(8, 20, 60, 210))
        painter.setPen(QPen(QColor(30, 144, 255, 220), 2))  # DodgerBlue4
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)

    def mousePressEvent(self, event):
        self.mw.show_menu()   # advance to next state

    def reposition(self):
        """Center over the main window."""
        self.adjustSize()
        gp = self.mw.mapToGlobal(self.mw.rect().center())
        self.move(gp.x() - self.width() // 2, gp.y() - self.height() // 2)


class RemoteOverlay(QWidget):
    """
    Displays the IR remote control image (remote-245x700.png) at native size.
    Background is fully transparent — the PNG alpha shows through.
    Click anywhere to advance the help cycle.
    """

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("background: transparent;")

        path = RESOURCES_DIR + "remote-245x700.png"
        if os.path.exists(path):
            pm = QPixmap(path)
            lbl.setPixmap(pm)
            self.setFixedSize(pm.size())
        else:
            lbl.setText("remote image not found")

        layout.addWidget(lbl)

    def mousePressEvent(self, event):
        self.mw.show_menu()   # advance to next state

    def reposition(self):
        """Center over the main window."""
        gp = self.mw.mapToGlobal(self.mw.rect().center())
        self.move(gp.x() - self.width() // 2, gp.y() - self.height() // 2)


# ── Current position OSD ──────────────────────────────────────────────────

class CurPosOsd(QWidget):
    """
    Always-visible current-position counter anchored to the upper-left corner.

    Three states (cycled by toggle_curpos_osd() in MainWindow):
        0 — hidden
        1 — wall-clock position only            "03:47"
        2 — wall-clock position / eff. duration "03:47 / 12:35"

    State 1 fades DodgerBlue → hotpink in the final 20 wall-clock seconds.
    State 2 always DodgerBlue (duration is visible, warning is redundant).
    Font: luximb.ttf (Luxi Mono Bold). Outline: DodgerBlue4.
    """

    _HOTPINK     = QColor(255, 105, 180)
    _DODGERBLUE  = QColor( 30, 144, 255)
    _DODGERBLUE4 = QColor( 16,  78, 139)

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        screen_h = main_window.screen().geometry().height()
        px = max(32, int(screen_h * 0.036))   # ~77 px at 2160p, ~39 px at 1080p

        font_path = FONT_DIR + "luximb.ttf"
        fid = QFontDatabase.addApplicationFont(font_path) if os.path.exists(font_path) else -1
        families = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        family   = families[0] if families else "monospace"

        self._font = QFont(family)
        self._font.setPixelSize(px)

        fm = QFontMetrics(self._font)
        max_w          = fm.horizontalAdvance("00:00:00 / 00:00:00")
        self._pad_x    = 12
        self._pad_y    = 8
        self._baseline = self._pad_y + fm.ascent()
        self.setFixedSize(max_w + self._pad_x * 2, fm.height() + self._pad_y * 2)

        self._position_ms = 0
        self._duration_ms = 0

        self.hide()

    # ── Data feed (called every second by _tick_position) ─────────────────

    def refresh(self, position_ms: int, duration_ms: int):
        self._position_ms = position_ms
        self._duration_ms = duration_ms
        self.update()

    # ── Positioning ───────────────────────────────────────────────────────

    def reposition(self):
        gp = self.mw.mapToGlobal(QPoint(15, 15))
        self.move(gp)

    # ── Paint ─────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        state = self.mw._curpos_state
        if state == 0:
            return

        speed  = self.mw._speed
        pos_ms = self._position_ms
        dur_ms = self._duration_ms

        pos_str = _format_time(pos_ms)

        if state == 2 and dur_ms > 0:
            eff_dur = int(dur_ms / speed) if speed > 0 else dur_ms
            text = f"{pos_str} / {_format_time(eff_dur)}"
        else:
            text = pos_str

        # Color: state 1 fades in final 20 wall-clock seconds; state 2 stays blue
        text_color = self._DODGERBLUE
        if state == 1 and dur_ms > 0:
            eff_dur   = int(dur_ms / speed) if speed > 0 else dur_ms
            remaining = eff_dur - pos_ms
            if remaining < 20_000:
                t = max(0.0, min(1.0, (20_000 - remaining) / 20_000))
                text_color = QColor(
                    int( 30 + t * (255 -  30)),
                    int(144 + t * (105 - 144)),
                    int(255 + t * (180 - 255)),
                )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addText(self._pad_x, self._baseline, self._font, text)

        # Outline pass
        pen = QPen(self._DODGERBLUE4, 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Fill pass
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(text_color)
        painter.drawPath(path)


# ── HUD widget ─────────────────────────────────────────────────────────────

class HUD(QWidget):
    """
    Fullscreen bottom-bar HUD.
    Appears on mouse entry into the bottom activation zone.
    Auto-hides after HIDE_DELAY_MS; hover suspends the timer.
    """

    def __init__(self, main_window):
        super().__init__(main_window)   # parent → WM_TRANSIENT_FOR
        self.mw = main_window

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        global _fonts_registered
        if not _fonts_registered:
            _register_fonts()
            _fonts_registered = True

        screen = self.mw.screen().geometry()
        _apply_tooltip_style(screen.height())

        # Scale to screen
        self._hud_height = max(70,  int(screen.height() * HUD_HEIGHT_RATIO))
        self._icon_sz    = max(32,  int(self._hud_height * 0.65))
        self._fs         = max(16,  int(screen.height() * 0.016))    # base font px
        self._fs_pos     = max(18,  int(self._fs * 1.15))             # position label slightly larger
        self._vol_w      = max(80,  int(screen.width()  * 0.06))

        # Internal state
        self._filter_visible = False
        self._is_repeating   = False
        self._is_muted       = False
        self._seek_dragging  = False
        self._last_seek_val  = 0

        # Shared tooltip-above filter for all icon buttons
        self._tooltip_filter = _AboveToolTipFilter(self)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._opacity_hide)
        self.pinned = False   # set True by IR HUD button: disables auto-hide and mouse-driven hide

        self._load_icons()
        self._build_ui()
        # NOT shown here — _init_overlays() in MainWindow handles initial mapping

    # ──────────────────────────────────────────────
    # Icon loading
    # ──────────────────────────────────────────────

    def _load_icons(self):
        sz = self._icon_sz
        self._icon_play         = _load_icon("play.png",                 sz)
        self._icon_pause        = _load_icon("pause.png",                sz)
        self._icon_exit         = _load_icon("exit.png",                 sz)
        self._icon_previous     = _load_icon("previous.png",             sz)
        self._icon_next         = _load_icon("next.png",                 sz)
        self._icon_plus         = _load_icon("plus.png",                 sz)
        self._icon_minus        = _load_icon("minus.png",                sz)
        self._icon_repeat       = _load_icon("repeat.png",               sz)
        self._icon_repeat_white = _load_icon("repeat_white.png",         sz)
        self._icon_restart      = _load_icon("video-restart.png",        sz)
        self._icon_screenshot   = _load_icon("camera.svg",               sz)
        self._icon_filter_on    = _load_icon("Filter-Alt-ON-48x48.png",  sz)
        self._icon_filter_off   = _load_icon("Filter-Alt-OFF-48x48.png", sz)
        self._icon_volume       = _load_icon("volume.png",               sz)
        self._icon_mute         = _load_icon("mute.png",                 sz)
        self._icon_info         = _load_icon("faq.png",                  sz)

    # ──────────────────────────────────────────────
    # UI construction helpers
    # ──────────────────────────────────────────────

    def _icon_btn(self, pixmap, tooltip=""):
        """Flat icon-only QPushButton with a subtle DodgerBlue hover."""
        btn = QPushButton()
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        sz  = self._icon_sz
        pad = max(4, sz // 10)
        btn.setFixedSize(sz + pad * 2, sz + pad * 2)
        if pixmap:
            btn.setIcon(QIcon(pixmap))
            btn.setIconSize(QSize(sz, sz))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
            }}
            QPushButton:hover {{
                background: rgba(30, 144, 255, 60); 
                border-radius: {pad + 2}px;
            }}
        """)
        btn.installEventFilter(self._tooltip_filter)
        return btn

    def _text_lbl(self, text="", color="rgb(255,255,255)", bold=False,
                  font_family=None, font_size=None,
                  align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft):
        lbl = QLabel(text)
        ff     = font_family or FF_CONDENSED
        fs     = font_size   or self._fs
        weight = "bold" if bold else "normal"
        lbl.setStyleSheet(
            f"color:{color}; font-family:{ff}; "
            f"font-size:{fs}px; font-weight:{weight}; background:transparent;"
        )
        lbl.setAlignment(align)
        return lbl

    # ──────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────

    def _build_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(2)
        self.setLayout(layout)

        # ── Icon buttons (left → right per spec) ──────────────────────────
        self.btn_play_pause = self._icon_btn(self._icon_play,        "Play / Pause")
        self.btn_exit       = self._icon_btn(self._icon_exit,        "Quit")
        self.btn_previous   = self._icon_btn(self._icon_previous,    "Previous")
        self.btn_next       = self._icon_btn(self._icon_next,        "Next")
        self.btn_plus       = self._icon_btn(self._icon_plus,        "Speed +")
        self.btn_minus      = self._icon_btn(self._icon_minus,       "Speed -")
        self.btn_repeat     = self._icon_btn(self._icon_repeat,      "Repeat Video")
        self.btn_restart    = self._icon_btn(self._icon_restart,     "Restart Video")
        self.btn_screenshot = self._icon_btn(self._icon_screenshot,  "Screenshot")
        self.btn_filter     = self._icon_btn(self._icon_filter_on,   "Filter Panel")
        self.btn_help       = self._icon_btn(self._icon_info,        "Help")

        self.btn_play_pause.clicked.connect(self.mw.toggle_play_pause)
        self.btn_exit.clicked.connect(self.mw.close)
        self.btn_previous.clicked.connect(self.mw.play_previous)
        self.btn_next.clicked.connect(self.mw.play_next)
        self.btn_plus.clicked.connect(self.mw.speed_up)
        self.btn_minus.clicked.connect(self.mw.speed_down)
        self.btn_repeat.clicked.connect(self.mw.toggle_repeat)
        self.btn_restart.clicked.connect(self.mw.restart_video)
        self.btn_screenshot.clicked.connect(self.mw.take_screenshot)
        self.btn_filter.clicked.connect(self._toggle_filter)
        self.btn_help.clicked.connect(self.mw.show_menu)

        for btn in (self.btn_play_pause, self.btn_exit, self.btn_previous, self.btn_next,
                    self.btn_plus, self.btn_minus, self.btn_repeat, self.btn_restart,
                    self.btn_screenshot, self.btn_filter, self.btn_help):
            layout.addWidget(btn)

        layout.addSpacing(10)

        # ── Centre stack: info page  ↔  seek-slider page ─────────────────
        # Hovering over the info area swaps to a seek slider; leaving reverts.
        self._centre_stack = QStackedWidget()
        self._centre_stack.setSizePolicy(
            self._centre_stack.sizePolicy().horizontalPolicy(),
            self._centre_stack.sizePolicy().verticalPolicy()
        )

        # ── Page 0: info labels ───────────────────────────────────────────
        info_page = QWidget()
        info_layout = QHBoxLayout(info_page)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        # "Playing" white / "Paused" yellow — fixed width prevents layout jump
        self.lbl_status = self._text_lbl("", color=C_STATUS_PLAY)
        self.lbl_status.setFixedWidth(max(80, self._fs * 5))
        info_layout.addWidget(self.lbl_status)

        # "N of Total:  " — magenta, no stretch
        self.lbl_filenum = self._text_lbl("", color=C_FILENUM)
        info_layout.addWidget(self.lbl_filenum)

        # "VideoName" — orange-amber (or aqua when looping), no stretch
        self.lbl_filename = self._text_lbl("No playlist loaded", color=C_FILENAME_NORM)
        info_layout.addWidget(self.lbl_filename)

        # Duration + speed rich-text: sits directly after filename
        self.lbl_duration = QLabel()
        self.lbl_duration.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_duration.setStyleSheet(
            f"font-family:{FF_CONDENSED}; font-size:{self._fs}px; background:transparent;"
        )
        self.lbl_duration.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        info_layout.addWidget(self.lbl_duration)

        info_layout.addSpacing(12)

        # Wall-clock position — green, Roboto-Bold, slightly larger
        self.lbl_position = self._text_lbl(
            "00:00", color=C_POSITION,
            bold=True, font_family=FF_BOLD, font_size=self._fs_pos,
            align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )
        self.lbl_position.setFixedWidth(max(70, self._fs_pos * 4))
        info_layout.addWidget(self.lbl_position)
        info_layout.addStretch(1)

        info_page.setMouseTracking(True)
        info_page.installEventFilter(self)   # hover → swap to seek page

        # ── Page 1: seek slider ───────────────────────────────────────────
        seek_page = QWidget()
        seek_layout = QHBoxLayout(seek_page)
        seek_layout.setContentsMargins(8, 0, 8, 0)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1)
        self.seek_slider.setValue(0)
        self.seek_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.seek_slider.setToolTip("Seek")
        self.seek_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(200,200,200,100);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: rgb(30,144,255);
                width: 14px; height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: rgb(30,144,255);
                border-radius: 3px;
            }
        """)
        from PySide6.QtWidgets import QSizePolicy
        self.seek_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.seek_slider.setFixedWidth(max(200, int(self._vol_w * 4)))
        self.seek_slider.setMouseTracking(True)   # hover tooltips without button press
        self.seek_slider.installEventFilter(self)
        seek_layout.addWidget(self.seek_slider)
        seek_layout.addSpacing(max(20, self._icon_sz + self._vol_w + 20))  # gap matching speaker+vol width

        seek_page.setMouseTracking(True)
        seek_page.installEventFilter(self)   # leave → swap back to info page

        self._centre_stack.addWidget(info_page)   # index 0
        self._centre_stack.addWidget(seek_page)   # index 1
        self._info_page = info_page
        self._seek_page = seek_page
        layout.addWidget(self._centre_stack, stretch=1)

        # ── Speaker + volume slider (placeholder) ─────────────────────────
        self.btn_speaker = self._icon_btn(self._icon_volume, "Mute / Unmute")
        self.btn_speaker.clicked.connect(self.mw.toggle_mute)
        layout.addWidget(self.btn_speaker)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(0)
        self.vol_slider.setFixedWidth(self._vol_w)
        self.vol_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol_slider.setToolTip("Volume: 0%")
        self.vol_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(200,200,200,100);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: rgb(30,144,255);
                width: 14px; height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: rgb(30,144,255);
                border-radius: 3px;
            }
        """)
        self.vol_slider.sliderMoved.connect(self._on_vol_slider_moved)
        self.vol_slider.installEventFilter(self)
        layout.addWidget(self.vol_slider)

    # ──────────────────────────────────────────────
    # State updates
    # ──────────────────────────────────────────────

    def update_state(self, filename="", index=0, total=0, speed=2.0,
                     is_paused=False, is_repeating=False,
                     duration_ms=0, position_ms=0):
        """Refresh all labels and toggle icons to reflect current playback state."""
        self._is_repeating = is_repeating

        # Play/Pause icon
        icon = self._icon_pause if is_paused else self._icon_play
        if icon:
            self.btn_play_pause.setIcon(QIcon(icon))

        # Repeat icon (white variant = repeat active)
        rep = self._icon_repeat_white if is_repeating else self._icon_repeat
        if rep:
            self.btn_repeat.setIcon(QIcon(rep))

        # Status label — white when playing, yellow + bold when paused
        if is_paused:
            self.lbl_status.setText("Paused")
            self.lbl_status.setStyleSheet(
                f"color:{C_STATUS_PAUSE}; font-family:{FF_CONDENSED}; "
                f"font-size:{self._fs}px; font-weight:bold; background:transparent;")
        else:
            self.lbl_status.setText("Playing")
            self.lbl_status.setStyleSheet(
                f"color:{C_STATUS_PLAY}; font-family:{FF_CONDENSED}; "
                f"font-size:{self._fs}px; font-weight:normal; background:transparent;")

        # File number + name
        if filename:
            name        = os.path.splitext(filename)[0]
            fname_color = C_FILENAME_LOOP if is_repeating else C_FILENAME_NORM
            fname_weight = "bold" if is_repeating else "normal"
            self.lbl_filenum.setText(f"{index} of {total}:  " if total else "")
            self.lbl_filename.setText(name)
            self.lbl_filename.setStyleSheet(
                f"color:{fname_color}; font-family:{FF_CONDENSED}; "
                f"font-size:{self._fs}px; font-weight:{fname_weight}; background:transparent;")
        else:
            self.lbl_filenum.setText("")
            self.lbl_filename.setText("No playlist loaded")
            self.lbl_filename.setStyleSheet(
                f"color:{C_FILENAME_NORM}; font-family:{FF_CONDENSED}; "
                f"font-size:{self._fs}px; font-weight:normal; background:transparent;")

        # Duration + speed (rich HTML)
        self.lbl_duration.setText(_duration_html(duration_ms, speed))

        # Wall-clock position
        self.lbl_position.setText(
            _format_time(position_ms) if (position_ms > 0 or duration_ms > 0) else "00:00"
        )

    # ──────────────────────────────────────────────
    # Mute toggle
    # ──────────────────────────────────────────────

    def _show_seek_page(self):
        if self._centre_stack.currentIndex() != 1:
            self._centre_stack.setCurrentIndex(1)

    def _show_info_page(self):
        if self._centre_stack.currentIndex() != 0:
            self._centre_stack.setCurrentIndex(0)

    def update_seek_slider(self, position_ms: int, duration_ms: int) -> None:
        """Called from _tick_position; only moves handle when not dragging."""
        if duration_ms > 0 and self.seek_slider.maximum() != duration_ms:
            self.seek_slider.setRange(0, duration_ms)
        if not self._seek_dragging and duration_ms > 0:
            self.seek_slider.setValue(position_ms)
            pct = int(position_ms * 100 / duration_ms)
            self.seek_slider.setToolTip(f"Seek  {pct}%")

    def _seek_pos_from_mouse(self, x: int) -> int:
        """Convert mouse X coordinate on seek_slider to position_ms."""
        dur = self.seek_slider.maximum()
        if dur <= 0:
            return 0
        half_handle = 7   # handle radius (stylesheet: width:14px, border-radius:7px)
        usable_w = max(1, self.seek_slider.width() - half_handle * 2)
        rel_x = max(0, min(x - half_handle, usable_w))
        return int(rel_x * dur / usable_w)

    def _seek_osd(self, value: int, forward: bool = True) -> None:
        dur = self.seek_slider.maximum()
        if dur <= 0:
            return
        pct = int(value * 100 / dur)
        bar_filled = pct // 5
        bar_empty  = 20 - bar_filled
        bar = (f'<span style="color:rgb(30,144,255)">{"█" * bar_filled}</span>'
               f'<span style="color:rgba(200,200,200,120)">{"░" * bar_empty}</span>')
        h, m, s = value // 3600000, (value % 3600000) // 60000, (value % 60000) // 1000
        time_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        icon = "►► " if forward else "◄◄ "
        self.mw.show_osd(
            f'<span style="color:white">{icon}{pct:3d}%  </span>{bar}'
            f'<span style="color:white">  {time_str}</span>',
            duration_ms=1200)

    def set_volume(self, pct: int) -> None:
        """Update the slider position and tooltip to reflect current volume (0–100)."""
        self.vol_slider.setValue(pct)
        self.vol_slider.setToolTip(f"Volume: {pct}%")

    def _on_vol_slider_moved(self, value: int) -> None:
        """User dragged the slider — apply volume and show OSD bar."""
        self.mw._apply_volume(value)

    def set_muted(self, is_muted):
        """Update the speaker icon to reflect mute state."""
        self._is_muted = is_muted
        icon = self._icon_mute if is_muted else self._icon_volume
        if icon:
            self.btn_speaker.setIcon(QIcon(icon))

    # ──────────────────────────────────────────────
    # Filter toggle (placeholder)
    # ──────────────────────────────────────────────

    def _toggle_filter(self):
        self._filter_visible = not self._filter_visible
        icon = self._icon_filter_off if self._filter_visible else self._icon_filter_on
        if icon:
            self.btn_filter.setIcon(QIcon(icon))
        self.mw.show_osd("Filter Panel — TODO", duration_ms=1500)

    # ──────────────────────────────────────────────
    # Visibility / positioning
    # ──────────────────────────────────────────────

    def _opacity_hide(self):
        self.setWindowOpacity(0.0)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def show_hud(self):
        if not self.isVisible():
            self.show()
        self._reposition()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setWindowOpacity(1.0)
        self.hide_timer.stop()
        if not self.pinned:
            self.hide_timer.start(HIDE_DELAY_MS)

    def hide_hud(self):
        """Immediately hide the HUD (used by pin toggle)."""
        self.hide_timer.stop()
        self._opacity_hide()

    def _reposition(self):
        global_pos = self.mw.mapToGlobal(QPoint(0, self.mw.height() - self._hud_height))
        self.resize(self.mw.width(), self._hud_height)
        self.move(global_pos)

    # ──────────────────────────────────────────────
    # Mouse-over: pause / resume hide timer
    # ──────────────────────────────────────────────

    def enterEvent(self, event):
        self.hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.pinned:
            self.hide_timer.start(HIDE_DELAY_MS)
        super().leaveEvent(event)

    def eventFilter(self, obj, event):
        t = event.type()

        # Volume slider: wheel → smooth OSD feedback
        if hasattr(self, 'vol_slider') and obj is self.vol_slider and t == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta > 0:
                self.mw.vol_up()
            elif delta < 0:
                self.mw.vol_down()
            return True   # consume — don't let QSlider also move

        # Seek slider: full mouse handling
        if hasattr(self, 'seek_slider') and obj is self.seek_slider:
            if t == QEvent.Type.Wheel:
                delta = event.angleDelta().y()
                if delta > 0:
                    self.mw.seek_forward()
                elif delta < 0:
                    self.mw.seek_backward()
                return True

            if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                old_val = self.seek_slider.value()
                new_val = self._seek_pos_from_mouse(int(event.position().x()))
                self._seek_dragging = True
                self._last_seek_val = new_val
                self.seek_slider.setValue(new_val)
                self.mw.video_widget.player.setPosition(new_val)
                self._seek_osd(new_val, forward=(new_val >= old_val))
                return True

            if t == QEvent.Type.MouseMove:
                x = int(event.position().x())
                dur = self.seek_slider.maximum()
                if dur > 0:
                    hover_pos = self._seek_pos_from_mouse(x)
                    pct = int(hover_pos * 100 / dur)
                    gp = self.seek_slider.mapToGlobal(
                        QPoint(x, -int(self.seek_slider.height() * 0.8)))
                    QToolTip.showText(gp, f"{pct}%", self.seek_slider)
                if event.buttons() & Qt.MouseButton.LeftButton and self._seek_dragging:
                    new_val = self._seek_pos_from_mouse(x)
                    self.seek_slider.setValue(new_val)
                    self.mw.video_widget.player.setPosition(new_val)
                    self._seek_osd(new_val, forward=(new_val >= self._last_seek_val))
                    self._last_seek_val = new_val
                    return True   # consume drag — don't let QSlider process it
                return False      # hover-only — let QSlider handle cursor/highlight

            if t == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                if self._seek_dragging:
                    self._seek_dragging = False
                    new_val = self._seek_pos_from_mouse(int(event.position().x()))
                    self.seek_slider.setValue(new_val)
                    self.mw.video_widget.player.setPosition(new_val)
                return True

            if t == QEvent.Type.Leave:
                QToolTip.hideText()
                return False

        # Info page: mouse enters → swap to seek slider
        if hasattr(self, '_info_page') and obj is self._info_page and t == QEvent.Type.Enter:
            self._show_seek_page()
            return False

        # Seek page: mouse leaves (and not dragging) → swap back to info
        if hasattr(self, '_seek_page') and obj is self._seek_page and t == QEvent.Type.Leave:
            if not self._seek_dragging:
                self._show_info_page()
            return False

        return super().eventFilter(obj, event)

    # ──────────────────────────────────────────────
    # Custom paint — gradient + DodgerBlue border
    # ──────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor( 8,  20,  60, 200))
        gradient.setColorAt(1.0, QColor(16,  40, 100, 230))
        painter.fillRect(self.rect(), QBrush(gradient))

        w, h = self.width() - 1, self.height() - 1
        painter.setPen(DODGERBLUE)
        painter.drawLine(0, 0, w, 0)
        painter.drawLine(0, 0, 0, h)
        painter.drawLine(w, 0, w, h)
        painter.drawLine(0, h, w, h)
