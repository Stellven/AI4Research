#!/usr/bin/env bash

bash_major_version() {
    "$1" -c 'printf "%s\n" "${BASH_VERSINFO[0]:-0}"' 2>/dev/null || printf '0\n'
}

bash_is_4_plus() {
    major="$(bash_major_version "$1")"
    case "$major" in
        ''|*[!0-9]*) return 1 ;;
    esac
    [ "$major" -ge 4 ]
}

find_bash4() {
    checked=""
    for candidate in "${SOLAR_BASH:-}" bash bash5 bash4 /opt/homebrew/bin/bash /usr/local/bin/bash /usr/bin/bash /bin/bash; do
        [ -n "$candidate" ] || continue
        if [ -x "$candidate" ]; then
            path="$candidate"
        else
            path="$(command_path "$candidate")"
        fi
        [ -n "$path" ] || continue
        case " $checked " in
            *" $path "*) continue ;;
        esac
        checked="$checked $path"
        if bash_is_4_plus "$path"; then
            printf '%s\n' "$path"
            return 0
        fi
    done
    return 1
}

system_dep_packages() {
    for dep in "$@"; do
        case "$dep" in
            tmux) printf 'tmux ' ;;
            jq) printf 'jq ' ;;
            bash4) printf 'bash ' ;;
        esac
    done
    printf '\n'
}

system_dep_install_command() {
    packages="$(system_dep_packages "$@")"
    case "$OS_KIND" in
        darwin)
            printf 'brew install %s\n' "$packages"
            ;;
        linux|wsl)
            if command -v apt-get >/dev/null 2>&1; then
                printf 'sudo apt-get update && sudo apt-get install -y %s\n' "$packages"
            elif command -v dnf >/dev/null 2>&1; then
                printf 'sudo dnf install -y %s\n' "$packages"
            elif command -v pacman >/dev/null 2>&1; then
                printf 'sudo pacman -S --needed %s\n' "$packages"
            else
                printf 'install packages with your OS package manager: %s\n' "$packages"
            fi
            ;;
        *)
            printf 'install packages with your OS package manager: %s\n' "$packages"
            ;;
    esac
}

missing_system_deps() {
    missing=""
    command -v tmux >/dev/null 2>&1 || missing="$missing tmux"
    command -v jq >/dev/null 2>&1 || missing="$missing jq"
    if ! find_bash4 >/dev/null 2>&1; then
        missing="$missing bash4"
    fi
    printf '%s\n' "$missing" | awk '{$1=$1; print}'
}

installer_run_pkg_command() {
    if [ "$(id -u)" = "0" ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        return 127
    fi
}

try_install_system_deps() {
    [ "$#" -gt 0 ] || return 0
    packages="$(system_dep_packages "$@")"
    [ -n "$packages" ] || return 0

    case "$OS_KIND" in
        darwin)
            if ! command -v brew >/dev/null 2>&1; then
                yellow "Homebrew not found; install system dependencies with: $(system_dep_install_command "$@")"
                yellow "Install Homebrew first if needed: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
                return 1
            fi
            info "installing system dependencies: brew install $packages"
            brew install $packages
            ;;
        linux|wsl)
            if command -v apt-get >/dev/null 2>&1; then
                info "installing system dependencies: apt-get install $packages"
                installer_run_pkg_command apt-get update \
                    && installer_run_pkg_command apt-get install -y $packages
            elif command -v dnf >/dev/null 2>&1; then
                info "installing system dependencies: dnf install $packages"
                installer_run_pkg_command dnf install -y $packages
            elif command -v pacman >/dev/null 2>&1; then
                info "installing system dependencies: pacman -S --needed $packages"
                installer_run_pkg_command pacman -S --needed $packages
            else
                yellow "no supported package manager found; install system dependencies with: $(system_dep_install_command "$@")"
                return 1
            fi
            ;;
        *)
            yellow "unsupported OS for automatic system dependency install; run: $(system_dep_install_command "$@")"
            return 1
            ;;
    esac
}

bootstrap_system_deps() {
    case " $SELECTED_COMPONENTS " in
        *" harness "*) : ;;
        *) return 0 ;;
    esac

    missing="$(missing_system_deps)"
    [ -n "$missing" ] || {
        info "system dependencies ok: tmux, jq, bash>=4"
        return 0
    }

    if [ "$DRY_RUN" = "true" ]; then
        info "dry-run: would install missing system dependencies: $missing"
        info "dry-run: command: $(system_dep_install_command $missing)"
        return 0
    fi

    yellow "missing harness system dependencies: $missing"
    if [ "$BOOTSTRAP_SYSTEM_DEPS" = "true" ]; then
        if ! try_install_system_deps $missing; then
            yellow "could not auto-install all system dependencies; run: $(system_dep_install_command $missing)"
        fi
    elif [ "$YES" != "true" ] && solar_can_prompt; then
        yellow "install command: $(system_dep_install_command $missing)"
        wizard_read "Install these system dependencies now? [y/N] "
        case "$WIZARD_ANSWER" in
            y|Y|yes|YES)
                if ! try_install_system_deps $missing; then
                    yellow "could not auto-install all system dependencies; run: $(system_dep_install_command $missing)"
                fi
                ;;
            *)
                yellow "skipping system dependency bootstrap; run later: $(system_dep_install_command $missing)"
                ;;
        esac
    else
        yellow "skipping system dependency bootstrap; run: $(system_dep_install_command $missing)"
    fi

    still_missing="$(missing_system_deps)"
    if [ -n "$still_missing" ]; then
        yellow "system dependencies still missing: $still_missing"
        if [ "$BOOTSTRAP_SYSTEM_DEPS" = "true" ]; then
            die "required harness system dependencies still missing: $still_missing. Run: $(system_dep_install_command $still_missing)"
        fi
        yellow "Solar install will continue, but harness launch will fail until you run: $(system_dep_install_command $still_missing)"
    else
        info "system dependencies installed: tmux, jq, bash>=4"
    fi
}
