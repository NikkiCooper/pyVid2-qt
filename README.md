# pyVid2-qt

A fullscreen hardware-accelerated video player for Linux, built with PySide6 and GStreamer.
Designed for unattended or kiosk-style playback — shuffle, loop, variable speed, and IR remote control support.

---

> **Personal project notice:** pyVid2-qt was written for my specific workflow and
> is not presented as a general-purpose application suitable for anyone else's use. If you find
> anything in this codebase useful for your own purposes, you are welcome to it — that is
> contribution enough to the free software ecosystem.

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
  - [BASIC](#basic)
  - [ADVANCED](#advanced)
- [Running](#running-after-basic-install)
- [Command-Line Reference](#command-line-reference)
- [Per-Video Playback Speed (Auto Speed Tags)](#per-video-playback-speed-auto-speed-tags)
- [Controlling Playback with `.ignore` Files](#controlling-playback-with-ignore-files)
- [Sub-Playlists (Model Filter)](#sub-playlists-model-filter)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [IR Remote Control](#ir-remote-control)
- [Hardware Decoder Selection](#hardware-decoder-selection)
- [License](#license)

---

## Requirements

> **Platform:** pyVid2-qt is developed and tested on **Arch Linux**, which is the supported
> platform. The BASIC installer is Arch-only: it checks your system's packages with `pacman`.
> Other distributions can use the ADVANCED install (see [Installation](#installation)), but that
> setup is unsupported.

> **Hardware drivers are not installed for you.** Neither installer mode installs GPU drivers,
> VA-API drivers, CUDA or OpenCV. If you want hardware-accelerated decoding, they must already be
> installed and working system-wide (see [VA-API](#va-api-hardware-decoding-intel--amd) and
> [NVDEC](#nvdec-hardware-decoding-nvidia--cuda) below).

> X11 or XWayland is required. Native Wayland is not supported.

### What pyVid2-qt needs at runtime

| Component | Why it is needed | Arch package(s) |
|---|---|---|
| **Python 3.10+** (system Python) | Runs the application | `python` |
| **PySide6** | Python bindings for Qt 6 | `pyside6` |
| **Qt 6 QtMultimedia** | All video and audio playback | `qt6-multimedia` (**not** pulled in by `pyside6`; see below) |
| **Qt 6 GStreamer media backend** | The playback engine pyVid2-qt uses; required for `--decoder` | `qt6-multimedia-gstreamer` |
| **GStreamer 1.0** + plugins | Demuxing and decoding | `gst-plugins-good`, `gst-libav` (both required); `gst-plugins-bad`, `gst-plugins-ugly` (recommended, extra formats) |
| **GStreamer VA-API plugin** | VA-API hardware decoding (Intel / AMD), `--decoder vaapi` | `gst-plugin-va` (recommended) |
| **python-gobject** | GStreamer Python bindings: decoder detection and `--decoder` selection | `python-gobject` |
| **python-magic** | Identifies video files by MIME type | `python-magic` |
| **exiftool** | Speed-tag operations only (`--addAutoSpeed`, `--delAutoSpeed`, `--searchAutoSpeed`, `--autoSpeed`) | `perl-image-exiftool` (recommended) |

The rest of what Qt and GStreamer need is pulled in automatically by the packages above. That
includes Qt's X11/XCB libraries (`xcb-util-cursor`, `libxkbcommon-x11`), audio (`libpulse`,
`pipewire`), `libmagic` (`file`), the H.264/HEVC parsers, and the NVDEC decoders
(`gst-plugins-bad-libs`).

### Arch Linux packages

Install everything, required and recommended, with:

```bash
sudo pacman -S --needed python pyside6 qt6-multimedia qt6-multimedia-gstreamer \
               python-gobject python-magic gst-plugins-good gst-libav \
               gst-plugin-va gst-plugins-bad gst-plugins-ugly perl-image-exiftool
```

The BASIC installer checks for all of these. If anything is missing, it prints the exact
`pacman` command and stops before installing anything.

Things worth knowing:

- **The Arch `pyside6` package does not pull in QtMultimedia.** It lists `qt6-multimedia` only as
  an *optional* dependency, so it must be named explicitly. Without it, pyVid2-qt fails at
  startup with `ModuleNotFoundError: No module named 'PySide6.QtMultimedia'`.
- **The GStreamer backend is required, not optional.** `main.py` sets
  `QT_MEDIA_BACKEND=gstreamer`; an explicit `QT_MEDIA_BACKEND` in your environment still wins.
  `--decoder` works by ranking GStreamer decoder elements. Qt's other backend, FFmpeg
  (`qt6-multimedia-ffmpeg`), ignores those ranks and makes its own hardware choice (CUDA/NVDEC
  first), so on a machine with an NVIDIA GPU it would always decode there, even with
  `--decoder vaapi`. If the GStreamer backend is unavailable, pyVid2-qt prints a warning at
  startup when `--decoder` is set.
- **Do not use PySide6 from pip.** The PyPI PySide6 wheels bundle their own Qt 6 with only the
  FFmpeg backend, so `--decoder`, VA-API, and the RGB-video colour fix
  ([Hardware Decoder Selection](#hardware-decoder-selection)) do not work with them. The BASIC
  launcher runs Python with `-s` so that a `pip install --user PySide6` in `~/.local` cannot
  shadow the Arch package.
- The older `gstreamer-vaapi` package is no longer in the Arch repositories. `gst-plugin-va`
  replaces it.

### VA-API hardware decoding (Intel / AMD)

VA-API is a vendor-neutral Linux video API used by both Intel and AMD GPUs; `--decoder vaapi`
selects it on either. (NVIDIA uses NVDEC instead; see below.) `gst-plugin-va` provides the
GStreamer VA-API decoders (`vah265dec`, `vah264dec`, ...). You also need the VA-API driver for
your GPU:

```bash
# Intel — Broadwell (5th gen) and later
sudo pacman -S intel-media-driver libva

# Intel — Haswell (4th gen) and earlier
sudo pacman -S libva-intel-driver libva

# AMD — Mesa's radeonsi VA-API driver. It is part of the 'mesa' package, which already
# replaced the former separate 'libva-mesa-driver' package.
sudo pacman -S mesa libva
```

On systems with an Intel GPU, `--decoder vaapi` sets `LIBVA_DRIVER_NAME=iHD` (unless you set it
yourself), so `libva-nvidia-driver`, if installed, cannot claim the NVIDIA GPU. On AMD-only
systems nothing is forced and libva picks `radeonsi` automatically.

### NVDEC hardware decoding (NVIDIA / CUDA)

The NVDEC GStreamer decoders (`nvh265dec`, `nvh264dec`, ...) are in `gst-plugins-bad-libs`
(pulled in automatically) but only activate when CUDA is present at runtime. A working NVIDIA
driver and the CUDA toolkit must both be installed system-wide:

```bash
# NVIDIA driver — choose one
sudo pacman -S nvidia           # proprietary (most GPUs)
sudo pacman -S nvidia-open      # open kernel module (Turing / RTX and later)

# CUDA toolkit
sudo pacman -S cuda             # in the extra repository
```

**OpenCV with CUDA support** is an additional requirement for certain processing features. The
standard `python-opencv` package does **not** include CUDA support. On Arch Linux the
CUDA-enabled build is in the Extra repository:

```bash
sudo pacman -S python-opencv-cuda
```

pacman will automatically pull in all required dependencies:
`fmt`, `glew`, `hdf5`, `jsoncpp`, `opencv-cuda`, `openmpi`, `pugixml`, `python-numpy`,
`qt6-base`, `vtk`

---

## Installation

Install the [Arch Linux packages](#arch-linux-packages) first. Then clone the repository and run
the installer:

```bash
git clone https://github.com/NikkiCooper/pyVid2-qt.git
cd pyVid2-qt
./install.sh
```

The installer asks you to choose a mode:

### BASIC

Recommended, and the supported setup on Arch Linux. pyVid2-qt runs on the system Python and
Arch's own PySide6 / Qt 6 / GStreamer packages. There is no virtual environment and no pip, so
nothing is downloaded and a `pacman -Syu` that upgrades Python or Qt keeps working.

1. Checks that the required Arch packages are installed (and reports missing recommended ones).
   If anything required is missing, it prints the `pacman` command and stops before installing
   anything.
2. Verifies that the system Python can load them. It checks that PySide6 is the Arch package,
   that QtMultimedia and Qt's GStreamer backend are present, and that the GStreamer bindings and
   python-magic load.
3. Creates `~/.local/share/pyVid2-qt` and copies fonts and icons from `ASSETS/`.
4. Creates `~/bin/pyVid`, a launcher that runs `/usr/bin/python3 -s main.py`.
5. Installs `~/bin/pyVid2-bash-completion.sh` and sources it from `~/.bashrc`.
6. Appends `export PATH="$PATH:$HOME/bin"` to `~/.bashrc`.

After installation, open a new terminal and run:

```bash
pyVid --Paths /path/to/videos [options]
```

Or activate the PATH immediately in the current shell:

```bash
export PATH="$PATH:$HOME/bin"
pyVid --Paths /path/to/videos [options]
```

> **Upgrading from an earlier version:** earlier installers created a virtual environment at
> `.venv/` in the project directory, with pip PySide6. The launcher no longer uses it. The
> installer offers to remove it, and the default is to keep it, in case an IDE such as PyCharm
> uses it as its project interpreter. Re-run `./install.sh` and choose BASIC to replace the old
> launcher.

### ADVANCED

Unsupported. For setups the BASIC installer cannot handle, such as other Linux distributions or
a hand-managed Python environment. On Arch Linux, BASIC should cover every normal case.

1. Creates `~/.local/share/pyVid2-qt` and copies fonts and icons from `ASSETS/`.

Everything else is up to you. You must provide the equivalents of the
[runtime requirements](#what-pyvid2-qt-needs-at-runtime): Qt 6 **with QtMultimedia and its
GStreamer backend**, PySide6 built against that Qt, GStreamer with the plugins above,
python-gobject, and python-magic. In practice that means your distribution's Qt and PySide6
packages, not pip, because the pip wheels have no GStreamer backend. Run the program directly:

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

| Cmd Line Argument               | Description |
|-------------------------------------|---|
| `--Paths` \<dir> [dir ...]          | Directories to scan recursively for video files |
| `--Files` \<file> [file ...]        | Explicit video files to load and play |
| `--loadPlayList` \<file> [file ...] | Load playlist files (one path per line). A relative name is looked up in the current directory, then in `$PLAYLIST_HOME` |
| `--Glob` \<pattern> [pattern ...]   | Glob or numeric-range patterns. Supports `*`, `?`, `[...]`, `{N-M}`, `{N-}` |

### Video Playback Options

| Cmd Line Argument    | Default | Description                                                  |
|----------------------|---------|--------------------------------------------------------------|
| `--loop`             | off     | Loop playlist instead of exiting at the end                  |
| `--noFilterLoop`     | off     | With `--loop`: don't loop a [sub-playlist](#sub-playlists-model-filter); return to the master playlist when it ends |
| `--shuffle`          | off     | Play videos in random order                                  |
| `--loopDelay` \<sec> | 1       | Delay in seconds between videos                              |
| `--playSpeed` \<spd> | 2.0     | Playback speed multiplier 0.5 - 10.0 in 0.5 increments       |
| `--decoder` \<dec>   | auto    | Hardware decoder: `auto` `nvdec` `vaapi` `software` |
| `--rgbFallback` \<dec> | software | With `--decoder vaapi`: decoder for [RGB-coded videos](#hardware-decoder-selection), which VA-API renders with wrong colours: `software` or `nvdec` |
| `--enableOSDcurpos`  | off     | Show always-visible playback position counter (upper-left). Toggle with `O` |
| `--autoSpeed`        | off     | Honour `auto_speed` XMP tags embedded in video files. See [Auto Speed Tags](#per-video-playback-speed-auto-speed-tags) |

> Speeds above 6× need proportionally more decoding work. 10× has been tested with 1080p HEVC
> on VA-API; 4K or 60 fps sources may not keep up at the highest speeds on slower GPUs.

### Audio Options

| Cmd Line Argument   | Default | Description |
|---------------------|---|---|
| `--mute`            | off | Start with audio muted |
| `--volume` \<0–100> | `0` | Initial volume percentage |

### Screenshot Options

| Cmd Line Argument | Default | Description |
|-----------------------|---|---|
| `--sshotDir` \<path>  | `~/pyVid2-qt-Shots` | Directory where screenshots are saved |
| `--useJPG`            | off | Save screenshots as JPEG instead of PNG |

### File Options

| Cmd Line Argument | Description |
|-----------------------|---|
| `--noIgnore`          | Ignore `.ignore` files (all files in a directory are included) |
| `--noRecurse`         | Do not recurse into subdirectories (applies to `--Paths` and `--Glob`) |
| `--printIgnoreList`   | Print all `.ignore` files found under `--Paths` directories |

### System Options

| Cmd Line Argument | Default | Description |
|-----------------------|---|---|
| `--display` \<N>      | active display | Target a specific monitor by index (`0`, `1`, …) or part of its name (case-sensitive, e.g. `HDMI`) |
| `--verbose`           | off | Enable verbose console output |
| `--metadata`          | off | Print video metadata to the console |
| `--cursorHide` \<sec> | `2` | Hide the mouse cursor after this many idle seconds (`0` = never) |
| `--udp-port` \<port>  | `5005` | UDP port for IR remote control commands |
| `--ir-keymap` \<path> | `~/.local/share/`<br>`pyVid2-qt/ir_keymap.conf` | Path to a custom IR remote keymap file |
| `--disable-IR`        | off | Disable the IR remote control UDP listener |

### Speed Tag Tools

These operate on video file metadata (XMP tags) and exit immediately after running.<br> Requires `exiftool`. See [Auto Speed Tags](#per-video-playback-speed-auto-speed-tags) for a full walkthrough.
`--addAutoSpeed` and `--delAutoSpeed` cannot be combined with `--loadPlayList`.

| Cmd Line Argument         | Description                                                                                                                             |
|---------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| `--addAutoSpeed` \<spd>   | Write an `auto_speed` XMP tag to matched files. Speed must be in range of `0.5 - 10` in `0.5` increments |
| `--delAutoSpeed`          | Remove the `auto_speed` XMP tag from matched files. Prompts for confirmation.                                                           |
| `--searchAutoSpeed` [spd] | Search for `auto_speed` tags and print a report. Omit speed to list all tagged files.                                                   |
| `--dryRun`                | Preview what `--addAutoSpeed` or `--delAutoSpeed` would do without modifying any files                                                  |

---

## Per-Video Playback Speed (Auto Speed Tags)

Most of a collection usually plays fine at a single speed, but some videos need a different one:
a slow scene you want to watch at 1×, or a long, uneventful video you want to get through at 8×.
Rather than pressing `+`/`-` every time one of those comes up, you can store the preferred speed
**inside the video file itself** as an XMP metadata tag called **Auto Speed**. When `--autoSpeed`
is on, pyVid2-qt reads that tag as each video starts and plays the video at the stored speed.

- Auto Speed values range from **0.5×** to **10×** in **0.5** increments (0.5, 1, 1.5, … 9.5, 10).
  These are the same steps `--playSpeed` and the `+`/`-` keys use.
- The tag is written to the file's XMP metadata (`XMP-pyvid2:AutoSpeed`, shown in reports as
  `auto_speed_<speed>`, e.g. `auto_speed_4.5`). Only the metadata changes; the audio and video
  streams are not re-encoded.
- All Auto Speed operations need `exiftool` (`sudo pacman -S perl-image-exiftool`).

### How `--playSpeed` and `--autoSpeed` work together

`--playSpeed` sets the **base speed** for the session (default `2.0`). With `--autoSpeed` on:

| Video                                | Plays at                                |
|--------------------------------------|-----------------------------------------|
| No Auto Speed tag                    | The base speed from `--playSpeed`       |
| Has an Auto Speed tag (e.g. `1.5`)   | The tag's speed, for that video only    |
| Next untagged video after a tagged one | Back to the base speed, automatically |

When a tagged video starts and its speed differs from the current one, the OSD shows
`Auto Speed: auto_speed_<speed>` for a moment. Once that video ends, the base speed comes back
for the next video.

> Any speed change you make with `+`/`-` while a tagged video is playing lasts only for that
> video. The base speed comes back when the next video starts.

Without `--autoSpeed`, the tags are ignored and every video plays at `--playSpeed`.

```bash
# Play most videos at 5×, but use each file's Auto Speed tag when it has one
pyVid --Paths /mnt/videos --playSpeed 5 --autoSpeed
```

### Managing tags: `--addAutoSpeed`, `--delAutoSpeed`, `--searchAutoSpeed`

These three options are command-line tools, not playback options. They build a file list from the
usual sources (`--Paths`, `--Files`, `--Glob`, plus `--noRecurse` and `.ignore` files), do their
job, print a report, and exit without opening the player.

| Option                      | Sources allowed                                    | Confirmation                         |
|-----------------------------|----------------------------------------------------|--------------------------------------|
| `--addAutoSpeed` \<spd>     | `--Paths` `--Files` `--Glob`                       | Type `Yes` when tagging 20+ files    |
| `--delAutoSpeed`            | `--Paths` `--Files` `--Glob`                       | Always asks you to type `Yes`        |
| `--searchAutoSpeed` [spd]   | `--Paths` `--Files` `--Glob` `--loadPlayList`      | None (read-only)                     |

`Yes` is case-sensitive. Pressing Enter or typing anything else cancels the operation.

#### `--addAutoSpeed <speed>`: add an Auto Speed tag

Writes an Auto Speed tag with the given speed to every matched file. If a file already has a tag,
it is replaced. Before writing, pyVid2-qt scans the files and shows how many are untagged, how many
already have this speed, and how many have a different speed (listed as `old → new`).

```bash
# Tag one video to always play at 1.5×
pyVid --Files ~/Videos/slow_scene.mp4 --addAutoSpeed 1.5

# Tag every video in a directory tree for 8× playback, previewing first
pyVid --Paths /mnt/videos/long-recordings --addAutoSpeed 8 --dryRun
pyVid --Paths /mnt/videos/long-recordings --addAutoSpeed 8

# Tag files matching a glob pattern
pyVid --Glob "/mnt/videos/lecture_{1-12}.mkv" --addAutoSpeed 3
```

#### `--delAutoSpeed`: remove the Auto Speed tag

Removes the Auto Speed tag from the matched files. Only files that actually have a tag are
changed. The files to be changed are listed first, and you always have to type `Yes` before
anything is deleted.

```bash
# Preview which files would lose their tag
pyVid --Paths /mnt/videos --delAutoSpeed --dryRun

# Remove the tag from a single file
pyVid --Files ~/Videos/slow_scene.mp4 --delAutoSpeed
```

#### `--searchAutoSpeed [speed]`: find and report Auto Speed tags

Scans the matched files and prints a report of the tagged ones, grouped by speed, with a summary
bar chart. Leave out the speed to list every tagged file, or give one to show only files tagged
with that speed. Nothing is modified. Unlike the other two tools, this one also accepts
`--loadPlayList`.

```bash
# Report every Auto Speed tag in a collection
pyVid --Paths /mnt/videos --searchAutoSpeed

# Show only files tagged for 4.5× playback
pyVid --Paths /mnt/videos /mnt/more-videos --searchAutoSpeed 4.5

# Check which entries in a playlist have tags
pyVid --loadPlayList favourites.txt --searchAutoSpeed
```

#### `--dryRun`

Add `--dryRun` to `--addAutoSpeed` or `--delAutoSpeed` to see exactly what would change without
touching any files. `--dryRun` can only be used with those two options. `--searchAutoSpeed` never
changes anything, so it has no dry-run mode.

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

## Sub-Playlists (Model Filter)

With a large master playlist (hundreds or thousands of videos), a sub-playlist lets you
stay with whatever is playing right now: one key press narrows playback to every video in
the master playlist that shares the current video's **model name**, then returns you to
the master playlist when you are done.

### Model name

The model name is the part of the filename **before the first `-`**, with surrounding
spaces trimmed. Matching is exact and case-sensitive. A filename with no `-` uses its
whole name (without extension).

| Filename                            | Model name           |
|-------------------------------------|----------------------|
| `Eugenia-Slideshow-103_Kenburns.mp4` | `Eugenia`            |
| `Nikki C-Slideshow-Japan Vacation.mp4` | `Nikki C`            |
| `Barbara B Princess-034.mp4`        | `Barbara B Princess` |

### Using it

| Control | Action |
|---|---|
| `F` key / IR `FILTER` / HUD filter button | Sub-playlist **on**: collect every master entry with the same model name, sort them, and start playing the first one |
| `F` key / IR `FILTER` / HUD filter button (again) | Sub-playlist **off**: return to the master playlist at the next video after where you left it, skipping the sub-playlist's model |
| `J` | Shuffle / sort the sub-playlist (independent of the master playlist's shuffle state) |
| `,` (Comma) | Print the sub-playlist to the console |
| `.` (Period) | Save the sub-playlist to `~/+Playlists/<Model>-Playlist-<count>.txt` |

While a sub-playlist is active, the HUD shows **Sub-Video N of T** instead of **Video N of T**.

### When the sub-playlist ends

| Options | Result |
|---|---|
| `--loop` | The sub-playlist starts over |
| `--loop --noFilterLoop` | Return to the master playlist (which keeps looping) |
| no `--loop` | Return to the master playlist — a sub-playlist never ends the program |

> If the current model has only one video, `F` turns on **Repeat Video** instead.
> If every video in the master playlist has the same model name, there is nothing to filter and `F` does nothing.

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
| `+` or `=` | Increase playback speed (steps: 0.5 → 1.0 → 1.5 → … → 10.0) |
| `-` | Decrease playback speed |

### Audio

| Key | Action |
|---|---|
| `↑` (Up Arrow) | Volume up (+5%) |
| `↓` (Down Arrow) | Volume down (−5%) |
| `M` | Mute / Unmute |

### Display & OSD

| Key | Action                                                       |
|---|--------------------------------------------------------------|
| `O` | Cycle position OSD: Off → position → position/duration → Off |
| `T` | ~~Toggle video title display~~                               |
| `G` | ~~Toggle greyscale~~                                         |
| `H` | Show help overlay (cycles: keyboard → IR remote → Off)       |

### Playlist

| Key | Action |
|---|---|
| `J` | Toggle shuffle (randomize / sort the active playlist) |
| `F` | [Sub-playlist](#sub-playlists-model-filter) of the current model On / Off |
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
| `PLAY_PAUSE` | Play / Pause |
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
| `FILTER` | [Sub-playlist](#sub-playlists-model-filter) of the current model On / Off |
| `SHUFFLE` | Randomize (shuffle) playlist |
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
pyVid2-qt  version 0.95
────────────────────────────────────────────────────────
  Decoder:  NVDEC       nvh265dec                       [disabled by --decoder vaapi]
            VA-API      vah265dec                       [active]
            FFmpeg      avdec_h265                      [fallback]
────────────────────────────────────────────────────────
```

Each decoder is shown as `[active]`, `[available]`, `[fallback]` (software), `[not available]`
(not installed), `[disabled by --decoder …]`, or, with `--decoder vaapi --rgbFallback nvdec`,
`[RGB-coded files only — --rgbFallback nvdec]`.

| `--decoder` | Effect |
|---|---|
| `auto` (default) | GStreamer's own ranking decides. On systems with both NVIDIA and Intel/AMD GPUs this is usually NVDEC. |
| `nvdec` | Only NVIDIA NVDEC decoders are eligible (software decoding remains as fallback). |
| `vaapi` | Only VA-API decoders on non-NVIDIA GPUs are eligible (software decoding remains as fallback). VA-API devices backed by `libva-nvidia-driver` are excluded. When an Intel GPU is present and `LIBVA_DRIVER_NAME` is unset, it is set to `iHD`. The NVIDIA GPU is not used at all: no CUDA context, no VRAM. |
| `software` | All hardware decoders are disabled; FFmpeg (`avdec_*`) decodes on the CPU. |

The selection applies to every codec (HEVC, H.264, AV1, VP9, ...), not just HEVC.

**RGB-coded video and VA-API:** GStreamer's VA-API decoders mis-render video that is coded
directly in RGB rather than YUV (for example HEVC Range Extensions with pixel format `gbrp`,
colour matrix `gbr`, as some slideshow and Ken Burns tools produce). Saturated colours come out
blown out or washed out while greys look correct. pyVid2-qt checks each file before playback.
For RGB-coded files only, VA-API is skipped and another decoder is used. Normal YUV files (4:2:0
and 4:4:4) are unaffected and still use VA-API.

| Options | RGB-coded files decoded by | Console tag on that file's line |
|---|---|---|
| `--decoder vaapi` (`--rgbFallback software`, the default) | software (CPU); the NVIDIA GPU stays idle | `[RGB-coded: VA-API skipped (wrong colours) → software]` |
| `--decoder vaapi --rgbFallback nvdec` | NVDEC, for those files only; normal files stay on VA-API | `[RGB-coded: VA-API skipped (wrong colours) → NVDEC]` |
| `--decoder auto` | NVDEC if present, otherwise software | none with NVDEC (it would have decoded the file anyway); the software tag otherwise |

With `--rgbFallback nvdec`, the NVIDIA GPU's VRAM is used only while an RGB-coded file plays and
is released when the next normal file starts. The NVIDIA driver library stays loaded (and its
device files open) until pyVid2-qt exits, but holds no VRAM. `--rgbFallback` has no effect
without `--decoder vaapi`; pyVid2-qt says so at startup.

Vulkan video decoders are not supported. GStreamer registers them at rank NONE, meaning they are
not ready for automatic use, and pyVid2-qt leaves them disabled.

`--decoder` only takes effect on Qt's GStreamer backend (see
[Arch Linux packages](#arch-linux-packages)). If that backend is not available, pyVid2-qt prints a
warning at startup and Qt chooses the decoder itself.

---

## License

GNU Lesser General Public License v3.0 — see [LICENSE](LICENSE).
