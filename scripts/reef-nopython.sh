#!/bin/sh
# CLASS: code
# Reef's hooks when python3 is missing (hardening PR-6, docs/design/hardening-pr6-plan.md): hooks/hooks.json execs this
# instead of the guard, with the hook payload on stdin. Usage: reef-nopython.sh edit|bash|approval
# Before it the Edit|Write hook ran `exit 0`: with no python3 every edit was allowed (PR-4's audit, row H3). Now, in a Reef
# project (the guard's reach, #368: a folder holding .reef/config.json, or a linked worktree whose main checkout holds
# one), it fails closed; outside every Reef project it steps aside, as the guard does. POSIX sh and sed only.
#   edit      denied when the target or the session's cwd is in a Reef project
#   bash      in a Reef project, denied except one plain command that finds or installs python3; elsewhere today's
#             no-verify/hookspath grep (sh cannot place a command's targets: a write from outside into a project keeps that)
#   approval  in a Reef project, says the owner's answer was NOT recorded (exit 2: the PostToolUse stderr reaches Claude)
# Exit 0 allow · 2 deny (or, for approval, a message).
mode=${1:-}
p=$(cat)

field() {   # the raw string value of "<key>": a quote never opens a key inside a JSON string (it is escaped there)
	printf '%s\n' "$p" | sed -n 's/.*"'"$1"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | sed -n 1p
}

inproj() {   # exit 0 when <path> (relative to $base) lies in a Reef project
	d=$1
	case $d in /*) ;; *) d=$base/$d ;; esac
	while [ ! -d "$d" ]; do   # a file not written yet: placed by its nearest existing folder
		d=${d%/*}
		[ -n "$d" ] || d=/
	done
	d=$(cd -P -- "$d" 2>/dev/null && pwd -P) || return 0   # cannot be resolved: judged inside
	while :; do
		[ -f "$d/.reef/config.json" ] && return 0
		if [ -f "$d/.git" ]; then   # a linked worktree: gitdir: <main>/.git/worktrees/<name>
			g=$(sed -n 's/^gitdir:[[:space:]]*//p' "$d/.git")
			case $g in /*) ;; *) g=$d/$g ;; esac
			case $g in */.git/worktrees/*) [ -f "${g%/.git/worktrees/*}/.reef/config.json" ] && return 0 ;; esac
		fi
		[ "$d" = / ] && return 1
		d=${d%/*}
		[ -n "$d" ] || d=/
	done
}

cwd=$(field cwd)
[ -n "$cwd" ] || cwd=$PWD
base=$cwd
case $cwd in *\\*) here=1 ;; *) inproj "$cwd" && here=1 || here=0 ;; esac   # a JSON escape: cannot be placed, judged inside

case $mode in
edit)
	fp=$(field file_path)
	case $fp in *\\*) here=1 ;; esac
	[ "$here" = 1 ] || { [ -n "$fp" ] && inproj "$fp"; } && {
		echo "reef-guard: python3 is required to check an edit in a Reef project — denied (install python3 3.9+; \`command -v python3\` finds none)" >&2
		exit 2
	}
	exit 0 ;;
bash)
	if [ "$here" = 1 ]; then
		c=$(field command)
		case $c in *\\*) ;; *)
			# one plain command that finds or installs python3, whole (grep -x), nothing chained, redirected or substituted
			printf '%s\n' "$c" | grep -qxE '(command -v|which|type) python3|echo \$PATH|uname( -[ams])?|cat /etc/os-release|(sudo )?(apt-get|apt) update|(sudo )?(apt-get|apt|dnf|yum)( -y)? install( -y)?( python3[A-Za-z0-9.:+_-]*)+|(sudo )?apk add( python3[A-Za-z0-9.:+_-]*)+|brew install python(3|@3\.[0-9]+)?|xcode-select --install|uv python install( 3(\.[0-9]+)*)?|pyenv install 3(\.[0-9]+)*' && exit 0 ;;
		esac
		echo "reef-guard: python3 is required to check a command in a Reef project — denied; only finding or installing python3 runs without it (command -v python3, brew install python3, sudo apt-get install -y python3)" >&2
		exit 2
	fi
	if printf '%s\n' "$p" | grep -qiE 'no-?verify|hookspath'; then
		echo "reef-guard (no python3, degraded): possible gate bypass — denied" >&2
		exit 2
	fi
	exit 0 ;;
approval)
	if [ "$here" = 1 ]; then
		echo "reef-approval: python3 is missing — this answer was NOT recorded as an approval; install python3 3.9+ and ask again" >&2
		exit 2
	fi
	exit 0 ;;
*)
	echo "reef-nopython.sh: usage: reef-nopython.sh edit|bash|approval" >&2
	exit 2 ;;
esac
