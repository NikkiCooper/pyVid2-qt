#!/usr/bin/env python3
#  main.py Copyright (c) 2026 Nikki Cooper
#
#  This program and the accompanying materials are made available under the
#  terms of the GNU Lesser General Public License, version 3.0 which is available at
#  https://www.gnu.org/licenses/gpl-3.0.html#license-text
#

import sys
import os
import ctypes
import signal
import socket

# Force X11 (XWayland) — on native Wayland, Qt cannot position top-level windows;
# the compositor ignores all geometry hints. X11 gives full positioning control.
# VA-API hardware decode is unaffected (it uses DRM/libva, not the display server).
# The environment variable QT_QPA_PLATFORM=xcb  *MUST* be set in order for pyVid2-qt to operate correctly.
#
# IMPORTANT:
# Explicitly set QT_QPA_PLATFORM=xcb, Whether it is already set or not and regardless of if it is set to wayland or not.
os.environ['QT_QPA_PLATFORM'] = 'xcb'

# Qt Multimedia backend: GStreamer.
# --decoder (HWAccel.py) works by changing GStreamer decoder ranks, which only affects
# playback on Qt's GStreamer backend. Qt's default FFmpeg backend ignores those ranks and
# makes its own hardware choice (CUDA/NVDEC first), so --decoder vaapi would still decode on
# an NVIDIA GPU. setdefault() so an explicit QT_MEDIA_BACKEND in the environment still wins.
# Requires Qt's GStreamer media plugin (Arch: qt6-multimedia-gstreamer). The PyPI PySide6
# wheels do not ship it; Qt then silently falls back to FFmpeg (HWAccel warns about this).
os.environ.setdefault('QT_MEDIA_BACKEND', 'gstreamer')

# Suppress Qt multimedia framework logging (codec/stream info on stderr)
os.environ.setdefault('QT_LOGGING_RULES', 'qt.multimedia.*=false')

# Redirect C-level fd 2 to /dev/null — silences FFmpeg, PipeWire/SPA, GStreamer and any
# other C library that writes directly to the file descriptor, bypassing Python's sys.stderr.
# Python's own error output is preserved by duplicating the real fd first.
_real_stderr_fd = os.dup(2)
sys.stderr = os.fdopen(_real_stderr_fd, 'w', 1)   # Python errors still reach the terminal
_devnull = os.open(os.devnull, os.O_WRONLY)
os.dup2(_devnull, 2)                               # C libraries now write to /dev/null
os.close(_devnull)
del _real_stderr_fd, _devnull

# Suppress libavutil log output via its API (belt-and-suspenders with the fd redirect)
import ctypes.util as _cu
_libav = _cu.find_library('avutil')
if _libav:
    try:
        ctypes.cdll.LoadLibrary(_libav).av_log_set_level(-8)   # AV_LOG_QUIET
    except Exception:
        pass
del _cu, _libav

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSocketNotifier
from ui.main_window import MainWindow


# ── Remote restart (SIGUSR1) ────────────────────────────────────────────────
# `pkill -USR1 -f <something unique on the command line>` makes a running instance
# shut down cleanly and re-launch itself with exactly the same command line, working
# directory and environment, so the playlist is rescanned from the original sources.
# Re-launching in place keeps the desktop session's DISPLAY / XAUTHORITY etc., which
# is what makes this usable over ssh under Wayland/XWayland.
#
# SIGUSR1 (not SIGHUP): Linux sends SIGHUP when the launching terminal closes, and
# that must keep meaning "quit".
#
# A Python signal handler only runs when the interpreter gets control, which it does
# not while Qt's event loop sits waiting in C.  set_wakeup_fd() makes the C-level
# handler write the signal number to a socket; a QSocketNotifier on the other end
# wakes the event loop immediately.
_RESTART_SIGNAL = signal.SIGUSR1
_wake_rsock = None
_restart_requested = False


