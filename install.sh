#!/usr/bin/env bash
#
#   install.sh — pyVid2-qt installer
#   Copyright (c) 2026 Nikki Cooper
#
#   Usage:  bash install.sh
#
#   BASIC mode runs pyVid2-qt on Arch Linux's own packages (system Python, Arch PySide6 /
#   Qt 6 / GStreamer). No virtual environment and no pip: the PyPI PySide6 wheels lack
#   Qt's GStreamer media backend, without which --decoder (e.g. VA-API) has no effect.
#

# Strict developer mode enabled safely
#set -euo pipefail
#
set -u
#
# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSETS_DIR="$SCRIPT_DIR/ASSETS"
DATA_DIR="$HOME/.local/share/pyVid2-qt"
BIN_DIR="$HOME/bin"
OLD_VENV_DIR="$SCRIPT_DIR/.venv"          # created by earlier versions of this installer
LAUNCHER="$BIN_DIR/pyVid"
BASH_COMPLETION_SRC="$ASSETS_DIR/pyVid2-bash-completion.sh"
BASH_COMPLETION_DST="$BIN_DIR/pyVid2-bash-completion.sh"

# System Python. '-s' keeps ~/.local user site-packages (e.g. a stray
# 'pip install --user PySide6') from shadowing the Arch packages.
PYTHON="/usr/bin/python3"
PYTHON_FLAGS="-s"

# ── Arch packages ──────────────────────────────────────────────────────────────
# Required: pyVid2-qt does not run correctly without these.
#   qt6-multimedia            QtMultimedia (the Arch pyside6 package lists it only as OPTIONAL)
#   qt6-multimedia-gstreamer  Qt's GStreamer media backend (used by main.py; --decoder needs it)
#   python-gobject            GStreamer Python bindings (decoder detection / selection)
#   gst-plugins-good          MP4/Matroska demuxers;  gst-libav: software decoders
# Everything else Qt/GStreamer needs (xcb-util-cursor, libpulse, pipewire, libmagic, the
# H.264/HEVC parsers and NVDEC in gst-plugins-bad-libs, ...) is pulled in by these.
REQUIRED_PKGS=(python pyside6 qt6-multimedia qt6-multimedia-gstreamer
               python-gobject python-magic gst-plugins-good gst-libav)

# Recommended: specific features degrade without these.
declare -A RECOMMENDED_PKGS=(
    [gst-plugin-va]="VA-API hardware decoding (Intel / AMD) — --decoder vaapi"
    [gst-plugins-bad]="additional formats and codecs"
    [gst-plugins-ugly]="additional formats and codecs"
    [perl-image-exiftool]="speed-tag operations (--addAutoSpeed, --autoSpeed, ...)"
)

# ── Colours ────────────────────────────────────────────────────────────────────
BOLD='\033[1m'
RESET='\033[0m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
DIM='\033[2m'

# ── Helpers ────────────────────────────────────────────────────────────────────
info()    { echo -e "  ${GREEN}=>${RESET} $*"; }
warn()    { echo -e "  ${YELLOW}!${RESET}  $*"; }
error()   { echo -e "  ${RED}ERROR:${RESET} $*" >&2; }
heading() { echo -e "\n${BOLD}${CYAN}$*${RESET}"; }

# ── Banner ─────────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║         pyVid2-qt  Installer             ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo

# inform about the necessary dependencies
echo -e "${BOLD} REQUIREMENTS (BASIC — Arch Linux packages)${RESET}"
echo
echo -e "      ${BOLD}${CYAN}• Required${RESET}${DIM}    — ${REQUIRED_PKGS[*]}${RESET}"
echo -e "      ${BOLD}${CYAN}• Recommended${RESET}${DIM} — ${!RECOMMENDED_PKGS[*]}${RESET}"
echo
echo -e "${BOLD}${YELLOW}The installer checks for these and prints the pacman command for anything missing.${RESET}"
echo -e "${BOLD}${YELLOW}Hardware drivers (intel-media-driver, libva-mesa-driver, nvidia) are not checked.${RESET}"
echo

