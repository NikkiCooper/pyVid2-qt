# pyVid2-qt

A fullscreen hardware-accelerated video player for Linux, built with PySide6 and GStreamer.
Designed for unattended or kiosk-style playback — shuffle, loop, variable speed, and IR remote control support.

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
  - [BASIC](#basic)
  - [ADVANCED](#advanced)
- [Running](#running-after-basic-install)
- [Command-Line Reference](#command-line-reference)
- [Controlling Playback with `.ignore` Files](#controlling-playback-with-ignore-files)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [IR Remote Control](#ir-remote-control)
- [Hardware Decoder Selection](#hardware-decoder-selection)
- [License](#license)

---

## Requirements

### System packages

Install these before running the installer:

```bash
# Arch Linux / Manjaro
sudo pacman -S python gst-plugins-good gst-plugins-bad gst-plugins-ugly \
               gst-libav gstreamer-vaapi python-gobject perl-image-exiftool
```

 **Python 3.10+**
- **GStreamer 1.0** with `gst-plugins-good`, `gst-plugins-bad`, `gst-plugins-ugly`, `gst-libav`
- **gstreamer-vaapi** — for VA-API hardware decoding (Intel / AMD)
- **python-gobject** — GStreamer Python bindings
- **exiftool** (`perl-image-exiftool`) — required only for speed-tag operations

> X11 or XWayland is required. Native Wayland is not supported.

---

## Installation

Clone the repository, then run the installer:

```bash
git clone https://github.com/NikkiCooper/pyVid2-qt.git
cd pyVid2-qt
./install.sh
```

The installer asks you to choose a mode:

### BASIC

Recommended for most users.

1. Creates `~/.local/share/pyVid2-qt` and copies fonts and icons from `ASSETS/`
2. Creates a Python virtual environment at `.venv/` inside the project directory
3. Installs Python dependencies (`PySide6`, `python-magic`) into the venv
4. Creates `~/bin/pyVid` — a launcher script that activates the venv and runs the player
5. Appends `export PATH="$PATH:$HOME/bin"` to `~/.bashrc`

After installation, open a new terminal and run:

```bash
pyVid --Paths /path/to/videos [options]
```

Or activate the PATH immediately in the current shell:

```bash
export PATH="$PATH:$HOME/bin"
pyVid --Paths /path/to/videos [options]
```

### ADVANCED

For users who manage their own Python environment (system Python, conda, pipx, etc.).

1. Creates `~/.local/share/pyVid2-qt` and copies fonts and icons from `ASSETS/`

Python dependencies, virtual environment, and PATH are left entirely to you. Run the program directly:

```bash
python /path/to/pyVid2-qt/main.py --Paths /path/to/videos [options]
```

---

## Running (after BASIC install)

```bash
pyVid --Paths /path/to/videos [options]
```

At least one source argument (`--Paths`, `--Files`, `--loadPlayList`, or `--Glob`) is required.

### Example

```bash
pyVid \
  --Paths /mnt/videos /mnt/more-videos \
  --shuffle \
  --loop \
  --loopDelay 2 \
  --playSpeed 5 \
  --display 1 \
  --autoSpeed \
  --mute \
  --sshotDir ~/Screenshots
```

---

## Command-Line Reference

### Source (one or more required, may be combined)

| Argument | Description |
|---|---|
| `--Paths <dir> [dir ...]` | Directories to scan recursively for video files |
| `--Files <file> [file ...]` | Explicit video files to load and play |
| `--loadPlayList <file> [file ...]` | Load playlist files (one path per line) |
| `--Glob <pattern> [pattern ...]` | Glob or numeric-range patterns. Supports `*`, `?`, `[...]`, `{N-M}`, `{N-}` |

### Video Playback Options

| Argument | Default | Description |
|---|---|---|
| `--loop` | off | Loop playlist instead of exiting at the end |
| `--shuffle` | off | Play videos in random order |
| `--loopDelay <seconds>` | `1` | Delay in seconds between videos |
| `--playSpeed <0.5–10.0>` | `2.0` | Playback speed multiplier |
| `--decoder <choice>` | `auto` | Hardware decoder: `auto` `nvdec` `vulkan` `vaapi` `software` |
| `--enableOSDcurpos` | off | Show always-visible playlist position counter (upper-left). Toggle with `o` key or IR `1` |
| `--autoSpeed` | off | Honour `auto_speed` XMP tags embedded in video files — applies a per-video speed override |

### Audio Options

| Argument | Default | Description |
|---|---|---|
| `--mute` | off | Start with audio muted |
| `--volume <0–100>` | `0` | Initial volume percentage |

### Screenshot Options

| Argument | Default | Description |
|---|---|---|
| `--sshotDir <path>` | `~/pyVid2-qt-Shots` | Directory where screenshots are saved |
| `--useJPG` | off | Save screenshots as JPEG instead of PNG |

### File Options

| Argument | Description |
|---|---|
| `--noIgnore` | Ignore `.ignore` files (all files in a directory are included) |
| `--noRecurse` | Do not recurse into subdirectories (applies to `--Paths` and `--Glob`) |
| `--printIgnoreList` | Print all `.ignore` files found under `--Paths` directories |

### System Options

| Argument | Default | Description |
|---|---|---|
| `--display <N>` | active display | Target a specific monitor by index |
| `--verbose` | off | Enable verbose console output |
| `--metadata` | off | Print video metadata to the console |
| `--udp-port <port>` | `5005` | UDP port for IR remote control commands |
| `--ir-keymap <path>` | `~/.local/share/pyVid2-qt/ir_keymap.conf` | Path to a custom IR remote keymap file |
| `--disable-IR` | off | Disable the IR remote control UDP listener |

### Speed Tag Tools

These operate on video file metadata (XMP tags) and exit immediately after running. Requires `exiftool`.
`--addAutoSpeed` and `--delAutoSpeed` cannot be combined with `--loadPlayList`.

| Argument | Description |
|---|---|
| `--addAutoSpeed <speed>` | Write an `auto_speed` XMP tag to matched files. Speed must be one of: `0.5 1 1.5 2 2.5 3 3.5 4 4.5 5 5.5 6` |
| `--delAutoSpeed` | Remove the `auto_speed` XMP tag from matched files. Prompts for confirmation. |
| `--searchAutoSpeed [speed]` | Search for `auto_speed` tags and print a report. Omit speed to list all tagged files. |
| `--dryRun` | Preview what `--addAutoSpeed` or `--delAutoSpeed` would do without modifying any files |

---

## Controlling Playback with `.ignore` Files

When scanning large, deeply-nested video collections with `--Paths`, you often want certain directories excluded — work-in-progress encodes, partially downloaded files, backups, etc. — without having to manually maintain an exclusion list on the command line. `.ignore` files solve this.

### How it works

Place an empty file named `.ignore` in any directory you want excluded. When pyVid2-qt encounters a `.ignore` file while scanning, it skips **all video files in that directory**. Each directory is evaluated independently — sibling and parent directories are unaffected.

> The file only needs to exist. Its contents are ignored. You can also name it anything ending in `.ignore` (e.g. `skip.ignore`, `wip.ignore`).

### Example directory structure

```
/mnt/Videos/
├── Movies/
│   ├── Action/
│   │   ├── film_a.mp4          ← played
│   │   └── film_b.mkv          ← played
│   ├── Drama/
│   │   ├── .ignore             ← Drama/ is excluded
│   │   ├── old_encode.mp4      ← skipped
│   │   └── rough_cut.mkv       ← skipped
│   └── SciFi/
│       ├── movie1.mp4          ← played
│       └── movie2.mkv          ← played
├── TV/
│   ├── ShowA/
│   │   ├── Season1/
│   │   │   ├── ep01.mp4        ← played
│   │   │   └── ep02.mp4        ← played
│   │   └── Season2/
│   │       ├── .ignore         ← Season2/ is excluded
│   │       ├── ep01.mp4        ← skipped
│   │       └── ep02.mp4        ← skipped
│   └── ShowB/
│       ├── ep01.mkv            ← played
│       └── ep02.mkv            ← played
└── WIP/
    ├── .ignore                 ← entire WIP/ directory excluded
    ├── transcode_test.mp4      ← skipped
    └── rough_edit.mkv          ← skipped
```

Running:
```bash
pyVid --Paths /mnt/Videos --shuffle --loop
```

pyVid2-qt will find and play everything **not** under a `.ignore`-marked directory:
`Action/`, `SciFi/`, `ShowA/Season1/`, and `ShowB/` — but not `Drama/`, `ShowA/Season2/`, or `WIP/`.

### Creating a `.ignore` file

```bash
touch /mnt/Videos/WIP/.ignore
touch /mnt/Videos/Movies/Drama/.ignore
```

### Related options

| Option | Effect |
|---|---|
| `--noIgnore` | Disables all `.ignore` file processing — every directory is scanned |
| `--printIgnoreList` | Prints the path of every `.ignore` file found during the scan |

To audit which directories are currently excluded before starting playback:
```bash
pyVid --printIgnoreList --Paths /mnt/Videos
```

---

## Keyboard Shortcuts

All shortcuts work while the player window is focused.

### Playback Control

| Key | Action |
|---|---|
| `Space` | Play / Pause |
| `N` | Next video |
| `P` | Previous video |
| `R` | Restart current video from the beginning |
| `L` | Toggle repeat (loop current video) |

### Seeking

| Key | Action |
|---|---|
| `→` (Right Arrow) | Seek forward 10 seconds |
| `←` (Left Arrow) | Seek backward 10 seconds |
| Mouse Wheel Up | Seek forward 10 seconds |
| Mouse Wheel Down | Seek backward 10 seconds |

### Speed

| Key | Action |
|---|---|
| `+` or `=` | Increase playback speed (steps: 0.5 → 1.0 → 1.5 → … → 6.0) |
| `-` | Decrease playback speed |

### Audio

| Key | Action |
|---|---|
| `↑` (Up Arrow) | Volume up (+5%) |
| `↓` (Down Arrow) | Volume down (−5%) |
| `M` | Mute / Unmute |

### Display & OSD

| Key | Action |
|---|---|
| `O` | Cycle position OSD: Off → position → position/duration → Off |
| `T` | Toggle video title display |
| `G` | Toggle greyscale |
| `H` | Show help overlay (cycles: keyboard → IR remote → Off) |

### Playlist

| Key | Action |
|---|---|
| `J` | Toggle shuffle (randomize / sort playlist) |
| `,` (Comma) | Print playlist to console |
| `.` (Period) | Save current playlist to a file |
| `Insert` | Show video metadata |

### Misc

| Key | Action |
|---|---|
| `S` | Take a screenshot |
| `Escape` or `Q` | Quit (or dismiss help overlay if open) |

---

## IR Remote Control

IR remote support is provided by a Raspberry Pi Pico W running `ir_wifi.py`, which decodes NEC IR signals
and forwards them to pyVid2-qt over UDP. Full setup instructions are in
**[IR_Pico_W/README.md](./IR_Pico_W/README.md)**.

Remote button names map to player actions via `~/.local/share/pyVid2-qt/ir_keymap.conf`.

### Default IR Key Actions

| IR Button | Action |
|---|---|
| `PWR` | Quit program |
| `PLAY_PAUSE` / `PLAY_PSE` | Play / Pause |
| `PLAY_NEXT` | Next video |
| `PLAY_PREV` | Previous video |
| `FWD` | Seek forward 10 seconds (repeats while held) |
| `REW` | Seek backward 10 seconds (repeats while held) |
| `SPEED+` | Increase playback speed |
| `SPEED-` | Decrease playback speed |
| `VOL+` | Volume up (repeats while held) |
| `VOL-` | Volume down (repeats while held) |
| `MUTE-UNMUTE` | Mute / Unmute |
| `LOOP` | Toggle repeat (loop current video) |
| `RESTART` | Restart current video |
| `SCREENSHOT` / `SCRNSHOT` | Take a screenshot |
| `MENU` | Show help overlay |
| `HUD` | Toggle HUD pin (keep HUD visible) |
| `1` | Cycle position OSD: Off → position → position/duration → Off |
| `3` | Save current playlist to a file |
| `4` | Print playlist to console |
| `5` | Randomize (shuffle) playlist |
| `6` | Show video metadata |
| `7` | Toggle video title display |

> Button codes in `ir_keymap.conf` are hex values from your specific remote. Edit this file to match
> the codes your remote actually sends. See [IR_Pico_W/README.md](IR_Pico_W/README.md) for full setup instructions,
> including how to discover your remote's codes using the Pico W debug output.

---

## Hardware Decoder Selection

At startup, pyVid2-qt probes available GStreamer decoder elements and prints a status table:

```
pyVid2-qt  version 0.75
────────────────────────────────────────────────────────
  Decoder:  VA-API      vah264dec                       [active]
            NVDEC       —                               [not available]
            Vulkan      —                               [not available]
            FFmpeg      avdec_h264                      [fallback]
────────────────────────────────────────────────────────
```

Use `--decoder auto` (default) to let GStreamer pick the highest-ranked available decoder, or force a specific backend with `--decoder vaapi`, `--decoder nvdec`, etc.

---

## License

GNU Lesser General Public License v3.0 — see [LICENSE](LICENSE).
