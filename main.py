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

# Force X11 (XWayland) — on native Wayland, Qt cannot position top-level windows;
# the compositor ignores all geometry hints. X11 gives full positioning control.
# VA-API hardware decode is unaffected (it uses DRM/libva, not the display server).
os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')

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
from ui.main_window import MainWindow


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
    from version import __version__

    # Parse CLI args BEFORE QApplication so decoder setup (rank changes, env vars)
    # happens before Qt's multimedia stack initializes its GStreamer pipeline.
    opts = None
    if len(sys.argv) > 1:
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
    from HWAccel import setup_decoder, print_startup_info
    decoder_pref = opts.decoder if opts else 'auto'
    active_label, available = setup_decoder(decoder_pref)
    print_startup_info(__version__, active_label, available)

    # Pass Qt a display-stripped argv so it doesn't try to open X display "1"
    app = QApplication(_qt_argv())
    window = MainWindow(opts=opts)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