def _install_restart_signal():
    """Catch SIGUSR1 from the very start (its default action is to kill the process)."""
    global _wake_rsock
    rsock, wsock = socket.socketpair()
    rsock.setblocking(False)
    wsock.setblocking(False)
    signal.set_wakeup_fd(wsock.fileno(), warn_on_full_buffer=False)
    signal.signal(_RESTART_SIGNAL, lambda *_: None)   # real work: _on_signal_wakeup()
    _wake_rsock = (rsock, wsock)                         # keep both ends alive


def _watch_restart_signal(app, window):
    """Once Qt is up: act on SIGUSR1 (including one that arrived during startup)."""
    rsock = _wake_rsock[0]

    def _on_signal_wakeup():
        global _restart_requested
        try:
            data = rsock.recv(256)
        except (BlockingIOError, InterruptedError):
            return
        if _RESTART_SIGNAL in data and not _restart_requested:
            _restart_requested = True
            print("\nRestart requested (SIGUSR1): restarting pyVid2-qt...", flush=True)
            window.close()       # closeEvent: stop IR listener, close player
            app.quit()

    notifier = QSocketNotifier(rsock.fileno(), QSocketNotifier.Type.Read, app)
    notifier.activated.connect(_on_signal_wakeup)
    app._restart_notifier = notifier     # keep a reference


def _restart_self():
    """Replace this process with a fresh copy of itself (same args, cwd, environment)."""
    signal.set_wakeup_fd(-1)
    sys.stdout.flush()
    sys.stderr.flush()
    # fd 2 points at /dev/null (see top of file); hand the new process the real stderr,
    # or its Python tracebacks would be lost after the first restart.
    os.dup2(sys.stderr.fileno(), 2)
    # Run the same interpreter, but keep the original argv verbatim (e.g. "python main.py ...")
    # so `pgrep -f` / `pkill -f` patterns still match after any number of restarts.
    try:
        os.execv(sys.executable, sys.orig_argv)
    except OSError as e:
        print(f"Restart failed: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


def _qt_argv():
    """
    Return a copy of sys.argv with --display stripped out.
    Qt intercepts --display as an X11 display connection string (e.g,':0.0').
    We use it as a monitor-index selector instead, so Qt must not see it.
    """
    result = []
    skip_next = False
    for arg in sys.argv:
        if skip_next:
            skip_next = False
            continue
        if arg == '--display':
            skip_next = True
            continue
        result.append(arg)
    return result


def main():
    _install_restart_signal()

    from version import __version__

    # Parse CLI args BEFORE QApplication so decoder setup (rank changes, env vars)
    # happens before Qt's multimedia stack initializes its GStreamer pipeline.
    # Always parse — even with no args — so argparse enforces the required
    # source options (--Paths / --Files / --loadPlayList / --Glob) and exits
    # with usage instead of MainWindow crashing on opts=None.
    from cmdLineOpts import cmdLineOptions
    opts = cmdLineOptions()   # argparse reads original sys.argv, sees --display

    # Speed-tag tool operations (--addAutoSpeed / --delAutoSpeed / --searchAutoSpeed)
    # run without Qt — exit immediately after.
    if opts is not None and (
        opts.addAutoSpeed is not None
        or opts.delAutoSpeed
        or opts.searchAutoSpeed is not None
    ):
        from SpeedTag import run_tag_tool
        run_tag_tool(opts)
        sys.exit(0)

    # Detect available decoders, configure GStreamer ranks, print startup banner
    from HWAccel import setup_decoder, print_startup_info, warn_if_decoder_ineffective
    decoder_pref = opts.decoder if opts else 'auto'
    rgb_fallback = opts.rgbFallback if opts else 'software'
    active_label, available = setup_decoder(decoder_pref, rgb_fallback)
    print_startup_info(__version__, active_label, available, decoder_pref)
    if decoder_pref != 'auto':
        warn_if_decoder_ineffective(decoder_pref)

    # Pass Qt a display-stripped argv so it doesn't try to open X display "1"
    app = QApplication(_qt_argv())
    window = MainWindow(opts=opts)
    window.show()
    _watch_restart_signal(app, window)
    rc = app.exec()
    if _restart_requested:
        _restart_self()
    sys.exit(rc or window.exit_code)

if __name__ == "__main__":
    main()
