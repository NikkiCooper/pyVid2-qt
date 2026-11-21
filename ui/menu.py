#  ui/menu.py Copyright (c) 2026 Nikki Cooper
#
#  This program and the accompanying materials are made available under the
#  terms of the GNU Lesser General Public License, version 3.0 which is available at
#  https://www.gnu.org/licenses/gpl-3.0.html#license-text
#
"""
Remote-friendly menu system.

    IR A / F1  →  Main Menu          IR B / F2  →  Playlists
    IR C / F3  →  Common Controls    IR D / F4  →  Configuration

While a menu is open:
    1-9            select an item             (IR digits, keyboard digits, or mouse click)
    0              Back  (closes at a root menu)
    REW / FWD      page through long lists    (keyboard: ←/→ or PgUp/PgDn; mouse wheel)
                   — only on a menu with several pages; otherwise they seek as usual.
    Esc            close                      (keyboard)
    same colour button again closes; another colour button switches menus.
Items that show a live value (Repeat ON/OFF, Shuffle, Mute...) run *quietly*:
the value next to the item is the feedback, so their OSD notification is
suppressed.  Actions without a value (Restart, Screenshot...) keep their OSD.

Playlist viewer (Playlists → View / Play Active Playlist):
    PLAY_NEXT / PLAY_PREV   move the highlight up / down by default — swap in
                            Configuration → Playlist Viewer Up / Down
                            (keyboard ↑/↓ always literal; mouse click)
    REW / FWD               a screenful at a time  (keyboard ←/→, PgUp/PgDn; mouse wheel)
    PLAY_PAUSE              play the highlighted video — or pause/resume if it is
                            the one already playing      (keyboard Enter/Space; double-click)
    0                       Back
Playing an entry *jumps* to it within the active playlist; the next video comes
from the playlist after it.  Nothing is inserted, so no duplicates.  Entries that
are missing or fail to load are shown in red.

The menu stays up until the user closes it, or after a long idle time-out
(default 10 min, Configuration → Menu Time-out; 'Never' disables it).  Running
an item never closes it.  While the centre OSD notification is showing, the menu
is suspended (hidden, state kept) and reappears when the notification goes away.

Layout lives in the MENUS table below: each entry is a builder function that
returns a Menu.  Builders run every time the menu is drawn, so live values
(Shuffle ON/OFF, ...) and folder listings are always current.  Actions call
MainWindow methods — the menu holds no player state of its own.

The overlay never takes focus (same window attributes as the other overlays —
see the KWin "demands attention" notes in main_window/_OsdWidget), so keyboard
input stays with MainWindow, which forwards menu keys here.
"""

import os
import glob
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStyle,
                               QListWidget, QListWidgetItem, QAbstractItemView, QStyledItemDelegate)
from PySide6.QtCore import Qt, QTimer, QSize, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics

from ui.hud import FF_CONDENSED, FF_MONTSERRAT

MENU_TIMEOUT_STEPS   = [1, 2, 5, 10, 30, 60, 0]   # minutes; 0 = never
MENU_TIMEOUT_DEFAULT = 10
PAGE_REPEAT_S        = 0.35     # min gap between page turns (held REW/FWD auto-repeats ~9/s)
PAGE_SIZE       = 9          # digits 1-9; 0 is always Back
VIEW_ROWS       = 16         # playlist viewer: visible rows

ROOTS = {'A': 'main', 'B': 'playlists', 'C': 'controls', 'D': 'config'}

C_KEY      = "rgb(30,144,255)"     # DodgerBlue — [n]
C_TEXT     = "rgb(255,255,255)"
C_DIM      = "rgb(130,135,145)"    # disabled / placeholder
C_ON       = "rgb(0,210,0)"
C_OFF      = "rgb(160,160,160)"
C_SUBTITLE = "rgb(170,180,200)"
C_BAD      = "rgb(255,80,80)"      # viewer: missing / failed to load
ROLE_ENTRY = Qt.ItemDataRole.UserRole   # viewer row data: (number, marker, name, colour)
_OFF_WORDS = {"OFF", "Off", "Never", "Sorted"}


