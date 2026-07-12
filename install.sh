#!/usr/bin/env bash
#
#   install.sh — pyVid2-qt installer
#   Copyright (c) 2026 Nikki Cooper
#
#   Usage:  bash install.sh
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
VENV_DIR="$SCRIPT_DIR/.venv"
LAUNCHER="$BIN_DIR/pyVid"

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
echo -e "${BOLD} REQUIREMENTS${RESET}"
echo
echo -e "      ${BOLD}${CYAN}• Python 3.10+${RESET}"
echo -e "      ${BOLD}${CYAN}• GStreamer 1.0${RESET}${DIM}   — With gst-plugins-good, gst-plugins-bad, gst-plugins-ugly, gst-libav${RESET}"
echo -e "      ${BOLD}${CYAN}• gstreamer-vaapi${RESET}${DIM} — For VA-API hardware decoding (Intel / AMD)${RESET}"
echo -e "      ${BOLD}${CYAN}• python-gobject${RESET}${DIM} — GStreamer Python bindings${RESET}"
echo -e "      ${BOLD}${CYAN}• exiftool${RESET}${DIM}        — required only for speed-tag operations${RESET}"
echo
echo -e "${BOLD}${YELLOW}These must be already installed prior to running this script${RESET}"
echo
# ── Installation mode selection ────────────────────────────────────────────────
echo -e "${BOLD}Choose an installation mode:${RESET}"
echo
echo -e "  ${BOLD}[B] BASIC${RESET}"
echo -e "      ${DIM}• Creates ~/.local/share/pyVid2-qt and installs fonts and icons${RESET}"
echo -e "      ${DIM}• Creates a Python virtual environment inside the project directory${RESET}"
echo -e "      ${DIM}• Installs Python dependencies (PySide6, python-magic) into the venv${RESET}"
echo -e "      ${DIM}• Creates ~/bin/pyVid — a launcher script that activates the venv${RESET}"
echo -e "        and runs pyVid2-qt; adds ~/bin to PATH in ~/.bashrc${RESET}"
echo
echo -e "        ${BOLD}  After install: run 'pyVid --Paths /your/videos [options]'${RESET}"
echo
echo -e "  ${BOLD}[A] ADVANCED${RESET}"
echo -e "      ${DIM}• Creates ~/.local/share/pyVid2-qt and installs fonts and icons only${RESET}"
echo -e "      ${DIM}• Python environment, dependencies, and PATH are managed by you${RESET}"
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

# ── Step 1: Install assets (both modes) ───────────────────────────────────────
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
    echo -e "  Manage your Python environment and run:"
    echo -e "  ${CYAN}python $SCRIPT_DIR/main.py --Paths /your/videos [options]${RESET}"
    echo
    exit 0
fi

# ── BASIC: Step 2 — virtual environment ───────────────────────────────────────
heading "Creating virtual environment"

# Find a suitable Python (3.10+)
PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" &>/dev/null; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    error "Python 3.10 or newer not found. Install Python and re-run."
    exit 1
fi

info "Using Python: $(command -v "$PYTHON")  ($("$PYTHON" --version))"

if [[ -d "$VENV_DIR" ]]; then
    warn "Existing virtual environment found at $VENV_DIR — removing and recreating."
    rm -rf "$VENV_DIR"
fi

"$PYTHON" -m venv "$VENV_DIR"
info "Virtual environment created at $VENV_DIR"

# ── BASIC: Step 3 — pip dependencies ──────────────────────────────────────────
heading "Installing Python dependencies"

"$VENV_DIR/bin/pip" install --upgrade pip --quiet
info "pip upgraded"

DEPS=(PySide6 python-magic)

for dep in "${DEPS[@]}"; do
    echo -n "  Installing ${dep}... "
    if "$VENV_DIR/bin/pip" install "$dep" --quiet; then
        echo -e "${GREEN}done${RESET}"
    else
        echo -e "${RED}FAILED${RESET}"
        error "Failed to install $dep. Check your internet connection and try again."
        exit 1
    fi
done

# ── BASIC: Step 4 — launcher script ───────────────────────────────────────────
heading "Creating launcher: $LAUNCHER"

install -d "$BIN_DIR"

command cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
#  pyVid — pyVid2-qt launcher (generated by install.sh)
#  Activates the project virtual environment and runs pyVid2-qt.
PROJ="${SCRIPT_DIR}"
source "\${PROJ}/.venv/bin/activate"
exec python "\${PROJ}/main.py" "\$@"
LAUNCHER_EOF

chmod +x "$LAUNCHER"
info "Launcher created   → $LAUNCHER"

# ── BASIC: Step 5 — PATH in ~/.bashrc ─────────────────────────────────────────
heading "Updating PATH in ~/.bashrc"

PATH_LINE='export PATH="$PATH:$HOME/bin"'

# Fixed regex matching by replacing grep -qF with grep -qE
#if grep -qE '(\$HOME|~)/bin' "$HOME/.bashrc" 2>/dev/null; then\
if grep -qE '(\$HOME|~)/bin' "${HOME:-}/.bashrc" 2>/dev/null; then
    warn "~/bin already present in ~/.bashrc PATH — skipping."
else
    echo "" >> "$HOME/.bashrc"
    echo "# Added by pyVid2-qt installer" >> "$HOME/.bashrc"
    echo "$PATH_LINE" >> "$HOME/.bashrc"
    info "Appended to ~/.bashrc: $PATH_LINE"
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}${GREEN}Basic install complete.${RESET}"
echo
echo -e "  Assets    → ${CYAN}$DATA_DIR${RESET}"
echo -e "  Venv      → ${CYAN}$VENV_DIR${RESET}"
echo -e "  Launcher  → ${CYAN}$LAUNCHER${RESET}"
echo
echo -e "  ${BOLD}To use pyVid immediately in this shell:${RESET}"
echo -e "    ${CYAN}export PATH=\"\$PATH:\$HOME/bin\"${RESET}"
echo -e "    ${CYAN}pyVid --Paths /your/videos [options]${RESET}"
echo
echo -e "  In new terminals the PATH will be set automatically via ~/.bashrc."
echo