# ── Installation mode selection ────────────────────────────────────────────────
echo -e "${BOLD}Choose an installation mode:${RESET}"
echo
echo -e "  ${BOLD}[B] BASIC${RESET}  ${DIM}(Arch Linux — recommended)${RESET}"
echo -e "      ${DIM}• Checks that the required Arch packages are installed and importable${RESET}"
echo -e "      ${DIM}• Creates ~/.local/share/pyVid2-qt and installs fonts and icons${RESET}"
echo -e "      ${DIM}• Creates ~/bin/pyVid — a launcher that runs pyVid2-qt with the system Python${RESET}"
echo -e "      ${DIM}  (no virtual environment, no pip); adds ~/bin to PATH in ~/.bashrc${RESET}"
echo -e "      ${DIM}• Installs ~/bin/pyVid2-bash-completion.sh and sources it from ~/.bashrc${RESET}"
echo
echo -e "        ${BOLD}  After install: run 'pyVid --Paths /your/videos [options]'${RESET}"
echo
echo -e "  ${BOLD}[A] ADVANCED${RESET}  ${DIM}(other distributions / custom environments — unsupported)${RESET}"
echo -e "      ${DIM}• Creates ~/.local/share/pyVid2-qt and installs fonts and icons only${RESET}"
echo -e "      ${DIM}• Qt 6, PySide6, GStreamer, Python environment, PATH, and shell completion are managed by you${RESET}"
echo
echo -e "        ${BOLD}  After install: run 'python ${SCRIPT_DIR}/main.py --Paths /your/videos [options]'${RESET}"
echo
echo -e "  ${BOLD}[Q] Quit${RESET}"
echo

read -rp "  Your choice [B/A/Q]: " MODE
echo

case "${MODE^^}" in
    B) ;;
    A) ;;
    Q|"") echo "Aborted."; exit 0 ;;
    *)    echo "Aborted."; exit 0 ;;
esac