@dataclass
class Item:
    label: str
    run: Optional[Callable[[], None]] = None     # action
    submenu: Optional[str] = None                # menu id to open
    arg: object = None                           # passed to the submenu builder
    value: Optional[Callable[[], str]] = None    # live state, shown right-aligned
    enabled: Optional[Callable[[], bool]] = None
    disabled_msg: str = "Not available right now"
    todo: bool = False                           # placeholder: listed but not implemented
    quiet: Optional[bool] = None                 # suppress the action's OSD; None = quiet iff
                                                 # the item shows a live value


@dataclass
class Menu:
    title: str
    items: list = field(default_factory=list)
    subtitle: str = ""


def _on_off(flag):
    return "ON" if flag else "OFF"


# ==================== Menu definitions ====================

def _main(mw, _arg):
    return Menu("Main Menu", [
        Item("Common Controls",         submenu='controls'),
        Item("Playlists",               submenu='playlists'),
        Item("Configuration",           submenu='config'),
        Item("Load Playlist",           submenu='load',
             enabled=lambda: not mw._sub_active, disabled_msg="Exit Sub-Playlist mode first"),
        Item("Restore Master Playlist", run=mw.restore_master_playlist,
             enabled=mw.loaded_playlist_active, disabled_msg="Master playlist already active"),
        Item("Sub-Playlist (this model)", run=mw.toggle_sub_playlist, quiet=False,
             value=lambda: _on_off(mw._sub_active)),
        Item("Shuffle / Sort",          run=mw.toggle_shuffle,
             value=lambda: "Shuffle" if mw._shuffle_enabled() else "Sorted"),
        Item("Position OSD",            run=mw.toggle_curpos_osd,
             value=mw.curpos_osd_label),
        Item("Repeat Video",            run=mw.toggle_repeat,
             value=lambda: _on_off(mw._is_repeating)),
    ])


def _playlists(mw, _arg):
    return Menu("Playlists", [
        Item("Load Playlist",           submenu='load',
             enabled=lambda: not mw._sub_active, disabled_msg="Exit Sub-Playlist mode first"),
        Item("Restore Master Playlist", run=mw.restore_master_playlist,
             enabled=mw.loaded_playlist_active, disabled_msg="Master playlist already active"),
        Item("Save Master Playlist",    run=mw.save_master_playlist),
        Item("Save Sub-Playlist",       run=mw.save_sub_playlist,
             enabled=lambda: mw._sub_active, disabled_msg="Sub-Playlist mode is off"),
        Item("View / Play Active Playlist", submenu='viewer'),
        Item("Shuffle / Sort",          run=mw.toggle_shuffle,
             value=lambda: "Shuffle" if mw._shuffle_enabled() else "Sorted"),
        Item("Sub-Playlist (this model)", run=mw.toggle_sub_playlist, quiet=False,
             value=lambda: _on_off(mw._sub_active)),
    ], subtitle=f"Active: {mw.active_playlist_label()}")


def _controls(mw, _arg):
    return Menu("Common Controls", [
        Item("Position OSD",   run=mw.toggle_curpos_osd, value=mw.curpos_osd_label),
        Item("Repeat Video",   run=mw.toggle_repeat,
             value=lambda: _on_off(mw._is_repeating)),
        Item("Mute",           run=mw.toggle_mute, value=lambda: _on_off(mw._is_muted)),
        Item("Pin HUD",        run=mw.toggle_hud_pin, value=lambda: _on_off(mw._hud_pinned)),
        Item("Restart Video",  run=mw.restart_video),
        Item("Screenshot",     run=mw.take_screenshot),
        Item("Video Title",    run=mw.toggle_video_title, todo=True),
        Item("Video Metadata", run=mw.show_metadata, todo=True),
        Item("Greyscale",      run=mw.toggle_greyscale, todo=True),
    ])


