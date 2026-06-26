#  cmdLineHelp.py Copyright (c) 2025, 2026 Nikki Cooper
#
#  This program and the accompanying materials are made available under the
#  terms of the GNU Lesser General Public License, version 3.0 which is available at
#  https://www.gnu.org/licenses/gpl-3.0.html#license-text
#
# help dictionary for argparse usage in cmdLineOpts.py
#
from Bcolors import Bcolors
bc = Bcolors()

# argparse parser.add_argument_group()
# pylint: disable=use-dict-literal
group = dict(
    source_group=f"{bc.BOLD}{bc.Light_Blue_f}Source (one or more required, may be combined){bc.RESET}",
    video_group=f"{bc.BOLD}{bc.Blue_f}Video Playback Options{bc.RESET}",
    audio_group=f"{bc.BOLD}{bc.Blue_f}Audio Options{bc.RESET}",
    screenshot_group=f"{bc.BOLD}{bc.Blue_f}Screenshot Options{bc.RESET}",
    system_group=f"{bc.BOLD}{bc.Light_Blue_f}System Options{bc.RESET}",
    file_group=f"{bc.BOLD}{bc.Light_Blue_f}File Options{bc.RESET}",
    tag_group=f"{bc.BOLD}{bc.Light_Blue_f}Speed Tag Tools  {bc.Dark_Gray_f}(program exits after running){bc.RESET}",
)

