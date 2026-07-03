#  cmdLineOpts.py Copyright (c) 2025, 2026 Nikki Cooper
#
#  This program and the accompanying materials are made available under the
#  terms of the GNU Lesser General Public License, version 3.0 which is available at
#  https://www.gnu.org/licenses/gpl-3.0.html#license-text
#
import argparse
import os
import re as _re

from Bcolors import Bcolors
import cmdLineHelp as chl

bc = Bcolors()


def cmdLineOptions():
    parser = argparse.ArgumentParser(
        description=f"{bc.BOLD}{bc.Blue_f}pyVid2-qt - Hardware-accelerated Video Player{bc.RESET}",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # Source group — one or more required, any combination is allowed
    source = parser.add_argument_group(chl.group["source_group"])
    source.add_argument("--Paths",        nargs="+", type=validate_user_dirs,    default=None, help=chl.help["Paths"])
    source.add_argument("--Files",        nargs="+", type=validate_user_files,   default=None, help=chl.help["Files"])
    source.add_argument("--loadPlayList", nargs="+", type=validate_playList,     default=None, help=chl.help["loadPlayList"])
    source.add_argument("--Glob",         nargs="+", type=validate_glob_pattern, default=None, help=chl.help["Glob"])

    # Video Playback Options
    video_group = parser.add_argument_group(chl.group["video_group"])
    video_group.add_argument("--loop",      action="store_true",                         help=chl.help["loop"])
    video_group.add_argument("--decoder",   choices=['auto','nvdec','vulkan','vaapi','software'],
                                            default='auto', metavar='DECODER',           help=chl.help["decoder"])
    video_group.add_argument("--shuffle",   action="store_true",                         help=chl.help["shuffle"])
    video_group.add_argument("--loopDelay", type=int,   default=1,                       help=chl.help["loopDelay"])
    video_group.add_argument("--playSpeed",       type=restricted_float_or_int, default=2.0,  help=chl.help["playSpeed"])
    video_group.add_argument("--enableOSDcurpos", action="store_true",                       help=chl.help["enableOSDcurpos"])
    video_group.add_argument("--autoSpeed",       action="store_true",                       help=chl.help["autoSpeed"])

    # Speed Tag Tools (mutually exclusive; program exits after running)
    tag_group = parser.add_argument_group(chl.group["tag_group"])
    tag_ops = tag_group.add_mutually_exclusive_group()
    tag_ops.add_argument("--addAutoSpeed",    type=validate_speed_tag, metavar="SPEED",
                         default=None,        help=chl.help["addAutoSpeed"])
    tag_ops.add_argument("--delAutoSpeed",    action="store_true",
                         default=False,       help=chl.help["delAutoSpeed"])
    tag_ops.add_argument("--searchAutoSpeed", nargs="?", const="any", default=None,
                         metavar="SPEED",     help=chl.help["searchAutoSpeed"])
    tag_group.add_argument("--dryRun",        action="store_true",
                           default=False,     help=chl.help["dryRun"])

    # Audio Options
    audio_group = parser.add_argument_group(chl.group["audio_group"])
    audio_group.add_argument("--mute",   action="store_true",                                help=chl.help["mute"])
    audio_group.add_argument("--volume", type=validate_volume, default=0, metavar="PERCENT", help=chl.help["volume"])

    # Screenshot Options
    screenshot_group = parser.add_argument_group(chl.group["screenshot_group"])
    screenshot_group.add_argument("--sshotDir", type=str,          default="~/pyVid2-qt-Shots", help=chl.help["sshotDir"])
    screenshot_group.add_argument("--useJPG",   action="store_true",                            help=chl.help["useJPG"])

    # System Options
    system_group = parser.add_argument_group(chl.group["system_group"])
    system_group.add_argument("--verbose",    action="store_true",                       help=chl.help["verbose"])
    system_group.add_argument("--display",    type=str,                                  help=chl.help["display"])
    system_group.add_argument("--udp-port", action="store", type=int, dest="udpPort", default=5005, help=chl.help["udp_port"])
    system_group.add_argument("--ir-keymap",action="store", type=str, dest="irKeymap", default=None, help=chl.help["ir_keymap"])
    system_group.add_argument("--disable-IR", action="store_true", dest="disable_IR",   help=chl.help["disable_IR"])
    system_group.add_argument("--metadata",   action="store_true",                       help=chl.help["metadata"])

    # File Options
    file_group = parser.add_argument_group(chl.group["file_group"])
    file_group.add_argument("--noIgnore",  action="store_true", help=chl.help["noIgnore"])
    file_group.add_argument("--noRecurse", action="store_true", help=chl.help["noRecurse"])
    file_group.add_argument("--printIgnoreList", action="store_true", help=chl.help["printIgnoreList"])

    args = parser.parse_args()

    # ── Tag tool validation ────────────────────────────────────────────────────
    _is_tag_op = (args.addAutoSpeed is not None
                  or args.delAutoSpeed
                  or args.searchAutoSpeed is not None)

    if args.dryRun and not (args.addAutoSpeed is not None or args.delAutoSpeed):
        parser.error("--dryRun requires --addAutoSpeed or --delAutoSpeed")

    if args.addAutoSpeed is not None or args.delAutoSpeed:
        # --loadPlayList is not safe for write operations (may be stale/remote paths)
        if args.loadPlayList is not None:
            parser.error("--addAutoSpeed and --delAutoSpeed cannot be combined with --loadPlayList")

    # Validate --searchAutoSpeed speed argument when a specific value is given.
    # "any" (the nargs="?" const) means search all speeds — left as-is here so
    # main.py's `is not None` check can detect that the flag was supplied at all.
    if args.searchAutoSpeed is not None and args.searchAutoSpeed != "any":
        try:
            sv = float(args.searchAutoSpeed)
        except ValueError:
            parser.error(f"--searchAutoSpeed: '{args.searchAutoSpeed}' is not a valid speed value")
        if sv not in {round(i * 0.5, 1) for i in range(1, 13)}:
            parser.error(f"--searchAutoSpeed: {sv} is not a valid speed "
                         f"(must be 0.5–6.0 in 0.5 increments)")
        args.searchAutoSpeed = sv
    # "any" remains as-is; run_tag_tool converts it to None (search all speeds)

    # ── Source requirement ─────────────────────────────────────────────────────
    if not any([args.Paths, args.Files, args.loadPlayList, args.Glob]):
        parser.error(
            f"{bc.Red_f}At least one of --Paths, --Files, --loadPlayList, or --Glob is required.{bc.RESET}")

    # Convenience flags (mirrors pyVid2 pattern — FindVideos.py relies on these)
    args.loadPlayListFlag = args.loadPlayList is not None
    args.loadFilesFlag    = args.Files        is not None
    args.disableGIF       = False

    return args


# ── Validators (ported directly from pyVid2/cmdLineOpts.py) ──────────────────

def validate_playList(playlist):
    """Validate playlist path: absolute, CWD, or PLAYLIST_HOME."""
    if os.path.isabs(playlist):
        if os.path.isfile(os.path.expanduser(playlist)):
            return os.path.expanduser(playlist)
        raise argparse.ArgumentTypeError(
            f"Error: {bc.Red_f}'{playlist}'{bc.Light_Yellow_f} was not found.{bc.RESET}")

    cwd_path = os.path.join(os.getcwd(), playlist)
    if os.path.isfile(cwd_path):
        return cwd_path

    if "PLAYLIST_HOME" in os.environ:
        home_path = os.path.join(os.environ["PLAYLIST_HOME"], playlist)
        if os.path.isfile(home_path):
            return home_path

    raise argparse.ArgumentTypeError(
        f"Error: {bc.Red_f}'{playlist}'{bc.Light_Yellow_f} was not found in current directory or PLAYLIST_HOME.{bc.RESET}")


def validate_user_dirs(path):
    """Check that a user-supplied path is a valid directory."""
    if path is None:
        raise argparse.ArgumentTypeError(
            f"Error: {bc.Light_Yellow_f}At least one valid directory must be supplied.{bc.RESET}")
    if not os.path.isdir(os.path.expanduser(path)):
        raise argparse.ArgumentTypeError(
            f"Error: {bc.Red_f}'{path}'{bc.Light_Yellow_f} is not a valid directory.{bc.RESET}")
    return os.path.expanduser(path)


def validate_user_files(FilePath):
    """Check that a user-supplied file path is valid."""
    if FilePath is None:
        raise argparse.ArgumentTypeError(
            f"Error: {bc.Light_Yellow_f}At least one valid file must be supplied.{bc.RESET}")
    expanded = os.path.expanduser(FilePath)
    if not os.path.isfile(expanded):
        raise argparse.ArgumentTypeError(
            f"Error: {bc.Red_f}'{FilePath}'{bc.Light_Yellow_f} is not a valid file.{bc.RESET}")
    return expanded


def validate_glob_pattern(pattern):
    """
    Validate that the base directory portion of a glob/range pattern exists.

    If the pattern contains no wildcard or range tokens (e.g. the shell already
    expanded it into literal filenames) it is accepted as-is — buildGlobPlayList
    handles literal paths via os.path.isfile() at runtime.

    When wildcards/range tokens ARE present the base directory (the longest
    leading path before the first special component) must exist.
    """
    has_special = (any(c in pattern for c in ('*', '?', '[', '{'))
                   or _re.search(r'\d+-\d*}', pattern))

    if not has_special:
        # Literal path — existence is checked at runtime, not here.
        return pattern

    parts = pattern.split(os.sep)
    base_parts = []
    for part in parts:
        if any(c in part for c in ('*', '?', '[', '{')) or _re.search(r'\d+-\d*}', part):
            break
        base_parts.append(part)

    base = os.sep.join(base_parts) or '.'
    base = os.path.expanduser(base)

    if not os.path.isdir(base):
        raise argparse.ArgumentTypeError(
            f"Error: {bc.Red_f}'{base}'{bc.Light_Yellow_f} is not a valid directory "
            f"(base of pattern '{pattern}').{bc.RESET}")
    return pattern


def validate_volume(x):
    """Validate --volume: integer 0–100."""
    try:
        val = int(x)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{bc.Red_f}'{x}'{bc.Light_Yellow_f} is not a valid integer{bc.RESET}")
    if not 0 <= val <= 100:
        raise argparse.ArgumentTypeError(
            f"{bc.Light_Yellow_f}Volume must be{bc.Green_f} 0{bc.Light_Yellow_f}–"
            f"{bc.Green_f}100{bc.Light_Yellow_f}, got{bc.Red_f} {val}{bc.RESET}")
    return val


def validate_speed_tag(x):
    """Validate --addAutoSpeed: must be 0.5–6.0 in 0.5 increments."""
    try:
        val = float(x)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{bc.Red_f}'{x}'{bc.Light_Yellow_f} is not a valid number{bc.RESET}")
    valid = {round(i * 0.5, 1) for i in range(1, 13)}
    if val not in valid:
        raise argparse.ArgumentTypeError(
            f"{bc.Light_Yellow_f}Speed must be one of: "
            f"{bc.Green_f}0.5 1 1.5 2 2.5 3 3.5 4 4.5 5 5.5 6{bc.RESET}")
    return val


def restricted_float_or_int(x):
    """Validate --playSpeed: float or int between 0.5 and 10.0."""
    try:
        x = float(x)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{bc.Red_f}{x}{bc.Light_Yellow_f} is not a valid number{bc.RESET}")

    if x < 0.5 or x > 10.0:
        raise argparse.ArgumentTypeError(
            f"{bc.Light_Yellow_f}Value must be between{bc.Green_f} 0.5{bc.Light_Yellow_f} and"
            f"{bc.Green_f} 10.0{bc.Light_Yellow_f}, but got{bc.Red_f} {x}{bc.RESET}")

    return int(x) if x.is_integer() else x
