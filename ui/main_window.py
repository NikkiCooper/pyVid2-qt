#  main_window.py Copyright (c) 2026 Nikki Cooper
#
#  This program and the accompanying materials are made available under the
#  terms of the GNU Lesser General Public License, version 3.0 which is available at
#  https://www.gnu.org/licenses/gpl-3.0.html#license-text
#
"""
MainWindow - pyVid2-qt
Fullscreen-only video player with hardware acceleration.
"""

import os
import random
import Bcolors

bc = Bcolors.Bcolors()

SEEK_TIME_SECONDS = 10
SPEED_STEPS  = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
VOLUME_STEP  = 0.05    # 5% per key/IR press

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QEvent, Signal, QTimer
from PySide6.QtGui import QCursor, QPainter, QColor, QPen
from IRRemoteControl import IRRemoteControl
from ui.hud import HUD, CurPosOsd
from core.video_widget import VideoWidget
from SpeedTag import read_tag, tag_label


class _OsdWidget(QWidget):
    """
    Semi-transparent OSD notification overlay.

    QLabel with WA_TranslucentBackground doesn't paint its stylesheet
    background on X11 (WA_NoSystemBackground suppresses all background
    painting).  This custom widget paints the rounded-rect background
    explicitly in paintEvent, exactly like HUD does, so rgba transparency
    works correctly under XWayland/KDE compositing.
    """

    def __init__(self, parent, font_size):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 25, 50, 25)   # matches original padding: 25px 50px
        layout.setSpacing(0)

        self._lbl = QLabel()
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # default color was  rgb(255,200,0)
        self._lbl.setStyleSheet(
            f"color: rgb(30,144,255); font-size:{font_size}px; "
            f"font-weight:bold; background:transparent;"
        )
        layout.addWidget(self._lbl)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(8, 20, 60, 155))
        # DodgerBlue
        painter.setPen(QPen(QColor(30, 144, 255, 200), 2))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)

    def setText(self, text):
        self._lbl.setText(text)
        self.adjustSize()

    def text(self):
        return self._lbl.text()