# ── BASIC: Step 1 — check Arch packages (before anything is installed) ────────
if [[ "${MODE^^}" == "B" ]]; then
    heading "Checking Arch Linux packages"

    if ! command -v pacman &>/dev/null; then
        error "pacman not found. BASIC mode requires Arch Linux (or an Arch-based distribution)."
        error "On other distributions use ADVANCED mode and install the equivalents yourself."
        exit 1
    fi

    MISSING_REQ=()
    for pkg in "${REQUIRED_PKGS[@]}"; do
        if pacman -Q "$pkg" &>/dev/null; then
            info "$pkg"
        else
            echo -e "  ${RED}✗${RESET}  $pkg  ${DIM}(required)${RESET}"
            MISSING_REQ+=("$pkg")
        fi
    done

    MISSING_REC=()
    for pkg in "${!RECOMMENDED_PKGS[@]}"; do
        if pacman -Q "$pkg" &>/dev/null; then
            info "$pkg"
        else
            warn "$pkg  ${DIM}(recommended — ${RECOMMENDED_PKGS[$pkg]})${RESET}"
            MISSING_REC+=("$pkg")
        fi
    done

    if (( ${#MISSING_REQ[@]} > 0 )); then
        echo
        error "Required packages are missing. Install them and re-run the installer:"
        echo
        echo -e "    ${CYAN}sudo pacman -S --needed ${MISSING_REQ[*]} ${MISSING_REC[*]}${RESET}"
        echo
        exit 1
    fi

    if (( ${#MISSING_REC[@]} > 0 )); then
        echo
        warn "Recommended packages are missing; the features listed above will be unavailable."
        warn "To install them:  ${CYAN}sudo pacman -S --needed ${MISSING_REC[*]}${RESET}"
    fi

    # ── BASIC: Step 2 — verify the system Python can actually use them ────────
    heading "Verifying system Python modules"

    if [[ ! -x "$PYTHON" ]]; then
        error "$PYTHON not found. Install it and re-run:  sudo pacman -S python"
        exit 1
    fi
    info "Python: $PYTHON  ($("$PYTHON" --version 2>&1))"

    # Each check: label | python code that exits non-zero / raises on failure | fix hint
    CHECKS=(
        "PySide6 (Arch package)|import PySide6, sys; sys.exit(0 if PySide6.__file__.startswith('/usr/lib/') else 1)|the PySide6 found is not the Arch package; remove any pip-installed PySide6 and run: sudo pacman -S pyside6"
        "QtMultimedia|from PySide6 import QtMultimedia, QtMultimediaWidgets|sudo pacman -S qt6-multimedia"
        "Qt GStreamer media backend|import os, sys; from PySide6.QtCore import QLibraryInfo as L; sys.exit(0 if os.path.isfile(os.path.join(L.path(L.LibraryPath.PluginsPath), 'multimedia', 'libgstreamermediaplugin.so')) else 1)|sudo pacman -S qt6-multimedia-gstreamer"
        "GStreamer Python bindings|import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst; Gst.init(None)|sudo pacman -S python-gobject gstreamer"
        "python-magic|import magic; magic.Magic(mime=True)|sudo pacman -S python-magic"
    )

    FAILED=0
    for check in "${CHECKS[@]}"; do
        IFS='|' read -r label code hint <<< "$check"
        if "$PYTHON" $PYTHON_FLAGS -c "$code" &>/dev/null; then
            info "$label"
        else
            echo -e "  ${RED}✗${RESET}  $label"
            error "  Fix: $hint"
            FAILED=1
        fi
    done

    if (( FAILED )); then
        FOUND="$("$PYTHON" $PYTHON_FLAGS -c 'import PySide6; print(PySide6.__file__)' 2>/dev/null)"
        [[ -n "$FOUND" ]] && warn "PySide6 currently loads from: $FOUND"
        echo
        error "System Python cannot load everything pyVid2-qt needs. Fix the items above and re-run."
        exit 1
    fi

    info "GStreamer: $("$PYTHON" $PYTHON_FLAGS -c "import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst; Gst.init(None); print(Gst.version_string())" 2>/dev/null)"
    info "PySide6:   $("$PYTHON" $PYTHON_FLAGS -c "import PySide6; print(PySide6.__version__, '—', PySide6.__file__.rsplit('/', 2)[0])" 2>/dev/null)"
fi

# ── Install assets (both modes) ────────────────────────────────────────────────
heading "Installing assets to $DATA_DIR"

install -d "$DATA_DIR/fonts"
install -d "$DATA_DIR/Resources"

# Ensure assets directory exists before copying to avoid script crash under set -e
if [[ -d "$ASSETS_DIR" ]]; then
    cp -r "$ASSETS_DIR/fonts/."     "$DATA_DIR/fonts/"
    cp -r "$ASSETS_DIR/Resources/." "$DATA_DIR/Resources/"
    [[ -f "$ASSETS_DIR/ir_keymap.conf" ]] && cp "$ASSETS_DIR/ir_keymap.conf" "$DATA_DIR/"
else
    error "Assets folder not found at $ASSETS_DIR."
    exit 1
fi

info "Fonts installed    → $DATA_DIR/fonts/"
info "Resources installed → $DATA_DIR/Resources/"
info "ir_keymap.conf installed → $DATA_DIR/"

# ── ADVANCED: done ─────────────────────────────────────────────────────────────
if [[ "${MODE^^}" == "A" ]]; then
    echo
    echo -e "${BOLD}${GREEN}Advanced install complete.${RESET}"
    echo
    echo -e "  Assets are installed to ${CYAN}$DATA_DIR${RESET}"
    echo -e "  Provide Qt 6 + QtMultimedia with its GStreamer backend, PySide6, GStreamer,"
    echo -e "  python-gobject and python-magic (see README.md, Requirements), then run:"
    echo -e "  ${CYAN}python $SCRIPT_DIR/main.py --Paths /your/videos [options]${RESET}"
    echo
    echo -e "  Bash completion is available at:"
    echo -e "  ${CYAN}$BASH_COMPLETION_SRC${RESET}"
    echo -e "  To enable pyVid shell completion, install pyVid2-bash-completion.sh manually"
    echo -e "  and source it from your shell startup file."
    echo
    exit 0
fi

# ── BASIC: Step 3 — old virtual environment from earlier installers ───────────
if [[ -d "$OLD_VENV_DIR" ]]; then
    heading "Old virtual environment found"
    warn "$OLD_VENV_DIR exists. pyVid2-qt no longer uses it (BASIC now runs on the system Python)."
    warn "If an IDE (e.g. PyCharm) uses it as its project interpreter, keep it."
    read -rp "  Remove $OLD_VENV_DIR? [y/N]: " RM_VENV
    if [[ "${RM_VENV,,}" == "y" ]]; then
        rm -rf "$OLD_VENV_DIR"
        info "Removed $OLD_VENV_DIR"
    else
        info "Kept $OLD_VENV_DIR (unused by pyVid)"
    fi
fi

# ── BASIC: Step 4 — launcher script ───────────────────────────────────────────
heading "Creating launcher: $LAUNCHER"

install -d "$BIN_DIR"

command cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
#  pyVid — pyVid2-qt launcher (generated by install.sh)
#  Runs pyVid2-qt with the Arch system Python and system packages (PySide6 / Qt 6 /
#  GStreamer). '${PYTHON_FLAGS}' ignores ~/.local user site-packages so a pip-installed
#  PySide6 cannot shadow the Arch one.
PROJ="${SCRIPT_DIR}"
exec ${PYTHON} ${PYTHON_FLAGS} "\${PROJ}/main.py" "\$@"
LAUNCHER_EOF

chmod +x "$LAUNCHER"
info "Launcher created   → $LAUNCHER"

# ── BASIC: Step 5 — bash completion ───────────────────────────────────────────
heading "Installing bash completion: $BASH_COMPLETION_DST"

if [[ -f "$BASH_COMPLETION_SRC" ]]; then
    cp "$BASH_COMPLETION_SRC" "$BASH_COMPLETION_DST"
    chmod +x "$BASH_COMPLETION_DST"
    info "Bash completion installed → $BASH_COMPLETION_DST"
else
    warn "Bash completion script not found at $BASH_COMPLETION_SRC — skipping."
fi

# ── BASIC: Step 6 — PATH in ~/.bashrc ─────────────────────────────────────────
heading "Updating PATH in ~/.bashrc"

PATH_LINE='export PATH="$PATH:$HOME/bin"'

if grep -qE '(\$HOME|~)/bin' "${HOME:-}/.bashrc" 2>/dev/null; then
    warn "~/bin already present in ~/.bashrc PATH — skipping."
else
    echo "" >> "$HOME/.bashrc"
    echo "# Added by pyVid2-qt installer" >> "$HOME/.bashrc"
    echo "$PATH_LINE" >> "$HOME/.bashrc"
    info "Appended to ~/.bashrc: $PATH_LINE"
fi

# ── BASIC: Step 7 — bash completion in ~/.bashrc ──────────────────────────────
heading "Updating bash completion in ~/.bashrc"

BASH_COMPLETION_LINE='source ~/bin/pyVid2-bash-completion.sh'

if grep -qF "$BASH_COMPLETION_LINE" "${HOME:-}/.bashrc" 2>/dev/null; then
    warn "pyVid2-qt bash completion already sourced in ~/.bashrc — skipping."
else
    echo "" >> "$HOME/.bashrc"
    echo "# pyVid2-qt bash completion script" >> "$HOME/.bashrc"
    echo "$BASH_COMPLETION_LINE" >> "$HOME/.bashrc"
    info "Appended pyVid2-qt bash completion source line to ~/.bashrc"
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}${GREEN}Basic install complete.${RESET}"
echo
echo -e "  Assets     → ${CYAN}$DATA_DIR${RESET}"
echo -e "  Python     → ${CYAN}$PYTHON $PYTHON_FLAGS${RESET}  (system packages)"
echo -e "  Launcher   → ${CYAN}$LAUNCHER${RESET}"
echo -e "  Completion → ${CYAN}$BASH_COMPLETION_DST${RESET}"
echo
echo -e "  ${BOLD}To use pyVid immediately in this shell:${RESET}"
echo -e "    ${CYAN}export PATH=\"\$PATH:\$HOME/bin\"${RESET}"
echo -e "    ${CYAN}source ~/bin/pyVid2-bash-completion.sh${RESET}"
echo -e "    ${CYAN}pyVid --Paths /your/videos [options]${RESET}"
echo
echo -e "  In new terminals the PATH and pyVid2 bash completion will be set automatically via ~/.bashrc."
echo
