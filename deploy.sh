#!/usr/bin/env bash
# Deploy this checkout as a systemd service. No git pull or runtime-data reset by default.
set -Eeuo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd -- "$project_root"
service_name=algoquest
service_user="${SUDO_USER:-$(id -un)}"
python_command=python3
follow_logs=true
start_service=true
skip_system_deps=false
reset_data=false
rebuild_venv=false
uninstall=false
plan=false
bot_only=false
snowluma_directory="$project_root/.snowluma"
if [[ -f /opt/SnowLuma/launcher.sh ]]; then snowluma_directory=/opt/SnowLuma; fi
snowluma_archive=""
snowluma_repo=SnowLuma/SnowLuma
snowluma_service=snowluma
webui_port=5099
ssh_target=user@SERVER_IP

usage() {
    cat <<'HELP'
Usage: bash deploy.sh [options]
  --user USER          Service owner (default: invoking user, or SUDO_USER)
  --python PATH        Python 3.10+ command (default: python3)
  --service NAME       systemd service name (default: algoquest)
  --reset-data         Erase project/data after stopping the service
  --rebuild-venv       Erase and recreate this checkout's .venv
  --skip-system-deps   Skip apt and Chromium OS-library installation
  --no-start           Install/enable the service without starting it
  --no-follow          Exit after deployment instead of following the journal
  --uninstall          Remove managed services; retain project/login/configuration data
  --bot-only           Skip SnowLuma installation/management
  --snowluma-dir PATH  Reuse/install SnowLuma here (default: existing /opt/SnowLuma or .snowluma)
  --snowluma-archive P Install from a full local SnowLuma tar.gz instead of downloading
  --snowluma-repo R    Explicitly choose a trusted owner/repository for releases
  --snowluma-service N Bridge service name (default: snowluma)
  --webui-port PORT    WebUI fallback port shown in login links (default: 5099)
  --ssh-target TARGET  SSH login in printed tunnel command (example: ubuntu@1.2.3.4)
  --plan               Show the plan without changing files or services
  --help               Show this help
Ubuntu 22.04+/Debian 12+ with systemd are supported. Install QQ and log in via SnowLuma WebUI.
Deployment output is live and also saved under logs/. Ctrl+C while following logs leaves the service running.
HELP
}
while (($#)); do
    case "$1" in
        --user|--python|--service|--snowluma-dir|--snowluma-archive|--snowluma-repo|--snowluma-service|--webui-port|--ssh-target)
            (($# >= 2)) || { usage >&2; exit 2; }
            case "$1" in
                --user) service_user="$2";; --python) python_command="$2";; --service) service_name="${2%.service}";;
                --snowluma-dir) snowluma_directory="$2";; --snowluma-archive) snowluma_archive="$2";;
                --snowluma-repo) snowluma_repo="$2";; --snowluma-service) snowluma_service="${2%.service}";;
                --webui-port) webui_port="$2";; --ssh-target) ssh_target="$2";;
            esac
            shift 2;;
        --reset-data) reset_data=true; shift;;
        --rebuild-venv) rebuild_venv=true; shift;;
        --skip-system-deps) skip_system_deps=true; shift;;
        --no-start) start_service=false; shift;;
        --no-follow) follow_logs=false; shift;;
        --uninstall) uninstall=true; shift;;
        --plan) plan=true; shift;;
        --bot-only) bot_only=true; shift;;
        --help|-h) usage; exit 0;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2;;
    esac