# argparse help=""
# pylint: disable=redefined-builtin
help = dict(
    Paths=f"{bc.Light_Yellow_f}Directories to scan for playable media.\n{bc.Magenta_f}Specify: {bc.Green_f}<Path> <Path> <Path> ...{bc.RESET}",
    Files=f"{bc.Light_Yellow_f}Load & play supported media.\n{bc.Magenta_f}Specify: {bc.Green_f}<File> <File> <File> ...{bc.RESET}",
    loadPlayList=f"{bc.Light_Yellow_f}Load and play a playlist from a file.\n{bc.Magenta_f}Specify:{bc.Green_f} /path/PlaylistName{bc.RESET}",
    Glob=(f"{bc.Light_Yellow_f}Glob / numeric-range patterns to match video files.\n"
          f"{bc.Magenta_f}Supports: {bc.Green_f}*  ?  [...]  {{N-M}}  {{N-}}\n"
          f"{bc.Magenta_f}  {{N-M}}{bc.Light_Yellow_f} numeric range, e.g. {bc.Green_f}Set{{001-020}}/*.mp4\n"
          f"{bc.Magenta_f}  {{N-}} {bc.Light_Yellow_f} from N to 999\n"
          f"{bc.Light_Yellow_f}Recursive by default; {bc.White_f}--noRecurse{bc.Light_Yellow_f} for flat match.\n"
          f"{bc.Magenta_f}Specify: {bc.Green_f}<pattern> <pattern> ...{bc.RESET}"),
    #
    loop=f"{bc.Light_Yellow_f}Loop videos instead of exiting{bc.RESET}",
    decoder=(f"{bc.Light_Yellow_f}Hardware decoder to use.\n"
             f"{bc.Magenta_f}Choices: {bc.Green_f}auto  nvdec  vulkan  vaapi  software\n"
             f"{bc.Magenta_f}Default: {bc.Green_f}auto{bc.RESET}"),
    shuffle=f"{bc.Light_Yellow_f}Play videos in random order{bc.RESET}",
    loopDelay=f"{bc.Light_Yellow_f}The delay in seconds between each video.\n{bc.Magenta_f}Default:{bc.Green_f} 1{bc.Light_Yellow_f} sec{bc.Magenta_f} (recommended){bc.RESET}",
    playSpeed=f"{bc.Light_Yellow_f}Set playback speed ({bc.Green_f}0.5{bc.Light_Yellow_f} - {bc.Green_f}10.0{bc.Light_Yellow_f})\n{bc.Magenta_f}Default: {bc.Green_f}2.0{bc.RESET}",
    enableOSDcurpos=(f"{bc.Light_Yellow_f}Show always-visible position counter (upper-left).\n"
                     f"{bc.Magenta_f}Toggle:{bc.Green_f} o{bc.Light_Yellow_f} key  |  IR:{bc.Green_f} 1\n"
                     f"{bc.Magenta_f}Default:{bc.Green_f} off{bc.RESET}"),
    autoSpeed=(f"{bc.Light_Yellow_f}Honour {bc.Green_f}auto_speed{bc.Light_Yellow_f} XMP tags embedded in video files.\n"
               f"When a tagged video is encountered, its speed is applied for\n"
               f"that video only; the original speed is restored afterward.\n"
               f"{bc.Magenta_f}Default:{bc.Green_f} off{bc.RESET}"),
    #
    addAutoSpeed=(f"{bc.Light_Yellow_f}Write an {bc.Green_f}auto_speed{bc.Light_Yellow_f} XMP tag to video files.\n"
                  f"{bc.Magenta_f}Specify: {bc.Green_f}SPEED{bc.Light_Yellow_f} — one of: "
                  f"{bc.Green_f}0.5 1 1.5 2 2.5 3 3.5 4 4.5 5 5.5 6\n"
                  f"{bc.Light_Yellow_f}Existing tag is replaced.  Use with {bc.White_f}--dryRun{bc.Light_Yellow_f} to preview.\n"
                  f"{bc.Magenta_f}Sources: {bc.Green_f}--Paths  --Files  --Glob{bc.Light_Yellow_f}  (not --loadPlayList){bc.RESET}"),
    delAutoSpeed=(f"{bc.Light_Yellow_f}Delete the {bc.Green_f}auto_speed{bc.Light_Yellow_f} XMP tag from video files.\n"
                  f"Only files that actually carry the tag are modified.\n"
                  f"{bc.Light_Yellow_f}Always prompts for confirmation.  Use with {bc.White_f}--dryRun{bc.Light_Yellow_f} to preview.\n"
                  f"{bc.Magenta_f}Sources: {bc.Green_f}--Paths  --Files  --Glob{bc.Light_Yellow_f}  (not --loadPlayList){bc.RESET}"),
    searchAutoSpeed=(f"{bc.Light_Yellow_f}Search for {bc.Green_f}auto_speed{bc.Light_Yellow_f} XMP tags and print a report.\n"
                     f"{bc.Magenta_f}Specify: {bc.Green_f}SPEED{bc.Light_Yellow_f} to filter (e.g. {bc.Green_f}4.5{bc.Light_Yellow_f}), "
                     f"or omit to list all tagged files.\n"
                     f"{bc.Magenta_f}Sources: {bc.Green_f}--Paths  --Files  --Glob  --loadPlayList{bc.RESET}"),
    dryRun=(f"{bc.Light_Yellow_f}Preview what {bc.White_f}--addAutoSpeed{bc.Light_Yellow_f} or "
            f"{bc.White_f}--delAutoSpeed{bc.Light_Yellow_f} would do — no files are modified.{bc.RESET}"),
    #
    verbose=f"{bc.Light_Yellow_f}Enable verbose output.{bc.RESET}",
    display=f"{bc.Light_Yellow_f}Enable output on a specific display.\n{bc.Magenta_f}Default: {bc.Green_f}The currently active display{bc.RESET}",
    udp_port=f"{bc.Light_Yellow_f}UDP port to listen on for {bc.White_f}IR Remote Control{bc.Light_Yellow_f} commands.\n{bc.Magenta_f}Default: {bc.Green_f}5005{bc.RESET}",
    ir_keymap=f"{bc.Light_Yellow_f}Path to a custom {bc.White_f}IR Remote Control{bc.Light_Yellow_f} keymap file.\n{bc.Magenta_f}Default: {bc.Green_f}~/.local/share/pyVid2-qt/ir_keymap.conf{bc.RESET}",
    disable_IR=f"{bc.Light_Yellow_f}Disable the {bc.White_f}IR Remote Control{bc.Light_Yellow_f} UDP listener.\n{bc.Magenta_f}Default: {bc.Green_f}IR Remote enabled{bc.RESET}",
    metadata=f"{bc.Light_Yellow_f}Enable metadata output to the console.\n{bc.Magenta_f}Default: {bc.Green_f}disabled{bc.RESET}",
    #
    noIgnore=f"{bc.Light_Yellow_f}Do not honor {bc.Green_f}.ignore{bc.Light_Yellow_f} files.{bc.RESET}",
    noRecurse=f"{bc.Light_Yellow_f}Do not recurse into subfolders (applies to {bc.White_f}--Paths{bc.Light_Yellow_f} and {bc.White_f}--Glob{bc.Light_Yellow_f}).{bc.RESET}",
    printIgnoreList=f"{bc.Light_Yellow_f}Search for {bc.Green_f}.ignore{bc.Light_Yellow_f} files in subfolders specified by {bc.White_f}--Paths{bc.Light_Yellow_f}{bc.RESET}",
    #
    mute=f"{bc.Light_Yellow_f}Start with audio muted.\n{bc.Magenta_f}Default: {bc.Green_f}audio on{bc.RESET}",
    volume=(f"{bc.Light_Yellow_f}Set initial volume ({bc.Green_f}0{bc.Light_Yellow_f}–{bc.Green_f}100{bc.Light_Yellow_f}).\n"
            f"{bc.Magenta_f}Default: {bc.Green_f}0{bc.Light_Yellow_f} (silent — set explicitly to hear audio){bc.RESET}"),
    #
    sshotDir=f"{bc.Light_Yellow_f}Base directory for screenshots.\n{bc.Magenta_f}Default: {bc.Green_f}~/pyVid2-qt-Shots{bc.RESET}",
    useJPG=f"{bc.Light_Yellow_f}Save screenshots as JPEG instead of PNG.\n{bc.Magenta_f}Default: {bc.Green_f}PNG (lossless){bc.RESET}",
)
