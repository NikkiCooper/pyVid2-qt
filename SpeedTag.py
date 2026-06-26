#  SpeedTag.py Copyright (c) 2026 Nikki Cooper
#
#  This program and the accompanying materials are made available under the
#  terms of the GNU Lesser General Public License, version 3.0 which is available at
#  https://www.gnu.org/licenses/gpl-3.0.html#license-text
#
"""
SpeedTag — ExifTool-based auto_speed tag management for pyVid2-qt.

Manages a custom XMP tag (auto_speed) that instructs pyVid2-qt to override
the default playback speed for specific video files when --autoSpeed is active.

Tag storage:
  key:   auto_speed   (XMP, written via pyVid2.ExifTool_config)
  value: decimal string, e.g. "1", "2", "4.5"

Display label convention (human-facing):
  auto_speed_1  auto_speed_2  auto_speed_4.5  etc.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

from Bcolors import Bcolors

bc = Bcolors()

# ── Constants ────────────────────────────────────────────────────────────────

TAG_KEY       = "auto_speed"
TAG_ET_KEY    = "XMP-pyvid2:AutoSpeed"    # ExifTool argument form (namespace-qualified)
VALID_SPEEDS  = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
WARN_THRESHOLD = 20          # files at or above this count require 'Yes' for --addAutoSpeed
BATCH_SIZE     = 400         # max files per ExifTool invocation

_MODULE_DIR     = os.path.dirname(os.path.abspath(__file__))
EXIFTOOL_CONFIG = os.path.join(_MODULE_DIR, "pyVid2.ExifTool_config")

# ── Helpers: tag label / display ─────────────────────────────────────────────

def tag_label(speed: float) -> str:
    """Return display label: auto_speed_1, auto_speed_4.5, auto_speed_0.5 …"""
    val = int(speed) if speed == int(speed) else speed
    return f"{TAG_KEY}_{val}"


def speed_display(speed: float) -> str:
    """Return short speed string: '1x', '4.5x' …"""
    val = int(speed) if speed == int(speed) else speed
    return f"{val}x"


# ── ExifTool wrappers ─────────────────────────────────────────────────────────

def _check_exiftool() -> None:
    """Abort with a clear message if exiftool is not in PATH."""
    if not shutil.which("exiftool"):
        print(f"\n{bc.BOLD}{bc.Red_f}Error:{bc.RESET}{bc.Light_Yellow_f} "
              f"'exiftool' was not found in PATH.\n"
              f"  Install it with:  sudo pacman -S perl-image-exiftool{bc.RESET}\n")
        sys.exit(1)


def _et_cmd(*args) -> List[str]:
    """Build a base exiftool command with our custom config."""
    return ["exiftool", "-config", EXIFTOOL_CONFIG] + list(args)


def _run(*args) -> subprocess.CompletedProcess:
    return subprocess.run(_et_cmd(*args), capture_output=True, text=True)


def _parse_json_entry(entry: dict) -> Optional[float]:
    """
    Extract auto_speed float from a single ExifTool JSON record.
    ExifTool capitalises tag names in JSON: auto_speed → AutoSpeed.
    Check both the capitalised form and the raw form for robustness.
    """
    for key in ("XMP-pyvid2:AutoSpeed", "AutoSpeed", TAG_KEY, f"XMP:{TAG_KEY}"):
        raw = entry.get(key)
        if raw is not None:
            if isinstance(raw, list):
                raw = raw[-1]
            try:
                return float(raw)
            except (ValueError, TypeError):
                pass
    return None


# ── Public I/O ────────────────────────────────────────────────────────────────

def read_tag(filepath: str) -> Optional[float]:
    """
    Read the auto_speed tag from a single file.
    Returns the speed as float, or None if absent.
    Suitable for fast per-video calls during playback.
    """
    result = _run("-fast", "-j", f"-{TAG_ET_KEY}", filepath)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
        if data:
            return _parse_json_entry(data[0])
    except (json.JSONDecodeError, IndexError):
        pass
    return None


def read_tags_batch(filepaths: List[str]) -> Dict[str, Optional[float]]:
    """
    Read auto_speed tags from many files efficiently (chunked ExifTool calls).
    Returns {filepath: speed_or_None}.
    """
    results: Dict[str, Optional[float]] = {fp: None for fp in filepaths}
    if not filepaths:
        return results

    for i in range(0, len(filepaths), BATCH_SIZE):
        chunk = filepaths[i : i + BATCH_SIZE]
        result = _run("-j", f"-{TAG_ET_KEY}", *chunk)
        if result.returncode != 0 or not result.stdout.strip():
            continue
        try:
            data = json.loads(result.stdout)
            for entry in data:
                src = entry.get("SourceFile")
                if src in results:
                    results[src] = _parse_json_entry(entry)
        except (json.JSONDecodeError, KeyError):
            continue
    return results


def write_tag(filepath: str, speed: float) -> Tuple[bool, str]:
    """Write auto_speed tag. Returns (success, message)."""
    result = _run("-overwrite_original", f"-{TAG_ET_KEY}={speed}", filepath)
    if result.returncode != 0:
        return False, result.stderr.strip()
    msg = result.stdout.strip()
    # ExifTool exits 0 even when nothing was written ("0 image files updated").
    # Treat that as failure so cmd_add reports it correctly.
    ok = "1 image file" in msg or "image files updated" in msg
    return ok, msg


def delete_tag(filepath: str) -> Tuple[bool, str]:
    """Delete auto_speed tag. Returns (success, message)."""
    result = _run("-overwrite_original", f"-{TAG_ET_KEY}=", filepath)
    if result.returncode != 0:
        return False, result.stderr.strip()
    msg = result.stdout.strip()
    ok = "1 image file" in msg or "image files updated" in msg
    return ok, msg


# ── Console decoration ────────────────────────────────────────────────────────

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def _visual_len(s: str) -> int:
    """Length of string ignoring ANSI escape codes."""
    return len(_ANSI_RE.sub('', s))


def _pipe_to_pager(text: str) -> None:
    """
    Pipe colored text through  less -R -F -X.
    -R  passes ANSI color codes through.
    -F  exits automatically if the content fits on one screen.
    -X  does not clear the screen on exit (output stays in scrollback).
    Falls back to plain print if less is unavailable or the pipe breaks.
    """
    proc = subprocess.Popen(["less", "-R", "-F", "-X"], stdin=subprocess.PIPE)
    try:
        proc.stdin.write(text.encode())
        proc.stdin.close()
        proc.wait()
    except (BrokenPipeError, OSError):
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")


def _box(lines: List[str], color: str, width: int = 56) -> None:
    """Print lines inside a Unicode border box in the given color."""
    inner_w = max((len(ln) for ln in lines), default=0)
    inner_w = max(inner_w, width)
    pad = inner_w + 2
    print(color + bc.BOLD + f"╔{'═' * pad}╗" + bc.RESET)
    for ln in lines:
        padded = ln.ljust(inner_w)
        print(color + bc.BOLD + f"║ {padded} ║" + bc.RESET)
    print(color + bc.BOLD + f"╚{'═' * pad}╝" + bc.RESET)


def _section(title: str) -> None:
    """Print a section header bar (ANSI-aware padding)."""
    w   = 62
    pad = w - 2 - _visual_len(title)
    # Re-apply box color after the title, which may contain a RESET sequence.
    box = bc.BOLD + bc.Light_Blue_f
    padded = title + ' ' * max(0, pad)
    print(f"\n{box}┌{'─' * w}┐{bc.RESET}\n"
          f"{box}│  {padded}{box}│{bc.RESET}\n"
          f"{box}└{'─' * w}┘{bc.RESET}\n")


def _multi_col_str(items: List[str], color: str = "", col_w: int = 0) -> str:
    """
    Return items as a multi-column string (no grouping).
    Items must be plain strings (no embedded ANSI codes).
    col_w: fixed column width; 0 = auto (max item length + 2).
    """
    if not items:
        return ""
    term_w = shutil.get_terminal_size((160, 50)).columns
    if not col_w:
        col_w = max(len(s) for s in items) + 2
    cols  = max(1, (term_w - 4) // col_w)
    lines: List[str] = []
    row:   List[str] = []
    for i, item in enumerate(items):
        cell = f"{color}{item:<{col_w}}{bc.RESET}" if color else f"{item:<{col_w}}"
        row.append(cell)
        if len(row) == cols or i == len(items) - 1:
            lines.append("  " + "".join(row).rstrip())
            row = []
    return "\n".join(lines)


def _indexed_col_str(items: List[str], color: str = "",
                     index_color: str = "") -> str:
    """
    Return items grouped by first letter, each group preceded by a bold
    letter index header.  Items are sorted alphabetically (case-insensitive).
    Items must be plain strings (no embedded ANSI codes).
    """
    if not items:
        return ""
    if not index_color:
        index_color = bc.BOLD + bc.Yellow_f

    items_sorted = sorted(items, key=str.casefold)
    # Use a consistent column width across all groups so columns line up.
    col_w = max(len(s) for s in items_sorted) + 2

    # Group by uppercase first character
    groups: Dict[str, List[str]] = {}
    for item in items_sorted:
        key = item[0].upper() if item else '?'
        groups.setdefault(key, []).append(item)

    blocks: List[str] = []
    for letter in sorted(groups):
        group_items = groups[letter]
        header = f"  {index_color}{letter}{bc.RESET}"
        body   = _multi_col_str(group_items, color=color, col_w=col_w)
        blocks.append(header + "\n" + body)

    return "\n\n".join(blocks)


def _print_report(action: str, tag: str, ok: List[str], fail: List[str]) -> None:
    """Print a final results report after add/delete."""
    total = len(ok) + len(fail)
    _section(f"Results  ─  {action}  {tag}")

    if ok:
        print(f"  {bc.BOLD}{bc.Green_f}✓  {len(ok):,} of {total:,} file(s) updated successfully.{bc.RESET}")
    if fail:
        print(f"  {bc.BOLD}{bc.Red_f}✗  {len(fail):,} file(s) failed:{bc.RESET}")
        for fp in fail:
            print(f"      {bc.Red_f}{os.path.basename(fp)}{bc.RESET}")

    if ok:
        print(f"\n{bc.Light_Yellow_f}  Files updated:{bc.RESET}")
        _pipe_to_pager(_indexed_col_str([os.path.basename(fp) for fp in ok],
                                        color=bc.Green_f) + "\n\n")
    else:
        print()


# ── Tag tool commands ─────────────────────────────────────────────────────────

def cmd_add(files: List[str], speed: float, dry_run: bool = False) -> None:
    """
    Add (or replace) the auto_speed tag on every file in files.

    Behaviour:
    - Batch-reads existing tags first and reports what will change.
    - Files with the same tag are overwritten silently.
    - Files with a different tag are reported (old → new) before proceeding.
    - For >= WARN_THRESHOLD files: requires the user to type 'Yes' exactly.
    - For < WARN_THRESHOLD files: proceeds without prompting.
    """
    if not files:
        print(f"{bc.Red_f}No files to process.{bc.RESET}")
        return

    new_val = int(speed) if speed == int(speed) else speed
    mode    = (f"{bc.Cyan_f}DRY RUN{bc.RESET}" if dry_run
               else f"{bc.Green_f}LIVE{bc.RESET}")
    _section(f"Add  auto_speed = {new_val}  ─  {mode}")

    # ── Scan existing tags ────────────────────────────────────────────────────
    print(f"{bc.Light_Yellow_f}  Scanning {len(files):,} file(s) for existing tags …{bc.RESET}")
    existing = read_tags_batch(files)

    same_tag      = [(fp, v) for fp, v in existing.items() if v == speed]
    different_tag = [(fp, v) for fp, v in existing.items() if v is not None and v != speed]
    untagged      = [fp for fp, v in existing.items() if v is None]

    print(f"\n  {bc.Green_f}Untagged         {len(untagged):>6,}{bc.RESET}")
    print(f"  {bc.Light_Yellow_f}Same tag already {len(same_tag):>6,}  (will overwrite){bc.RESET}")
    print(f"  {bc.Magenta_f}Different tag    {len(different_tag):>6,}  (will replace){bc.RESET}")
    print(f"  {bc.BOLD}{bc.White_f}Total to tag     {len(files):>6,}{bc.RESET}")

    # ── Build pager buffer ────────────────────────────────────────────────────
    buf: List[str] = []

    if different_tag:
        buf.append(f"\n{bc.BOLD}{bc.Magenta_f}  Files with a different auto_speed tag"
                   f" (will be replaced):{bc.RESET}\n")
        # Group by first letter of filename for easy scanning
        diff_sorted = sorted(different_tag,
                             key=lambda t: os.path.basename(t[0]).casefold())
        diff_groups: Dict[str, list] = {}
        for fp, old_v in diff_sorted:
            key = os.path.basename(fp)[0].upper()
            diff_groups.setdefault(key, []).append((fp, old_v))
        for letter in sorted(diff_groups):
            buf.append(f"\n  {bc.BOLD}{bc.Yellow_f}{letter}{bc.RESET}\n")
            for fp, old_v in diff_groups[letter]:
                old_val = int(old_v) if old_v == int(old_v) else old_v
                buf.append(f"    {bc.Red_f}auto_speed = {old_val}{bc.RESET}"
                           f"  {bc.Dark_Gray_f}→{bc.RESET}"
                           f"  {bc.Green_f}auto_speed = {new_val}{bc.RESET}"
                           f"  {bc.White_f}{os.path.basename(fp)}{bc.RESET}\n")

    if dry_run:
        # In dry-run mode show ALL groups so the user sees exactly what would happen.
        if untagged:
            buf.append(f"\n{bc.BOLD}{bc.Green_f}  Untagged — would be tagged for the"
                       f" first time:{bc.RESET}\n")
            buf.append(_indexed_col_str([os.path.basename(fp) for fp in untagged],
                                        color=bc.Green_f) + "\n")

        if same_tag:
            buf.append(f"\n{bc.BOLD}{bc.Light_Yellow_f}  Already auto_speed = {new_val}"
                       f" — would be overwritten (no data change):{bc.RESET}\n")
            buf.append(_indexed_col_str([os.path.basename(fp) for fp, _ in same_tag],
                                        color=bc.Light_Yellow_f) + "\n")

    if buf:
        _pipe_to_pager("".join(buf))

    if dry_run:
        print(f"\n{bc.Cyan_f}  [DRY RUN]  Would write  {bc.BOLD}auto_speed = {new_val}{bc.RESET}"
              f"{bc.Cyan_f}  to {len(files):,} file(s).  No changes made.{bc.RESET}\n")
        return

    # ── Confirmation ──────────────────────────────────────────────────────────
    if len(files) >= WARN_THRESHOLD:
        print()
        _box([
            f"  You are about to add  {tag_label(speed)}",
            f"  to  {len(files):,}  video file(s).",
            "",
            "  Type  Yes  to proceed (case-sensitive),",
            "  or press Enter / anything else to cancel.",
        ], bc.Red_f)
        try:
            answer = input(f"\n{bc.BOLD}{bc.Red_f}  Confirm > {bc.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            answer = ""
        if answer != "Yes":
            print(f"\n{bc.Yellow_f}  Operation cancelled.{bc.RESET}\n")
            return
    # < WARN_THRESHOLD: proceed without prompting

    # ── Write ─────────────────────────────────────────────────────────────────
    print(f"\n{bc.Light_Yellow_f}  Writing  auto_speed = {new_val} …{bc.RESET}")
    ok_files:   List[str] = []
    fail_files: List[str] = []
    for fp in files:
        success, msg = write_tag(fp, speed)
        (ok_files if success else fail_files).append(fp)
        if not success:
            print(f"  {bc.Red_f}FAIL{bc.RESET}  {os.path.basename(fp)}  {bc.Dark_Gray_f}{msg}{bc.RESET}")

    _print_report("Add", f"auto_speed = {new_val}", ok_files, fail_files)


def cmd_del(files: List[str], dry_run: bool = False) -> None:
    """
    Delete all auto_speed tags from files that have one.
    Always prompts with a bold-red warning box regardless of file count.
    """
    if not files:
        print(f"{bc.Red_f}No files to process.{bc.RESET}")
        return

    mode = f"{bc.Cyan_f}DRY RUN{bc.RESET}" if dry_run else f"{bc.Green_f}LIVE{bc.RESET}"
    _section(f"Delete auto_speed tags  ─  {mode}")

    print(f"{bc.Light_Yellow_f}  Scanning {len(files):,} file(s) for auto_speed tags …{bc.RESET}")
    existing = read_tags_batch(files)
    tagged = [(fp, v) for fp, v in existing.items() if v is not None]

    if not tagged:
        print(f"\n{bc.Green_f}  No auto_speed tags found.  Nothing to delete.{bc.RESET}\n")
        return

    print(f"\n{bc.Yellow_f}  Found {len(tagged):,} file(s) with auto_speed tags:{bc.RESET}\n")

    if len(tagged) <= 40:
        for fp, val in sorted(tagged, key=lambda t: os.path.basename(t[0]).casefold()):
            print(f"    {bc.Magenta_f}{tag_label(val):<20}{bc.RESET}"
                  f"  {bc.White_f}{os.path.basename(fp)}{bc.RESET}")
    else:
        # Group by speed for a compact overview then columnar file list
        by_speed: Dict[float, int] = {}
        for _, v in tagged:
            by_speed[v] = by_speed.get(v, 0) + 1
        for spd in sorted(by_speed):
            print(f"    {bc.Magenta_f}{tag_label(spd):<20}{bc.RESET}"
                  f"  {bc.Light_Yellow_f}{by_speed[spd]:,} file(s){bc.RESET}")
        print()
        _pipe_to_pager(
            _indexed_col_str([os.path.basename(fp) for fp, _ in tagged],
                             color=bc.White_f) + "\n\n"
        )

    if dry_run:
        print(f"\n{bc.Cyan_f}  [DRY RUN]  Would delete tags from "
              f"{bc.BOLD}{len(tagged):,}{bc.RESET}"
              f"{bc.Cyan_f} file(s).  No changes made.{bc.RESET}\n")
        return

    # ── Always warn for delete ─────────────────────────────────────────────────
    print()
    _box([
        f"  ⚠  WARNING  ⚠",
        "",
        f"  You are about to PERMANENTLY DELETE",
        f"  all auto_speed tags from  {len(tagged):,}  file(s).",
        "",
        "  Type  Yes  to proceed (case-sensitive),",
        "  or press Enter / anything else to cancel.",
    ], bc.Red_f)
    try:
        answer = input(f"\n{bc.BOLD}{bc.Red_f}  Confirm > {bc.RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        answer = ""
    if answer != "Yes":
        print(f"\n{bc.Yellow_f}  Operation cancelled.{bc.RESET}\n")
        return

    # ── Delete ────────────────────────────────────────────────────────────────
    print(f"\n{bc.Light_Yellow_f}  Deleting tags …{bc.RESET}")
    ok_files:   List[str] = []
    fail_files: List[str] = []
    for fp, _ in tagged:
        success, _ = delete_tag(fp)
        (ok_files if success else fail_files).append(fp)

    _print_report("Delete", TAG_KEY, ok_files, fail_files)


def cmd_search(files: List[str], speed_filter: Optional[float] = None) -> None:
    """
    Search files for auto_speed tags and print a colorful grouped report.

    speed_filter: if given, only show files tagged with that exact speed.
    """
    if not files:
        print(f"{bc.Red_f}No files to process.{bc.RESET}")
        return

    filter_label = speed_display(speed_filter) if speed_filter is not None else "all speeds"
    _section(f"Search auto_speed tags  ─  filter: {filter_label}")

    print(f"{bc.Light_Yellow_f}  Scanning {len(files):,} file(s) …{bc.RESET}")
    existing = read_tags_batch(files)

    tagged = [(fp, v) for fp, v in existing.items() if v is not None]
    if speed_filter is not None:
        tagged = [(fp, v) for fp, v in tagged if v == speed_filter]

    if not tagged:
        msg = (f"No files tagged with {tag_label(speed_filter)}"
               if speed_filter is not None
               else "No auto_speed tags found")
        print(f"\n{bc.Green_f}  {msg}.{bc.RESET}\n")
        return

    # ── Group by speed ─────────────────────────────────────────────────────────
    by_speed: Dict[float, List[str]] = {}
    for fp, v in tagged:
        by_speed.setdefault(v, []).append(fp)

    # ── Build output buffer ───────────────────────────────────────────────────
    buf: List[str] = []

    buf.append(f"\n{bc.BOLD}{bc.Green_f}  Found {len(tagged):,} file(s)"
               f" with auto_speed tags:{bc.RESET}\n")

    for spd in sorted(by_speed):
        fps  = by_speed[spd]
        cnt  = len(fps)
        plural = 's' if cnt != 1 else ''
        buf.append(f"\n  {bc.BOLD}{bc.Blue_f}{tag_label(spd)}{bc.RESET}"
                   f"  {bc.Light_Yellow_f}({cnt:,} file{plural}){bc.RESET}\n")
        buf.append(_indexed_col_str([os.path.basename(fp) for fp in fps],
                                   color=bc.White_f))
        buf.append("\n")

    # ── Summary bar chart ─────────────────────────────────────────────────────
    if len(by_speed) > 1 or speed_filter is None:
        term_w    = shutil.get_terminal_size((160, 50)).columns
        bar_area  = max(20, min(40, term_w - 42))
        max_count = max(len(v) for v in by_speed.values())
        buf.append(f"\n{bc.BOLD}{bc.Light_Blue_f}  Summary:{bc.RESET}\n")
        for spd in sorted(by_speed):
            count   = len(by_speed[spd])
            bar_len = max(1, round(count * bar_area / max_count))
            bar     = "█" * bar_len
            buf.append(f"    {bc.Magenta_f}{tag_label(spd):<20}{bc.RESET}"
                       f"{bc.Green_f}{bar:<{bar_area + 2}}{bc.RESET}"
                       f"{bc.Light_Yellow_f}{count:>6,}{bc.RESET}\n")
        buf.append("\n")

    _pipe_to_pager("".join(buf))


# ── Entry point ───────────────────────────────────────────────────────────────

def run_tag_tool(opts) -> None:
    """
    Dispatch to the appropriate tag command based on CLI opts.
    Called from main.py before Qt initialises; exits the process when done.
    """
    _check_exiftool()

    # Build file list (FindVideos handles all source types)
    from FindVideos import FindVideos
    print(f"{bc.Light_Yellow_f}  Building file list …{bc.RESET}")
    fv = FindVideos(opts)

    if fv.numVideos == 0:
        print(f"{bc.Yellow_f}  No video files found from the specified sources.{bc.RESET}\n")
        return

    files = fv.videoList

    dry_run = getattr(opts, "dryRun", False)

    if opts.addAutoSpeed is not None:
        cmd_add(files, opts.addAutoSpeed, dry_run=dry_run)

    elif opts.delAutoSpeed:
        cmd_del(files, dry_run=dry_run)

    elif opts.searchAutoSpeed is not None:
        # "any" → search all speeds; float → filter to specific speed
        speed_filter = opts.searchAutoSpeed if isinstance(opts.searchAutoSpeed, float) else None
        cmd_search(files, speed_filter)