done
[[ "$service_name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$ ]] || { echo 'Invalid service name' >&2; exit 2; }
[[ "$service_user" =~ ^[a-zA-Z_][a-zA-Z0-9_.-]*\$?$ ]] || { echo 'Invalid service user' >&2; exit 2; }
[[ "$snowluma_service" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$ && "$snowluma_service" != "$service_name" ]] || { echo 'Invalid/conflicting SnowLuma service name' >&2; exit 2; }
[[ "$webui_port" =~ ^[0-9]{1,5}$ ]] && ((10#$webui_port >= 1 && 10#$webui_port <= 65535)) || { echo 'Invalid WebUI port' >&2; exit 2; }
[[ "$snowluma_directory" = /* ]] || snowluma_directory="$project_root/$snowluma_directory"
if $uninstall && { $reset_data || $rebuild_venv; }; then
    echo '--uninstall removes the service only; do not combine it with data/environment resets.' >&2; exit 2
fi
if $plan; then
    printf 'Project: %s\nService: %s.service\nService user: %s\nPython: %s\n' "$project_root" "$service_name" "$service_user" "$python_command"
    printf 'uninstall=%s reset_data=%s rebuild_venv=%s start=%s follow_logs=%s\n' "$uninstall" "$reset_data" "$rebuild_venv" "$start_service" "$follow_logs"
    printf 'SnowLuma: bot_only=%s directory=%s service=%s\n' "$bot_only" "$snowluma_directory" "$snowluma_service"
    echo 'Plan only: no files, services, packages or data changed.'
    exit 0
fi
[[ -f main.py && -f pyproject.toml && -f scripts/deploy_support.py && -f .env.example ]] || { echo 'Run the installer from a complete AlgoQuest checkout.' >&2; exit 1; }
[[ "$(uname -s)" == Linux && -d /run/systemd/system ]] || { echo 'A Linux host with running systemd is required.' >&2; exit 1; }
id "$service_user" >/dev/null 2>&1 || { echo "Service user does not exist: $service_user" >&2; exit 1; }
as_root() { if ((EUID == 0)); then "$@"; else sudo "$@"; fi; }
as_user() {
    if [[ "$(id -un)" == "$service_user" ]]; then "$@"; else as_root runuser -u "$service_user" -- "$@"; fi
}
if ((EUID != 0)); then sudo -v; fi
umask 077
mkdir -p logs
deployment_log="$project_root/logs/deploy-linux-$(date '+%Y%m%d-%H%M%S').log"
exec > >(tee -a "$deployment_log") 2>&1
step_number=0
step() { step_number=$((step_number + 1)); printf '\n[%s] [%d/11] %s\n' "$(date '+%H:%M:%S')" "$step_number" "$*"; }
trap 'code=$?; printf "\nDeployment failed at step %s (exit %s). Log: %s\n" "$step_number" "$code" "$deployment_log" >&2; exit "$code"' ERR
unit="$service_name.service"
unit_path="/etc/systemd/system/$unit"
if as_root systemctl cat "$unit" >/dev/null 2>&1; then
    # Prevent a mistyped service name from stopping an unrelated application.
    existing="$(as_root systemctl show "$unit" -p WorkingDirectory --value)"
    [[ "$existing" == "$project_root" ]] || { echo "Existing $unit belongs to a different project path; refusing to replace it." >&2; exit 1; }
    echo "Stopping existing $unit before changing dependencies..."
    as_root systemctl stop "$unit"
fi
if $uninstall; then
    as_root systemctl disable "$unit" || true
    if [[ -f "$unit_path" ]]; then as_root rm -- "$unit_path"; fi
    as_root systemctl daemon-reload
    if ! $bot_only && as_root systemctl cat "$snowluma_service.service" >/dev/null 2>&1; then
        existing="$(as_root systemctl show "$snowluma_service.service" -p WorkingDirectory --value)"
        [[ "$existing" == "$snowluma_directory" ]] || { echo 'SnowLuma service directory differs; pass its actual --snowluma-dir.' >&2; exit 1; }
        as_root systemctl disable --now "$snowluma_service.service"
        if [[ -f "/etc/systemd/system/$snowluma_service.service" ]]; then as_root rm -- "/etc/systemd/system/$snowluma_service.service"; fi
        as_root systemctl daemon-reload
    fi
    echo "Removed $unit. Project files, .env, source/, data/ and logs/ were retained."
    exit 0
fi

step 'Install Python, Chinese fonts and OS packages (live apt output)'
if ! $skip_system_deps; then
    command -v apt-get >/dev/null || { echo 'This installer supports apt-based Ubuntu/Debian. Install OS dependencies yourself and use --skip-system-deps.' >&2; exit 1; }
    as_root apt-get update
    as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip ca-certificates curl build-essential fontconfig fonts-noto-cjk fonts-dejavu-core
else echo 'OS package installation skipped.'; fi
command -v "$python_command" >/dev/null || { echo "Python not found: $python_command" >&2; exit 1; }
"$python_command" -c 'import sys; assert (3,10) <= sys.version_info < (4,0), "Python 3.10+ is required"; print("Python:", sys.version.split()[0])'

step 'Prepare the service-owned Python virtual environment'
[[ ! -L .venv && ! -L .playwright-browsers ]] || { echo 'Refusing redirected .venv/browser directories.' >&2; exit 1; }
if $rebuild_venv; then "$python_command" scripts/deploy_support.py reset-venv; fi
service_group="$(id -gn "$service_user")"
as_root chown "$service_user:$service_group" "$project_root"
as_root install -d -o "$service_user" -g "$service_group" -m 755 .venv .playwright-browsers
as_root chown -R --no-dereference "$service_user:$service_group" .venv .playwright-browsers
if [[ -d algoquest.egg-info && ! -L algoquest.egg-info ]]; then as_root chown -R --no-dereference "$service_user:$service_group" algoquest.egg-info; fi
as_user test -r "$project_root/main.py" || { echo 'The service user cannot read the project; move it to an accessible location.' >&2; exit 1; }
if [[ -f .venv/pyvenv.cfg && ! -x .venv/bin/python ]]; then echo 'Foreign or broken .venv; rerun with --rebuild-venv.' >&2; exit 1; fi
as_user "$python_command" -m venv "$project_root/.venv"
python_bin="$project_root/.venv/bin/python"

step 'Install/upgrade project dependencies (live pip output)'
as_user "$python_bin" -m pip install --upgrade pip
as_user "$python_bin" -m pip install -e "$project_root"

step 'Validate .env without printing keys or cookies'
if [[ -f .env ]]; then as_root chown "$service_user:$service_group" .env; as_root chmod 600 .env; fi
as_user "$python_bin" scripts/deploy_support.py config
as_root chown "$service_user:$service_group" .env
as_root chmod 600 .env
if $reset_data; then as_root "$python_bin" scripts/deploy_support.py reset-data; fi
runtime_path="$(as_user "$python_bin" scripts/deploy_support.py data-path)"
as_root install -d -o "$service_user" -g "$service_group" -m 755 "$runtime_path"

step 'Install Chromium and its runtime libraries (live download progress)'
if ! $skip_system_deps; then as_root "$python_bin" -m playwright install-deps chromium; fi
as_user env PLAYWRIGHT_BROWSERS_PATH="$project_root/.playwright-browsers" "$python_bin" -m playwright install chromium

step 'Check Chromium and cache mathematical rendering resources'
as_user env PLAYWRIGHT_BROWSERS_PATH="$project_root/.playwright-browsers" "$python_bin" scripts/deploy_support.py browser-check

step 'Install/reuse SnowLuma without replacing login/configuration state'
if ! $bot_only; then
    if as_root systemctl cat "$snowluma_service.service" >/dev/null 2>&1; then
        existing="$(as_root systemctl show "$snowluma_service.service" -p WorkingDirectory --value)"
        [[ "$existing" == "$snowluma_directory" ]] || { echo 'Existing SnowLuma service uses another directory; pass its actual --snowluma-dir or use --bot-only.' >&2; exit 1; }
        as_root systemctl stop "$snowluma_service.service"
    fi
    snow_args=(scripts/snowluma_support.py install --directory "$snowluma_directory" --repo "$snowluma_repo")
    if [[ -n "$snowluma_archive" ]]; then snow_args+=(--archive "$snowluma_archive"); fi
    as_root "$python_bin" "${snow_args[@]}"
    as_root chown -R --no-dereference "$service_user:$service_group" "$snowluma_directory"
else echo 'SnowLuma installation skipped (--bot-only).'; fi

step 'Configure the managed SnowLuma bridge and print first-login links'
if ! $bot_only; then
    snow_unit_file="$(mktemp --suffix=.service)"
    service_home="$(getent passwd "$service_user" | cut -d: -f6)"
    "$python_bin" scripts/deploy_support.py snowluma-unit --root "$snowluma_directory" --user "$service_user" --home "$service_home" --output "$snow_unit_file"
    as_root systemd-analyze verify "$snow_unit_file"
    as_root install -m 644 "$snow_unit_file" "/etc/systemd/system/$snowluma_service.service"
    rm -- "$snow_unit_file"
    as_root systemctl daemon-reload
    as_root systemctl enable "$snowluma_service.service"
    if $start_service; then as_root systemctl restart "$snowluma_service.service"; fi
    "$python_bin" scripts/snowluma_support.py links --directory "$snowluma_directory" --webui-port "$webui_port" --ssh-target "$ssh_target"
    echo "SnowLuma initial password/logs: sudo journalctl -u $snowluma_service.service -n 80 --no-pager"
else echo 'SnowLuma service management skipped.'; fi

step 'Write and validate the systemd unit'
temporary_unit="$(mktemp --suffix=.service)"
trap 'rm -f -- "$temporary_unit"' EXIT
"$python_bin" scripts/deploy_support.py systemd --user "$service_user" --output "$temporary_unit"
as_root systemd-analyze verify "$temporary_unit"
as_root install -m 644 "$temporary_unit" "$unit_path"
as_root systemctl daemon-reload
as_root systemctl enable "$unit"

step 'Start the managed bot service'
if $start_service; then
    as_root systemctl restart "$unit"
    as_root systemctl is-active "$unit"
else echo 'Service installed/enabled; automatic startup skipped (--no-start).'; fi

step 'Deployment complete; show live bot startup and problem-buffer progress'
printf 'Deployment log: %s\nService status: sudo systemctl status %s\nBot logs: sudo journalctl -u %s -f\n' "$deployment_log" "$unit" "$unit"
echo 'Service active means the process is managed; problem warmup and QQ connection are reported in the bot logs.'
echo 'In SnowLuma WebUI, log in/attach QQ and configure reverse WebSocket: ws://127.0.0.1:8080/onebot/v11/ws/ (use PORT in .env).'
if $follow_logs && $start_service; then
    trap 'echo; echo "Stopped following logs. The bot service is still running."; exit 0' INT
    journal_args=(-u "$unit")
    if ! $bot_only; then journal_args+=(-u "$snowluma_service.service"); fi
    as_root journalctl "${journal_args[@]}" -n 60 -f --no-pager || [[ $? == 130 ]]
fi