def _config(mw, _arg):
    have_opts = lambda: mw.opts is not None
    o = mw.opts
    return Menu("Configuration", [
        Item("Loop Playlist  (--loop)",        run=mw.toggle_loop, enabled=have_opts,
             value=lambda: _on_off(mw._cli_loop)),
        Item("At Sub-Playlist End  (--noFilterLoop)", run=mw.toggle_filter_loop,
             enabled=have_opts,
             value=lambda: "Return to Master" if getattr(o, "noFilterLoop", False) else "Loop"),
        Item("Loop Delay  (--loopDelay)",      run=mw.cycle_loop_delay, enabled=have_opts,
             value=lambda: f"{o.loopDelay} s" if o else "—"),
        Item("Cursor Hide  (--cursorHide)",    run=mw.cycle_cursor_hide,
             value=mw.cursor_hide_label),
        Item("Screenshot Format  (--useJPG)",  run=mw.toggle_jpg, enabled=have_opts,
             value=lambda: ("JPG" if o.useJPG else "PNG") if o else "—"),
        Item("Auto Speed  (--autoSpeed)",      run=mw.toggle_auto_speed, enabled=have_opts,
             value=lambda: _on_off(getattr(o, "autoSpeed", False))),
        Item("Menu Time-out",                  run=mw.menu.cycle_timeout,
             value=mw.menu.timeout_label),
        Item("Playlist Viewer Up / Down",      run=mw.menu.toggle_viewer_buttons,
             value=mw.menu.viewer_buttons_label),
        Item("OSD/HUD Time-out, Startup & Save Settings", todo=True),
    ], subtitle="Changes apply to this session only")


def playlist_dirs():
    """[(label, path)] of existing playlist folders: $PLAYLIST_HOME first, then ~/+Playlists."""
    dirs = []
    home = os.environ.get("PLAYLIST_HOME")
    if home and os.path.isdir(os.path.expanduser(home)):
        dirs.append(("Playlist Home", os.path.expanduser(home)))
    plus = os.path.expanduser("~/+Playlists")
    if os.path.isdir(plus) and all(os.path.realpath(plus) != os.path.realpath(d) for _, d in dirs):
        dirs.append(("~/+Playlists", plus))
    return dirs


def _load(mw, _arg):
    """Folder chooser — skipped straight to the file list when only one folder exists."""
    dirs = playlist_dirs()
    if len(dirs) == 1:
        return _files(mw, dirs[0][1])
    if not dirs:
        return Menu("Load Playlist", [Item("No playlist folder found", todo=True)],
                    subtitle="Set PLAYLIST_HOME or create ~/+Playlists")
    return Menu("Load Playlist", [
        Item(label, submenu='files', arg=path,
             value=lambda p=path: f"{len(glob.glob(os.path.join(p, '*.txt')))} lists")
        for label, path in dirs
    ], subtitle="Choose a folder")


def _playing_value(mw):
    """'▶ Playing 12 of 500' — position within the loaded (acting master) playlist."""
    pos, total = mw.master_position()
    return f"▶ Playing {pos:,} of {total:,}"


def _files(mw, folder):
    paths = sorted(glob.glob(os.path.join(folder, "*.txt")), key=lambda p: os.path.basename(p).lower())
    items = [
        Item(os.path.splitext(os.path.basename(p))[0], run=(lambda p=p: mw.load_playlist_file(p)),
             value=(lambda p=p: _playing_value(mw) if mw.loaded_playlist_path() == p else ""))
        for p in paths
    ]
    if not items:
        items = [Item("No playlists (*.txt) here", todo=True)]
    return Menu("Load Playlist", items, subtitle=folder)