class MainWindow(QMainWindow):
    """
    Fullscreen video player main window.
    Accepts optional argparse opts namespace from CLI; falls back to GUI dialog.
    """

    # Thread-safe signal for IR remote callbacks (IR runs in background thread)
    ir_signal = Signal(object)

    def __init__(self, opts=None):
        super().__init__()
        self.opts = opts
        self.setWindowTitle("pyVid2-qt")

        # Playlist state
        self.playlist = []
        self.current_index = -1
        self._speed = float(opts.playSpeed) if opts else 2.0
        self._is_paused = False
        self._cli_loop = opts.loop if opts else False       # --loop: loop entire playlist
        self._is_repeating = False                          # HUD toggle: repeat current video
        self._is_muted = opts.mute if opts else False       # --mute / 'M' key toggle
        self._volume   = opts.volume if opts else 0        # 0–100 integer
        self._screenshot_count = 0                          # files saved this session
        # 0=off  1=curpos  2=curpos/duration
        self._curpos_state = 1 if (opts and getattr(opts, 'enableOSDcurpos', False)) else 0
        # --autoSpeed: saved base speed while a tagged video overrides it
        self._auto_speed_saved: float | None = None
        # HUD pin: True = HUD is locked visible, mouse activation ignored
        self._hud_pinned = False

        # Wall-clock position counter (incremented by _position_timer every second)
        self._hud_position_ms = 0

        # Screen geometry
        screen_rect = self.screen().geometry()
        self.display_width = screen_rect.width()
        self.display_height = screen_rect.height()

        # Wire IR signal before registering callbacks
        self.ir_signal.connect(self._handle_ir_callback)

        if opts and opts.disable_IR:
            self.ir_remote = None
        else:
            self.ir_remote = IRRemoteControl(opts.irKeymap, opts.udpPort, debug=False)
            self._setup_ir_callbacks()
            self.ir_remote.start()

        self.init_ui()

        # Move window to specified display before fullscreen
        if opts and opts.display:
            self._move_to_display(opts.display)

        self.showFullScreen()
        QTimer.singleShot(200, self._init_overlays)

        # Auto-load from CLI opts after window is shown
        if opts:
            QTimer.singleShot(400, self._load_from_opts)

    # ==================== IR Remote helpers ====================

    def _invoke_on_main_thread(self, method):
        """Wrap a method so it's called on the Qt main thread from IR's background thread."""
        def wrapper():
            self.ir_signal.emit(method)
        return wrapper

    def _handle_ir_callback(self, method):
        method()

    # ==================== OSD ====================

    def _init_overlays(self):
        """Map overlay windows after parent is fully shown — avoids KDE panel-peek at startup."""
        if not self.osd_label.isVisible():
            self.osd_label.setWindowOpacity(0.0)
            self.osd_label.show()
        if not self.hud.isVisible():
            self.hud.setWindowOpacity(0.0)
            self.hud.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.hud.show()
        # help_overlay uses real show()/hide() — no need to pre-map it.
        # The opacity-based approach leaves a mapped window at center-screen that
        # intercepts clicks even at opacity=0 on XWayland (X11 routes by geometry).
        # Current position OSD — position then show if enabled via CLI
        self._curpos_osd.reposition()
        if self._curpos_state > 0:
            self._curpos_osd.show()
        # Apply initial volume and mute state
        self.video_widget.audio_output.setVolume(self._volume / 100.0)
        self.hud.set_volume(self._volume)
        if self._is_muted:
            self.video_widget.audio_output.setMuted(True)
            self.hud.set_muted(True)

    def show_osd(self, message, duration_ms=2000, persistent=False):
        """Display a notification overlay in the center of the screen."""
        if self._help_state == 1:
            self.help_overlay.hide()
        elif self._help_state == 2:
            self.remote_overlay.hide()

        self._help_state = 3

        self.osd_label.setText(message)
        self.osd_persistent = persistent
        self._reposition_osd()
        if not self.osd_label.isVisible():
            self.osd_label.show()
        self.osd_label.setWindowOpacity(1.0)
        if not persistent:
            self.osd_timer.stop()
            self.osd_timer.start(duration_ms)

    def hide_osd(self):
        """Hide OSD unless it's set to persist (e.g. pause state)."""
        if not self.osd_persistent:
            self.osd_label.setWindowOpacity(0.0)
            self.osd_timer.stop()

    def clear_osd(self):
        """Force-hide OSD regardless of persistent state."""
        self.osd_persistent = False
        self.osd_label.setWindowOpacity(0.0)
        self.osd_timer.stop()

    # Bottom 10% of screen activates the HUD
    _HUD_ACTIVATION_RATIO = 0.90   # mouse_y > screen_height * 0.90 → activate

    def _show_hud(self, mouse_pos=None):
        """Show HUD if a playlist is loaded and mouse is in the activation zone.
        When HUD is pinned, mouse-driven activation is skipped entirely."""
        if not self.playlist:
            return

        if self._hud_pinned:
            return   # pinned: only toggle_hud_pin can change visibility

        if mouse_pos is not None:
            sr = self.screen().geometry()
            # Reject cursor on a different monitor (same Y row would otherwise trigger HUD)
            if not (sr.x() <= mouse_pos.x() < sr.x() + sr.width()):
                return
            threshold = sr.y() + int(sr.height() * self._HUD_ACTIVATION_RATIO)
            if mouse_pos.y() < threshold:
                return   # outside bottom activation zone

        filename = os.path.basename(self.playlist[self.current_index]) \
            if self.current_index >= 0 else ""
        _, dur_ms, _ = self.video_widget.get_position_info()
        self.hud.update_state(filename, self.current_index + 1,
                              len(self.playlist), self._speed, self._is_paused,
                              self._is_repeating, dur_ms, self._hud_position_ms)
        self.hud.show_hud()

    def mouseMoveEvent(self, event):
        self._show_hud(mouse_pos=event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def _poll_cursor(self):
        """Fallback for Wayland: Qt events don't fire over native video surface."""
        self._show_hud(mouse_pos=QCursor.pos())

    def _reposition_osd(self):
        """Center OSD over the video area using global coordinates (separate top-level window)."""
        self.osd_label.adjustSize()
        global_center = self.video_container.mapToGlobal(self.video_container.rect().center())
        self.osd_label.move(
            global_center.x() - self.osd_label.width() // 2,
            global_center.y() - self.osd_label.height() // 2,
        )

    # ==================== Display selection ====================

    def _move_to_display(self, display_spec):
        """Move window to specified display by index (int) or partial name match."""
        from PySide6.QtWidgets import QApplication
        screens = QApplication.screens()
        target = None
        try:
            idx = int(display_spec)
            if 0 <= idx < len(screens):
                target = screens[idx]
        except ValueError:
            for s in screens:
                if display_spec in s.name():
                    target = s
                    break
        if target:
            self.move(target.geometry().topLeft())
        else:
            print(f"Warning: display '{display_spec}' not found — using default.")

    # ==================== CLI opts loading ====================

    def _load_from_opts(self):
        """Build playlist from CLI opts via FindVideos, then start playback."""
        from FindVideos import FindVideos

        if self.opts.verbose:
            print("Scanning for videos...")

        fv = FindVideos(self.opts)

        if self.opts.printIgnoreList:
            fv.print_ignores()

        if self.opts.verbose:
            fv.videoList_print()
            if fv.ignoreList:
                fv.print_ignores()

        if fv.numVideos == 0:
            print("No videos found.")
            return

        self.playlist = fv.videoList

        if self.opts.shuffle:
            random.shuffle(self.playlist)

        if self.opts.verbose:
            print(f"{bc.White_f}Loaded{bc.Green_f} {len(self.playlist)}{bc.White_f} videos.{bc.RESET}")

        self.current_index = -1
        self.play_next()

    # ==================== UI setup ====================

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        central_widget.setLayout(main_layout)

        # --- Video area ---
        self.video_container = QWidget()
        self.video_container.setStyleSheet("background-color: black;")
        self.video_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.video_container.setMouseTracking(True)
        self.video_container.installEventFilter(self)  # resize + mouse move
        video_container_layout = QVBoxLayout()
        video_container_layout.setContentsMargins(0, 0, 0, 0)
        video_container_layout.setSpacing(0)
        self.video_container.setLayout(video_container_layout)

        self.video_widget = VideoWidget()
        self.video_widget.set_speed(self._speed)
        self.video_widget.installEventFilter(self)
        self.video_widget.setMouseTracking(True)
        video_container_layout.addWidget(self.video_widget, stretch=1)

        main_layout.addWidget(self.video_container, stretch=1)

        # Auto-advance when video ends (via _on_video_ended for loopDelay support)
        self.video_widget.video_ended.connect(self._on_video_ended)

        # Enable mouse tracking on the main window too (covers margins/control panel area)
        self.setMouseTracking(True)

        # --- HUD ---
        self.hud = HUD(self)

        # --- Help overlays ---
        from ui.hud import HelpOverlay, RemoteOverlay
        self.help_overlay   = HelpOverlay(self)
        self.remote_overlay = RemoteOverlay(self)
        self._help_state = 0   # 0=off  1=keyboard shortcuts  2=remote control

        # --- Current position OSD ---
        self._curpos_osd = CurPosOsd(self)

        # Wayland native surfaces (wl_subsurface) swallow mouse-move events before
        # Qt sees them.  Poll QCursor.pos() every 50 ms as a workaround.
        self._cursor_poll_timer = QTimer(self)
        self._cursor_poll_timer.timeout.connect(self._poll_cursor)
        self._cursor_poll_timer.start(50)

        # Position display timer: polls actual video position every second for the HUD counter.
        # Reading the real player position means the display stays correct after speed changes.
        self._position_timer = QTimer(self)
        self._position_timer.setInterval(1000)
        self._position_timer.timeout.connect(self._tick_position)

        # --- OSD overlay — top-level Tool window, parent=self for WM_TRANSIENT_FOR ---
        # Opacity-based show/hide avoids XMapWindow events that trigger KDE panel-peek.
        osd_font_size = max(24, int(self.display_height * 0.022))
        self.osd_label = _OsdWidget(self, font_size=osd_font_size)
        self.osd_label.hide()   # _init_overlays() maps it with opacity=0 after parent is shown

        self.osd_timer = QTimer()
        self.osd_timer.setSingleShot(True)
        self.osd_timer.timeout.connect(self.hide_osd)
        self.osd_persistent = False

    # ==================== IR callbacks ====================

    def _setup_ir_callbacks(self):
        """Register all IR remote button callbacks."""
        self.ir_remote.register_callback('PWR',        self._invoke_on_main_thread(self.close))
        self.ir_remote.register_callback('PLAY_NEXT',  self._invoke_on_main_thread(self.play_next))
        self.ir_remote.register_callback('PLAY_PREV',  self._invoke_on_main_thread(self.play_previous))
        self.ir_remote.register_callback('REW',        self._invoke_on_main_thread(self.seek_backward),allow_repeat=True)
        self.ir_remote.register_callback('FWD',        self._invoke_on_main_thread(self.seek_forward),allow_repeat=True)
        self.ir_remote.register_callback('PLAY_PAUSE', self._invoke_on_main_thread(self.toggle_play_pause))
        self.ir_remote.register_callback('RESTART',    self._invoke_on_main_thread(self.restart_video))
        self.ir_remote.register_callback('VOL+',       self._invoke_on_main_thread(self.vol_up),allow_repeat=True)
        self.ir_remote.register_callback('VOL-',       self._invoke_on_main_thread(self.vol_down),allow_repeat=True)
        self.ir_remote.register_callback('MUTE-UNMUTE',self._invoke_on_main_thread(self.toggle_mute))
        self.ir_remote.register_callback('SPEED+',     self._invoke_on_main_thread(self.speed_up))
        self.ir_remote.register_callback('SPEED-',     self._invoke_on_main_thread(self.speed_down))
        self.ir_remote.register_callback('LOOP',       self._invoke_on_main_thread(self.toggle_repeat))
        self.ir_remote.register_callback('MENU',       self._invoke_on_main_thread(self.show_menu))
        self.ir_remote.register_callback('HUD',        self._invoke_on_main_thread(self.toggle_hud_pin))
        self.ir_remote.register_callback('SCREENSHOT', self._invoke_on_main_thread(self.take_screenshot))
        self.ir_remote.register_callback('SCRNSHOT',   self._invoke_on_main_thread(self.take_screenshot))
        self.ir_remote.register_callback('1',          self._invoke_on_main_thread(self.toggle_curpos_osd))     #OSD
        self.ir_remote.register_callback('3',          self._invoke_on_main_thread(self.save_playlist))         # Save playlist
        self.ir_remote.register_callback('4',          self._invoke_on_main_thread(self.print_playlist))        # print playlist
        self.ir_remote.register_callback('5',          self._invoke_on_main_thread(self.randomize_playlist))    # Shuffle
        self.ir_remote.register_callback('6',          self._invoke_on_main_thread(self.show_metadata))         # show metadata
        self.ir_remote.register_callback('7',          self._invoke_on_main_thread(self.toggle_video_title))    # Toggle video title

        # Stubs for future IR remote buttons:
        self.ir_remote.register_callback('8',          self._invoke_on_main_thread(self.stub_1))                # Stub_1
        self.ir_remote.register_callback('9',          self._invoke_on_main_thread(self.stub_2))                # Stub_2
        self.ir_remote.register_callback('0',          self._invoke_on_main_thread(self.stub_3))                # Stub_3

    def _tick_position(self):
        """
        Update HUD position counter.

        value = player_position / speed  →  "effective wall-clock position"
        This advances at exactly 1 real second per timer tick at any playback speed,
        and stays consistent with the effective-duration shown in the HUD duration label.
        """
        pos_ms, dur_ms, _ = self.video_widget.get_position_info()
        self._hud_position_ms = int(pos_ms / self._speed) if self._speed > 0 else 0
        if self._curpos_state > 0:
            self._curpos_osd.refresh(self._hud_position_ms, dur_ms)
        # Keep seek slider in sync when HUD is visible
        self.hud.update_seek_slider(pos_ms, dur_ms)
        # When HUD is pinned it never gets update_state() from _show_hud() — push it here.
        if self._hud_pinned and self.playlist and self.current_index >= 0:
            filename = os.path.basename(self.playlist[self.current_index])
            self.hud.update_state(filename, self.current_index + 1,
                                  len(self.playlist), self._speed, self._is_paused,
                                  self._is_repeating, dur_ms, self._hud_position_ms)

    # ==================== Playlist ====================

    def play_file(self, file_path):
        """Activate a playlist entry."""
        self._is_paused = False
        self._hud_position_ms = 0
        self._position_timer.start()

        # ── Auto-speed: restore base speed from the previous video's override,
        #    then check if this video has its own auto_speed tag.
        if self.opts and getattr(self.opts, "autoSpeed", False):
            # Always restore to base speed first (silently — no OSD flash)
            if self._auto_speed_saved is not None:
                self._speed = self._auto_speed_saved
                self.video_widget.set_speed(self._speed)
                self._auto_speed_saved = None

            # Check tag on the incoming file
            tag_speed = read_tag(file_path)
            if tag_speed is not None and tag_speed != self._speed:
                self._auto_speed_saved = self._speed
                self._speed = tag_speed
                self.video_widget.set_speed(tag_speed)
                lbl = tag_label(tag_speed)
                self.show_osd(f"Auto Speed: {lbl}", duration_ms=2500)
            elif tag_speed is not None and tag_speed == self._speed:
                # Tag matches current speed — no visible change, but mark override
                # so the "same tag, same speed" case doesn't confuse the restore logic.
                self._auto_speed_saved = self._speed   # effectively a no-op restore

        _filename = os.path.basename(file_path)
        filename = f'<span style="color:rgb(30,144,255)">{os.path.basename(file_path)}</span>'
        #position = f"[{self.current_index + 1}/{len(self.playlist)}]" if self.playlist else ""
        position = f'<span style="color:rgb(255,255,255)">Video</span> <span style="color:rgb(0,210,0)">{self.current_index + 1}</span><span style="color:rgb(255,255,255)"> of</span> <span style="color:rgb(0,210,0)">{len(self.playlist)}</span><span style="color:rgb(255,255,255)">:</span>' if self.playlist else ''

        # Always print the filename being played
        print(f"{bc.White_f}Playing video {bc.Light_Yellow_f}{self.current_index + 1}{bc.Green_f} of{bc.Light_Yellow_f} {len(self.playlist)}{bc.White_f}:{bc.Light_Blue_f} {_filename}{bc.RESET}")

        # Extended console output gated on --metadata
        if self.opts and self.opts.metadata:
            print(f"  [{self.current_index + 1} of {len(self.playlist)}]  {file_path}")

        self.show_osd(f"{position} {filename}".strip(), duration_ms=3000)
        self.hud.update_state(filename, self.current_index + 1,
                              len(self.playlist), self._speed, self._is_paused,
                              self._is_repeating)   # duration/position = 0 at load; poll fills them in
        self.video_widget.load_file(file_path)

    def play_next(self):
        if not self.playlist:
            return
        self.current_index = (self.current_index + 1) % len(self.playlist)
        self.play_file(self.playlist[self.current_index])

    def play_previous(self):
        if not self.playlist:
            return
        self.current_index = (self.current_index - 1) % len(self.playlist)
        self.play_file(self.playlist[self.current_index])

    def sort_playlist(self):
        if not self.playlist:
            return
        self.playlist.sort()
        #self.current_index = -1
        self.show_osd("Playlist Sorted", duration_ms=1500)

    def randomize_playlist(self):
        if not self.playlist:
            return
        random.shuffle(self.playlist)
        self.current_index = -1
        self.show_osd("Playlist Shuffled", duration_ms=1500)

    # ==================== Playback controls ====================

    def _on_video_ended(self):
        """Handle video end: apply loopDelay, repeat/loop/exit logic."""
        self._position_timer.stop()
        if self.opts is None:
            # GUI mode: play next, no exit
            self.play_next()
            return

        loop_delay_ms = self.opts.loopDelay * 1000

        # Repeat Video: silently replay current video
        if self._is_repeating:
            QTimer.singleShot(loop_delay_ms, self._replay_current)
            return

        # Reached last video: exit unless --loop (loop entire playlist)
        at_end = bool(self.playlist) and self.current_index == len(self.playlist) - 1
        if at_end and not self._cli_loop:
            QTimer.singleShot(loop_delay_ms, self.close)
            return

        QTimer.singleShot(loop_delay_ms, self.play_next)

    def _replay_current(self):
        """Silently restart the current video (Repeat Video mode)."""
        if not self.playlist or self.current_index < 0:
            return
        self._is_paused = False
        self._hud_position_ms = 0
        self._position_timer.stop()
        self._position_timer.start()
        self.video_widget.restart()

    def toggle_play_pause(self):
        if not self.playlist:
            return
        self._is_paused = not self._is_paused
        if self._is_paused:
            self._position_timer.stop()
            self.video_widget.pause()
            self.show_osd("⏸ Paused", duration_ms=1500)
        else:
            self._position_timer.start()
            self.video_widget.play()
            self.clear_osd()
            self.show_osd("▶ Playing", duration_ms=1500)
        # Keep HUD play/pause button in sync
        _, dur_ms, _ = self.video_widget.get_position_info()
        self.hud.update_state(
            os.path.basename(self.playlist[self.current_index]) if self.playlist and self.current_index >= 0 else "",
            self.current_index + 1, len(self.playlist), self._speed, self._is_paused,
            self._is_repeating, dur_ms, self._hud_position_ms
        )

    def _set_speed(self, speed):
        """Apply a new playback speed and sync the HUD position counter."""
        self._speed = speed
        self.video_widget.set_speed(speed)
        pos_ms, _, _ = self.video_widget.get_position_info()
        self._hud_position_ms = int(pos_ms / self._speed) if self._speed > 0 else 0
        spd = int(speed) if speed == int(speed) else speed
        self.show_osd(f"Speed: {spd}x", duration_ms=1500)

    def speed_up(self):
        try:
            idx = SPEED_STEPS.index(self._speed)
        except ValueError:
            idx = 0
        if idx < len(SPEED_STEPS) - 1:
            self._set_speed(SPEED_STEPS[idx + 1])
        else:
            spd = int(self._speed) if self._speed == int(self._speed) else self._speed
            # gray
            self.show_osd(f'<span style="color:rgb(160,160,160)">Speed: {spd}x  (max)</span>',
                          duration_ms=1500)

    def speed_down(self):
        try:
            idx = SPEED_STEPS.index(self._speed)
        except ValueError:
            idx = len(SPEED_STEPS) - 1
        if idx > 0:
            self._set_speed(SPEED_STEPS[idx - 1])
        else:
            spd = int(self._speed) if self._speed == int(self._speed) else self._speed
            # gray
            self.show_osd(f'<span style="color:rgb(160,160,160)">Speed: {spd}x  (min)</span>',
                          duration_ms=1500)

    def toggle_repeat(self):
        self._is_repeating = not self._is_repeating
        self.show_osd(f"Repeat Video: {'ON' if self._is_repeating else 'OFF'}", duration_ms=1500)

    def toggle_mute(self):
        self._is_muted = not self._is_muted
        self.video_widget.audio_output.setMuted(self._is_muted)
        self.hud.set_muted(self._is_muted)
        self.show_osd("🔇 Mute" if self._is_muted else "🔊 Unmute", duration_ms=1500)

    def restart_video(self):
        """Restart current video from 00:00 and reset all HUD counters."""
        if not self.playlist or self.current_index < 0:
            return
        # Ensure we're in playing state
        if self._is_paused:
            self._is_paused = False
            self.clear_osd()
        self.video_widget.restart()
        # Reset wall-clock counter and restart timer
        self._hud_position_ms = 0
        self._position_timer.stop()
        self._position_timer.start()
        self.show_osd("⏮ Restarted", duration_ms=1500)
        _, dur_ms, _ = self.video_widget.get_position_info()
        filename = os.path.basename(self.playlist[self.current_index])
        self.hud.update_state(filename, self.current_index + 1, len(self.playlist),
                              self._speed, False, self._is_repeating, dur_ms, 0)

    def toggle_curpos_osd(self):
        """Cycle CurPosOsd through OFF → CURPOS → CURPOS/DURATION → OFF."""
        self._curpos_state = (self._curpos_state + 1) % 3
        if self._curpos_state == 0:
            self._curpos_osd.hide()
        else:
            self._curpos_osd.reposition()
            if not self._curpos_osd.isVisible():
                self._curpos_osd.show()
            self._curpos_osd.update()

    def toggle_hud_pin(self):
        """IR HUD button: pin HUD visible / unpin (restores normal mouse behaviour)."""
        if not self.playlist:
            return
        self._hud_pinned = not self._hud_pinned
        self.hud.pinned = self._hud_pinned
        if self._hud_pinned:
            # Force HUD into view; show_hud() will not start hide_timer while pinned
            filename = os.path.basename(self.playlist[self.current_index]) \
                if self.current_index >= 0 else ""
            _, dur_ms, _ = self.video_widget.get_position_info()
            self.hud.update_state(filename, self.current_index + 1,
                                  len(self.playlist), self._speed, self._is_paused,
                                  self._is_repeating, dur_ms, self._hud_position_ms)
            self.hud.show_hud()
        else:
            # Unpin: hide immediately; normal mouse-driven behaviour resumes
            self.hud.hide_hud()

    def toggle_video_title(self):
        self.show_osd("Title Display — TODO", duration_ms=1500)

    def show_metadata(self):
        self.show_osd("Metadata — TODO", duration_ms=1500)

    def show_menu(self):
        """Cycle help: OFF → keyboard shortcuts → remote control → OFF."""
        if self._help_state == 1:
            self.help_overlay.hide()
        elif self._help_state == 2:
            self.remote_overlay.hide()

        self._help_state = (self._help_state + 1) % 3

        if self._help_state == 1:
            self.help_overlay.reposition()
            self.help_overlay.show()
        elif self._help_state == 2:
            self.remote_overlay.reposition()
            self.remote_overlay.show()

    def _seek_bar_osd(self, new_pos, duration, forward: bool) -> None:
        icon = "►► " if forward else "◄◄ "
        if new_pos is not None and duration:
            pct = int(new_pos * 100 / duration)
            bar_filled = pct // 5
            bar_empty  = 20 - bar_filled
            # DodgerBlue & gray
            bar = (f'<span style="color:rgb(30,144,255)">{"█" * bar_filled}</span>'
                   f'<span style="color:rgba(200,200,200,120)">{"░" * bar_empty}</span>')
            self.show_osd(
                f'<span style="color:white">{icon}{pct:3d}%  </span>{bar}',
                duration_ms=1200)
        else:
            self.show_osd(f'<span style="color:white">{icon.strip()}</span>', duration_ms=800)

    def seek_backward(self):
        new_pos, duration = self.video_widget.seek(-SEEK_TIME_SECONDS * 1000)
        self._seek_bar_osd(new_pos, duration, forward=False)

    def seek_forward(self):
        new_pos, duration = self.video_widget.seek(SEEK_TIME_SECONDS * 1000)
        self._seek_bar_osd(new_pos, duration, forward=True)

    def _vol_osd(self, pct: int) -> None:
        bar_filled = pct // 5
        bar_empty  = 20 - bar_filled
        # DodgerBlue & gray
        bar = (f'<span style="color:rgb(30,144,255)">{"█" * bar_filled}</span>'
               f'<span style="color:rgba(200,200,200,120)">{"░" * bar_empty}</span>')
        self.show_osd(
            f'<span style="color:white">🔊 {pct:3d}%  </span>{bar}',
            duration_ms=1200)

    def _apply_volume(self, pct: int) -> None:
        """Set volume, update internal state, HUD slider, and OSD."""
        self._volume = pct
        self.video_widget.audio_output.setVolume(pct / 100.0)
        self.hud.set_volume(pct)
        self._vol_osd(pct)

    def vol_up(self):
        self._apply_volume(min(100, self._volume + 5))

    def vol_down(self):
        self._apply_volume(max(0, self._volume - 5))

    def take_screenshot(self):
        """
        Capture the current video frame, scale to 2160p, and save as PNG or JPEG.

        Frame is sourced from QVideoSink (raw decoder output) — completely blind
        to HUD, OSD, and any other overlays.

        Path:  <sshotDir>/<video_name>/<video_name>-mm-dd-yy-HH:MM:SS.<ext>
        If a file with that timestamp already exists, the second is incremented
        until a unique name is found; the file is always saved.
        """
        import datetime

        if not self.playlist or self.current_index < 0:
            self.show_osd("No video loaded", duration_ms=1500)
            return

        # ── Get raw decoded frame ──────────────────────────────────────────
        img = self.video_widget.capture_frame()
        if img is None or img.isNull():
            self.show_osd("Screenshot failed — no frame available", duration_ms=2000)
            return

        # ── Scale to 2160p (2× bilinear — exact integer scale for 1080p src) ──
        from PySide6.QtCore import Qt as _Qt
        from core.video_widget import SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT
        img_out = img.scaled(SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT,
                             _Qt.AspectRatioMode.KeepAspectRatio,
                             _Qt.TransformationMode.SmoothTransformation)
        if img_out.isNull():
            self.show_osd("Screenshot scale failed", duration_ms=2000)
            return

        # ── Build output directory ─────────────────────────────────────────
        video_path = self.playlist[self.current_index]
        video_name = os.path.splitext(os.path.basename(video_path))[0]

        base_dir = os.path.expanduser(
            self.opts.sshotDir if self.opts and self.opts.sshotDir else "~/pyVid2-qt-Shots"
        )
        shot_dir = os.path.join(base_dir, video_name)

        try:
            os.makedirs(shot_dir, exist_ok=True)
        except OSError as e:
            self.show_osd(f"Screenshot dir error: {e.strerror}", duration_ms=3000)
            return

        # ── Unique filename — advance by 1 sec on collision ────────────────
        use_jpg = bool(self.opts and self.opts.useJPG)
        ext     = "jpg" if use_jpg else "png"
        now     = datetime.datetime.now()

        for _ in range(3600):           # cap: 1 hour of increments
            ts       = now.strftime("%m-%d-%y-%H:%M:%S")
            filename = f"{video_name}-{ts}.{ext}"
            filepath = os.path.join(shot_dir, filename)
            if not os.path.exists(filepath):
                break
            now += datetime.timedelta(seconds=1)

        # ── Save ───────────────────────────────────────────────────────────
        try:
            ok = img_out.save(filepath, "JPEG" if use_jpg else "PNG",
                              95 if use_jpg else -1)
        except OSError as e:
            self.show_osd(f"Screenshot write error: {e.strerror}", duration_ms=3000)
            return

        if not ok:
            # QImage.save() returns False on failure (disk full, bad path, etc.)
            self.show_osd("Screenshot save failed — check path / disk space", duration_ms=3000)
            return

        self._screenshot_count += 1
        # bright-green
        self.show_osd(
            f'<span style="color:rgb(0,210,0)">File: {self._screenshot_count}</span>'
            f'  {filename}',
            duration_ms=2500
        )

    def print_playlist(self):
        """
        Prints self.playlist contents to the console.
        :return: None
        """
        if not self.playlist:
            return
        print(f"\n{bc.Light_Magenta_f}Master Playlist:{bc.Light_Blue_f}\n")
        for videoFile in self.playlist:
            print(videoFile)
        print(f"\n{bc.Light_Yellow_f}Total Videos:{bc.Green_f} {len(self.playlist)}{bc.RESET}\n\n")

    def save_playlist(self):
        """
        Saves the current playlist to a specified file.

        Writes each video from the current video list into a specified file
        within the save playlist directory. Each video entry is written in
        a new line.

        Parameters:
        filename (str): The name of the file where the playlist will be stored.
        """
        if not self.playlist:
            return
        base_dir = "~/+Playlists"
        _savePlayListPath = os.path.expanduser(base_dir)
        _filename = 'VideoPlayList-' + str(len(self.playlist)) + '.txt'
        _file = _savePlayListPath + '/' + _filename
        with open(_file, "w") as file:
            for line in self.playlist:
                file.write(str(line) + "\n")
        #self.show_osd("Save Playlist as " + _filename, duration_ms=1500)
        self.show_osd(f'Save Playlist as <span style="color:rgb(0,210,0)">{_filename}</span>', duration_ms=1500)

    def toggle_greyscale(self):
        # Greyscale requires GStreamer pipeline-level filtering (videobalance
        # saturation=0).  Python-side QVideoFrame → QImage → setVideoFrame()
        # floods GPU memory at video rate (~480 MB/s into VRAM).
        # Needs QMediaPlayer replacement with a custom playbin3 pipeline — TODO.
        self.show_osd("Greyscale — TODO", duration_ms=1500)

    # ==================== Feature stubs (wired up in later phases) ====================
    def stub_1(self):
        self.show_osd("Stub_1 — TODO", duration_ms=1500)

    def stub_2(self):
        self.show_osd("Stub_2 — TODO", duration_ms=1500)

    def stub_3(self):
        self.show_osd("Stub_3 — TODO", duration_ms=1500)

    # ==================== Events ====================

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True
        elif event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta > 0:
                self.seek_forward()
            elif delta < 0:
                self.seek_backward()
            return True
        elif event.type() == QEvent.Type.MouseMove and obj == self.video_container:
            self._show_hud(mouse_pos=event.globalPosition().toPoint())
        elif event.type() == QEvent.Type.Resize and obj == self.video_container:
            self._reposition_osd()
            self._curpos_osd.reposition()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        key = event.key()
        # Dismiss help overlay before any action that would show an OSD behind it.
        # H and Escape/Q handle the overlay themselves.
        if self._help_state != 0 and key not in (
            Qt.Key.Key_Escape, Qt.Key.Key_Q, Qt.Key.Key_H
        ):
            if self._help_state == 1:
                self.help_overlay.hide()
            elif self._help_state == 2:
                self.remote_overlay.hide()
            self._help_state = 0

        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Q):                # Escape/Q
            if self._help_state != 0:
                self.help_overlay.hide()
                self.remote_overlay.hide()
                self._help_state = 0
            else:
                self.close()
        elif key == Qt.Key.Key_Space:                               # play/pause
            self.toggle_play_pause()
        elif key == Qt.Key.Key_N:                                   # next video
            self.play_next()
        elif key == Qt.Key.Key_P:                                   # previous video
            self.play_previous()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):            # speed up
            self.speed_up()
        elif key == Qt.Key.Key_Minus:                               # speed down
            self.speed_down()
        elif key == Qt.Key.Key_Left:                                # seek backward
            self.seek_backward()
        elif key == Qt.Key.Key_Right:                               # seek forward
            self.seek_forward()
        elif key == Qt.Key.Key_Down:                                # Volume Down
            self.vol_down()
        elif key == Qt.Key.Key_Up:                                  # Volume Up
            self.vol_up()
        elif key == Qt.Key.Key_M:                                   # mute/unmute
            self.toggle_mute()
        elif key == Qt.Key.Key_L:                                   # toggle repeat
            self.toggle_repeat()
        elif key == Qt.Key.Key_S:                                   # screenshot
            self.take_screenshot()
        elif key == Qt.Key.Key_R:                                   # restart video
            self.restart_video()
        elif key == Qt.Key.Key_H:                                   # show help
            self.show_menu()
        elif key == Qt.Key.Key_G:                                   # greyscale
            self.toggle_greyscale()
        elif key == Qt.Key.Key_O:                                   # curpos OSD
            self.toggle_curpos_osd()
        elif key == Qt.Key.Key_T:                                   # toggle title display
            self.toggle_video_title()
        elif key == Qt.Key.Key_J:                                   # shuffle playlist
            self.opts.shuffle = not self.opts.shuffle
            if self.opts.shuffle:
                self.randomize_playlist()
            else:
                self.sort_playlist()
        elif key == Qt.Key.Key_Insert:                              # metadata
            self.show_metadata()
        elif key == Qt.Key.Key_Comma:                               # print playlist
            self.print_playlist()
        elif key == Qt.Key.Key_Period:                              # save Playlist
            self.save_playlist()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.ir_remote:
            self.ir_remote.stop()
        self.video_widget.close_player()
        event.accept()
