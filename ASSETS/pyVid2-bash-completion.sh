#
# pyVid2-bash-completion.sh Copyright (c) 2026 Nikki Cooper
#
# Bash command line completion file for pyVid2-qt.
# Assumes there is a symlink from ~/bin/pyv-qt to <pyVid2-qt_install_dir>/pyv-qt
#
# add the following line to ~/.bashrc:
# source ~/path_to_script/pyVid2-bash-completion.sh
#

_pyv2_complete() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Core argument groups
    local source_opts="--Paths --Files --loadPlayList --Glob"
    local video_opts="--loop --noFilterLoop --decoder --rgbFallback --shuffle --loopDelay --playSpeed --dispTitles --enableOSDcurpos --autoSpeed"
    local speed_tag_opts="--addAutoSpeed --delAutoSpeed --searchAutoSpeed --dryRun"
    local audio_opts="--mute --volume"
    local screenshot_opts="--sshotDir --useJPG"
    local system_opts="--verbose --display --udp-port --ir-keymap --disable-IR --metadata --cursorHide"
    local file_opts="--noIgnore --noRecurse --printIgnoreList"

    local all_opts="--help $source_opts $video_opts $speed_tag_opts $audio_opts $screenshot_opts $system_opts $file_opts"

    # GOLDEN RULE: If the user types a hyphen, they want a flag, not a value!
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "$all_opts" -- "$cur") )
        return 0
    fi

    # Scan backwards to find the last option flag used on the command line
    local last_opt=""
    local opt_index=-1
    for ((i=COMP_CWORD-1; i>0; i--)); do
        if [[ "${COMP_WORDS[i]}" =~ ^-- ]]; then
            last_opt="${COMP_WORDS[i]}"
            opt_index=i
            break
        fi
    done

    # If an argument has already been provided for a single-argument flag,
    # reset last_opt so it falls back to general options.
    if [[ -n "$last_opt" && "$opt_index" -lt $((COMP_CWORD - 1)) ]]; then
        case "$last_opt" in
            --Paths|--Files|--loadPlayList|--Glob)
                ;;
            *)
                last_opt=""
                ;;
        esac
    fi

    # Match against the active option context
    case "$last_opt" in
        --Paths)
            COMPREPLY=( $(compgen -d -- "$cur") )  # Multiple directories
            return 0
            ;;
        --Files|--loadPlayList|--Glob)
            COMPREPLY=( $(compgen -f -- "$cur") )  # Multiple files
            return 0
            ;;
        --sshotDir)
            COMPREPLY=( $(compgen -d -- "$cur") )  # single directory
            return 0
            ;;
        --ir-keymap)
            COMPREPLY=( $(compgen -f -- "$cur") )  # single file only
            return 0
            ;;
        --decoder)
            COMPREPLY=( $(compgen -W "auto nvdec vaapi software" -- "$cur") )
            return 0
            ;;
        --rgbFallback)
            COMPREPLY=( $(compgen -W "software nvdec" -- "$cur") )
            return 0
            ;;
        --udp-port)
            COMPREPLY=( $(compgen -W "{5005..5009}" -- "$cur") )
            return 0
            ;;
        --volume)
            COMPREPLY=( $(compgen -W "{0..100}" -- "$cur") )
            return 0
            ;;
        --cursorHide)
            COMPREPLY=( $(compgen -W "{0..5}" -- "$cur") )
            return 0
            ;;
        --display)
            # 1. Gather static numeric indices (0-3 or more)
            local indices="0 1 2 3"

            # 2. Dynamically discover physical connectors present on the system (e.g., HDMI-1, DP-1)
            # /sys/class/drm/ card*-* directories represent active/connected outputs.
            local connectors=""
            if [[ -d /sys/class/drm ]]; then
                # Extract names like card0-HDMI-A-1 -> HDMI-A-1 or similar
                connectors=$(ls -1 /sys/class/drm/ 2>/dev/null | grep -oE '(HDMI|DP|eDP|VGA|DVI)[A-Z0-9-]*' | sort -u)
            fi

            # Combine them into a single word-list for compgen
            COMPREPLY=( $(compgen -W "$indices $connectors" -- "$cur") )
            return 0
            ;;
        --loopDelay)
            COMPREPLY=( $(compgen -W "{0..10}" -- "$cur") )
            return 0
            ;;
        --playSpeed|--addAutoSpeed|--searchAutoSpeed)
            COMPREPLY=( $(compgen -W "0.5 1.0 1.5 2.0 2.5 3.0 3.5 4.0 4.5 5.0 5.5 6.0 6.5 7.0 7.5 8.0 8.5 9.0 9.5 10.0" -- "$cur") )
            return 0
            ;;
        *)
            COMPREPLY=( $(compgen -W "$all_opts" -- "$cur") )
            ;;
    esac
}

complete -o nosort -F _pyv2_complete pyVid