def _viewer(mw, _arg):
    if mw._sub_active:
        title = "Sub-Playlist: " + " + ".join(sorted(mw._sub_models))
    else:
        title = "Playlist: " + mw.active_playlist_label()
    return Menu(title, [], subtitle=f"{len(mw.playlist)} videos")


MENUS = {
    'viewer':    _viewer,         # drawn by MenuOverlay._build_viewer()
    'main':      _main,
    'playlists': _playlists,
    'controls':  _controls,
    'config':    _config,
    'load':      _load,
    'files':     _files,
}


# ==================== Widgets ====================

class _Clickable(QWidget):
    """Row container that highlights on hover and calls `on_click` when clicked."""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self._on_click()

    def paintEvent(self, event):
        if self._hover:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(30, 144, 255, 70))
            p.drawRoundedRect(self.rect(), 6, 6)


def _qcolor(css):
    """QColor from 'rgb(r,g,b)' — QColor(str) does not parse CSS rgb() syntax."""
    if css.startswith("rgb("):
        return QColor(*(int(v) for v in css[4:-1].split(",")))
    return QColor(css)


class _ViewerDelegate(QStyledItemDelegate):
    """Paints a viewer row as aligned columns — number | marker | name — in the row's colour."""

    def __init__(self, font, widest_number, parent=None):
        super().__init__(parent)
        self._font = font
        fm = QFontMetrics(font)
        self._num_w  = fm.horizontalAdvance(widest_number) + 4
        self._mark_w = fm.horizontalAdvance("▶") + 16
        self._row_h  = fm.height() + 8

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self._row_h)

    def paint(self, p, option, index):
        number, marker, name, colour = index.data(ROLE_ENTRY)
        r = option.rect
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(30, 144, 255, 110))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 5, 5)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(30, 144, 255, 45))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 5, 5)
        p.setFont(self._font)
        p.setPen(_qcolor(colour))
        x = r.x() + 8
        align = Qt.AlignmentFlag.AlignVCenter
        p.drawText(QRect(x, r.y(), self._num_w, r.height()), align | Qt.AlignmentFlag.AlignRight, number)
        x += self._num_w
        p.drawText(QRect(x, r.y(), self._mark_w, r.height()), align | Qt.AlignmentFlag.AlignHCenter, marker)
        x += self._mark_w
        name_w = r.right() - x - 6
        elided = QFontMetrics(self._font).elidedText(name, Qt.TextElideMode.ElideRight, name_w)
        p.drawText(QRect(x, r.y(), name_w, r.height()), align | Qt.AlignmentFlag.AlignLeft, elided)
        p.restore()


class MenuOverlay(QWidget):
    """The menu window plus its navigation state (a stack of open menus)."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                            | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # Notification type: KWin never flags these "demands attention" (which pins auto-hide panels)
        self.setAttribute(Qt.WidgetAttribute.WA_X11NetWmWindowTypeNotification)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        screen = main_window.screen().geometry()
        self._title_fs = max(18, int(screen.height() * 0.020))
        self._row_fs   = max(15, int(screen.height() * 0.016))
        self._small_fs = max(12, int(screen.height() * 0.012))
        self._min_width = int(screen.width() * 0.20)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 24, 36, 24)
        outer.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)   # always fit the content
        self._outer = outer
        self._content = None    # rebuilt on every render

        self._stack = []        # [[menu_id, arg, page], ...]; empty = closed
        self._items = []        # items of the page currently shown
        self._num_pages = 1
        self._list = None           # viewer QListWidget while the viewer is shown
        self._view_rows = VIEW_ROWS # visible viewer rows (reduced on small screens)
        # Viewer: which way PLAY_NEXT / PLAY_PREV move the highlight.  True (default):
        # PLAY_NEXT (the remote's up-arrow) moves UP.  Keyboard ↑/↓ are always literal.
        self.viewer_next_up = True
        self._status_lbl = None
        self._viewer_status = ""

        self.timeout_min = MENU_TIMEOUT_DEFAULT
        self._suspended  = False    # hidden while the centre OSD notification is showing
        self._suspend_gen = 0
        self._last_page  = 0.0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.close_menu)

    # ---------- navigation (called by MainWindow for IR / keyboard) ----------

    @property
    def is_open(self):
        return bool(self._stack)

    def toggle_root(self, key):
        """Colour button: open its root menu; same button again closes."""
        root = ROOTS[key]
        if self.is_open and self._stack[0][0] == root:
            self.close_menu()
            return
        self._stack = [[root, None, 0]]
        self._suspended = False
        self._render()

    def digit(self, n):
        """1-9 select on the current page; 0 = Back.  No-op while closed."""
        if not self.is_open:
            return
        self._suspended = False
        if n == 0:
            self.back()
            return
        if 1 <= n <= len(self._items):
            self._activate(self._items[n - 1])
        else:
            self._arm_timer()

    def page(self, delta):
        """
        Turn a page.  Returns True if consumed: only while the open menu has
        several pages.  Otherwise False, so REW/FWD (and ←/→) keep seeking.
        Turns are rate-limited so a held, auto-repeating REW/FWD steps at a
        readable pace; repeats inside the gap are still consumed (no stray seeks).
        """
        if self.viewer_open:
            if self._list is None or self._list.count() <= self._view_rows:
                return False                    # fits on screen: REW/FWD keep seeking
            now = time.monotonic()
            if now - self._last_page >= PAGE_REPEAT_S:
                self._last_page = now
                self._viewer_set(self._stack[-1][2] + delta * (self._view_rows - 1))
            return True
        if not self.is_open or self._num_pages <= 1:
            return False
        if self._suspended:
            self._suspended = False
            self._show_on_top()
        now = time.monotonic()
        if now - self._last_page >= PAGE_REPEAT_S:
            self._last_page = now
            entry = self._stack[-1]
            entry[2] = (entry[2] + delta) % self._num_pages
            self._render()
        else:
            self._arm_timer()
        return True

    # ---------- playlist viewer ----------

    @property
    def viewer_open(self):
        return self.is_open and self._stack[-1][0] == 'viewer'

    def viewer_move(self, delta):
        """PLAY_PREV/NEXT, ↑/↓: move the highlight.  True if consumed (viewer open)."""
        if not self.viewer_open:
            return False
        self._viewer_set(self._stack[-1][2] + delta)
        return True

    def viewer_remote_move(self, button):
        """PLAY_NEXT (button=+1) / PLAY_PREV (-1), honouring the Up/Down setting."""
        return self.viewer_move(-button if self.viewer_next_up else button)

    def viewer_buttons_label(self):
        return "PLAY_NEXT = Up" if self.viewer_next_up else "PLAY_NEXT = Down"

    def toggle_viewer_buttons(self):
        self.viewer_next_up = not self.viewer_next_up

    def viewer_play(self, row=None):
        """
        PLAY_PAUSE, Enter/Space, double-click: play the highlighted entry, or
        pause/resume when it is the one already playing.  True if consumed.
        """
        if not self.viewer_open:
            return False
        if row is None:
            row = self._stack[-1][2]
        if not self.mw.playlist:
            return True
        self._wake()
        with self.mw.osd_muted():           # the viewer's ▶ / ⏸ marker is the feedback
            if row == self.mw.current_index:
                self.mw.toggle_play_pause()
                self._viewer_status = ""
            elif self.mw.play_index(row):
                self._viewer_status = ""
            else:
                self._viewer_status = "Cannot play: file is missing or unreadable"
        self.viewer_refresh()
        return True

    def viewer_refresh(self, status=None):
        """Update markers/colours in place (keeps the scroll position)."""
        if status is not None:
            self._viewer_status = status
        if not self.viewer_open or self._list is None:
            return
        pl = self.mw.playlist
        if self._list.count() != len(pl):
            self._render()                  # list changed shape: rebuild
            return
        for i, path in enumerate(pl):
            self._list.item(i).setData(ROLE_ENTRY, self._viewer_entry(i, path))
        if self._status_lbl is not None:
            self._status_lbl.setText(self._viewer_status)
            self._status_lbl.setVisible(bool(self._viewer_status))

    def _viewer_entry(self, i, path):
        """(number, marker, name, colour) for viewer row i."""
        mw = self.mw
        name = os.path.basename(path)
        if path in mw._bad_paths:
            return str(i + 1), "✖", name, C_BAD
        if i == mw.current_index:
            return str(i + 1), "⏸" if mw._is_paused else "▶", name, C_ON
        return str(i + 1), "", name, C_TEXT

    def _viewer_set(self, row):
        """Move the highlight to `row` (clamped), keeping it on screen."""
        self._wake()
        if self._list is None or self._list.count() == 0:
            return
        row = max(0, min(row, self._list.count() - 1))
        self._stack[-1][2] = row
        self._list.setCurrentRow(row)
        self._list.scrollToItem(self._list.item(row), QAbstractItemView.ScrollHint.EnsureVisible)
        if self._viewer_status:
            self.viewer_refresh(status="")

    def _viewer_row_changed(self, row):
        """Mouse click in the list moves the highlight."""
        if row >= 0 and self.viewer_open:
            self._stack[-1][2] = row
            self._arm_timer()

    def _wake(self):
        """User interaction: un-suspend (show right away) and restart the idle time-out."""
        if self._suspended:
            self._suspended = False
            self._show_on_top()
        self._arm_timer()

    # ---------- idle time-out ----------

    def timeout_label(self):
        return "Never" if self.timeout_min <= 0 else f"{self.timeout_min} min"

    def cycle_timeout(self):
        steps = MENU_TIMEOUT_STEPS
        i = steps.index(self.timeout_min) if self.timeout_min in steps else -1
        self.timeout_min = steps[(i + 1) % len(steps)]
        self._arm_timer()

    def _arm_timer(self):
        """(Re)start the idle time-out — called on every menu interaction."""
        if self.timeout_min > 0:
            self._timer.start(self.timeout_min * 60_000)
        else:
            self._timer.stop()

    def back(self):
        self._suspended = False
        if self._stack:
            self._stack.pop()
        if self._stack:
            self._render()
        else:
            self.close_menu()

    def close_menu(self):
        self._stack = []
        self._suspended = False
        self._timer.stop()
        self.hide()

    # ---------- OSD interplay (called by MainWindow.show_osd / hide_osd) ----------

    def suspend(self):
        """An OSD notification appeared: hide the menu but keep it open."""
        self._suspend_gen += 1          # cancels any resume still pending
        if self.is_open:
            self._suspended = True
            self.hide()

    def resume(self):
        """
        The OSD notification went away: bring the open menu back as it was.
        Deferred one event-loop pass so a clear_osd() immediately followed by a
        new show_osd() (e.g. un-pause) doesn't flash the menu on and off.
        """
        if self._suspended:
            gen = self._suspend_gen
            QTimer.singleShot(0, lambda: self._finish_resume(gen))

    def _finish_resume(self, gen):
        if gen == self._suspend_gen and self._suspended:
            self._suspended = False
            if self.is_open:
                self._render()

    # ---------- internals ----------

    def _activate(self, item):
        if item.todo:
            self.mw.show_osd(f'<span style="color:{C_OFF}">{item.label} — coming soon</span>',
                             duration_ms=1500)
            self._arm_timer()
            return
        if item.enabled is not None and not item.enabled():
            self.mw.show_osd(f'<span style="color:{C_OFF}">{item.disabled_msg}</span>', duration_ms=1800)
            self._arm_timer()
            return
        if item.submenu:
            start = max(0, self.mw.current_index) if item.submenu == 'viewer' else 0
            self._viewer_status = ""
            self._stack.append([item.submenu, item.arg, start])
            self._render()
            return
        quiet = item.quiet if item.quiet is not None else item.value is not None
        if quiet:
            with self.mw.osd_muted():   # the live value beside the item is the feedback
                item.run()
        else:
            item.run()          # an OSD it shows suspends the menu until the OSD is gone
        if self.is_open:
            self._render()      # refresh live values (and lists) after the action

    def _render(self):
        menu_id, arg, page = self._stack[-1]
        menu = MENUS[menu_id](self.mw, arg)
        viewer = menu_id == 'viewer'

        if viewer:
            self._num_pages, self._items = 1, []
        else:
            self._num_pages = max(1, -(-len(menu.items) // PAGE_SIZE))
            page = min(page, self._num_pages - 1)
            self._stack[-1][2] = page
            self._items = menu.items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
        self._list = self._status_lbl = None

        # Rebuild contents in a fresh container; detach the old one now (deleteLater alone
        # would leave its rows painted until the event loop runs).
        if self._content is not None:
            self._outer.removeWidget(self._content)
            self._content.setParent(None)
            self._content.deleteLater()
        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._outer.addWidget(self._content)

        title = QLabel(menu.title)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{C_TEXT}; font-family:{FF_MONTSERRAT}; font-size:{self._title_fs}px; "
                            f"font-weight:bold; background:transparent;")
        self._layout.addWidget(title)
        if menu.subtitle:
            sub = QLabel(menu.subtitle)
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setStyleSheet(self._style(C_SUBTITLE, self._small_fs))
            self._layout.addWidget(sub)
        self._layout.addSpacing(10)

        if viewer:
            self._build_viewer()
        for n, item in enumerate(self._items, start=1):
            self._layout.addWidget(self._row(str(n), item))

        self._layout.addSpacing(8)
        if self._num_pages > 1:
            self._layout.addWidget(self._pager(page))
        back_label = "Back" if len(self._stack) > 1 else "Close"
        self._layout.addWidget(self._row("0", Item(back_label), on_click=self.back))

        self._content.setMinimumWidth(self._min_width)
        # A child added to an already-visible window is only shown on the next event-loop
        # pass, and until then the layout counts it as empty — so sizing here would use the
        # OLD page's height and centre the wrong box.  Show it now, then size + place at once.
        self._content.show()
        self._outer.activate()
        self._place(self.sizeHint())
        if not self._suspended:
            self._show_on_top()
        self._arm_timer()

    def _build_viewer(self):
        pl = self.mw.playlist
        if not pl:
            self._layout.addWidget(self._label("Playlist is empty", C_DIM, self._row_fs))
            return
        screen = self.mw.screen().geometry()
        lst = QListWidget()
        lst.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lst.setUniformItemSizes(True)
        lst.setMouseTracking(True)                  # hover highlight
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lst.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        font = QFont()
        font.setFamilies(["Roboto Condensed", "RobotoCondensed", "Roboto", "sans-serif"])
        font.setPixelSize(self._row_fs)
        lst.setItemDelegate(_ViewerDelegate(font, str(len(pl)), lst))
        lst.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none; outline: 0; }}"
            f"QScrollBar:vertical {{ background: rgba(255,255,255,20); width: 10px; border-radius: 5px; }}"
            f"QScrollBar::handle:vertical {{ background: rgba(30,144,255,180); min-height: 30px;"
            f"  border-radius: 5px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}")
        for i, path in enumerate(pl):
            it = QListWidgetItem()
            it.setData(ROLE_ENTRY, self._viewer_entry(i, path))
            lst.addItem(it)
        row_h = lst.sizeHintForRow(0)
        # At most VIEW_ROWS, and never more than ~60% of the screen height (title,
        # hints and the Back row need the rest).
        self._view_rows = max(5, min(VIEW_ROWS, int(screen.height() * 0.60) // row_h))
        rows = min(self._view_rows, len(pl))
        lst.setFixedSize(int(screen.width() * 0.34), rows * row_h + 4)

        row = max(0, min(self._stack[-1][2], len(pl) - 1))
        self._stack[-1][2] = row
        lst.setCurrentRow(row)
        lst.scrollToItem(lst.item(row), QAbstractItemView.ScrollHint.PositionAtCenter)
        lst.currentRowChanged.connect(self._viewer_row_changed)
        lst.itemDoubleClicked.connect(lambda it: self.viewer_play(lst.row(it)))
        self._list = lst
        self._layout.addWidget(lst)

        self._status_lbl = self._label(self._viewer_status, C_BAD, self._small_fs, bold=True)
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setVisible(bool(self._viewer_status))
        self._layout.addWidget(self._status_lbl)

        hint = self._label("PREV / NEXT  move      REW / FWD  page      PLAY  play / pause",
                           C_SUBTITLE, self._small_fs)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addSpacing(6)
        self._layout.addWidget(hint)

    def _show_on_top(self):
        if not self.isVisible():
            self.show()
        self.raise_()

    def _style(self, color, size, bold=False):
        return (f"color:{color}; font-family:{FF_CONDENSED}; font-size:{size}px; "
                f"font-weight:{'bold' if bold else 'normal'}; background:transparent;")

    def _label(self, text, color, size, bold=False):
        lbl = QLabel(text)
        lbl.setStyleSheet(self._style(color, size, bold))
        lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        return lbl

    def _row(self, key, item, on_click=None):
        dim = item.todo or (item.enabled is not None and not item.enabled())
        row = _Clickable(on_click or (lambda: self._activate(item)))
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 4, 10, 4)
        h.setSpacing(14)
        h.addWidget(self._label(f"[{key}]", C_DIM if dim else C_KEY, self._row_fs, bold=True))
        text = item.label + ("  (coming soon)" if item.todo else "")
        h.addWidget(self._label(text, C_DIM if dim else C_TEXT, self._row_fs))
        h.addStretch(1)
        if item.submenu:
            h.addWidget(self._label("›", C_DIM if dim else C_KEY, self._row_fs, bold=True))
        elif item.value is not None:
            val = item.value()
            colour = C_DIM if dim else (C_OFF if val in _OFF_WORDS else C_ON)
            h.addWidget(self._label(val, colour, self._row_fs, bold=True))
        return row

    def _pager(self, page):
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 0, 10, 0)
        prev_btn = _Clickable(lambda: self.page(-1))
        QHBoxLayout(prev_btn).addWidget(self._label("◄◄ Prev", C_KEY, self._small_fs, bold=True))
        next_btn = _Clickable(lambda: self.page(+1))
        QHBoxLayout(next_btn).addWidget(self._label("Next ►►", C_KEY, self._small_fs, bold=True))
        h.addWidget(prev_btn)
        h.addStretch(1)
        h.addWidget(self._label(f"Page {page + 1} of {self._num_pages}", C_SUBTITLE, self._small_fs))
        h.addStretch(1)
        h.addWidget(next_btn)
        return bar

    def _place(self, size):
        """
        Size the window and put it at the left side, vertically centred (keeps the
        centre OSD and the video visible) — clamped so it never runs off the screen.
        """
        geo = self.mw.geometry()
        top_left = self.mw.mapToGlobal(self.mw.rect().topLeft())
        margin = int(geo.height() * 0.03)
        x = top_left.x() + int(geo.width() * 0.04)
        y = top_left.y() + (geo.height() - size.height()) // 2
        y = max(top_left.y() + margin, min(y, top_left.y() + geo.height() - margin - size.height()))
        self.setGeometry(x, y, size.width(), size.height())

    def wheelEvent(self, event):
        self.page(-1 if event.angleDelta().y() > 0 else +1)
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(8, 20, 60, 215))
        painter.setPen(QPen(QColor(30, 144, 255, 220), 2))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)
