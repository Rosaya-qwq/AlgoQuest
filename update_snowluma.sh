#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY="SnowLuma/SnowLuma"
INSTALL_DIR="${SNOWLUMA_DIR:-/opt/SnowLuma}"
SERVICE_NAME="${SNOWLUMA_SERVICE:-snowluma.service}"
BACKUP_DIR="${SNOWLUMA_BACKUP_DIR:-}"
OWNER="${SNOWLUMA_OWNER:-}"
DOWNLOAD_PROXY="${SNOWLUMA_DOWNLOAD_PROXY:-}"
REQUESTED_VERSION=""
USE_LITE=0
CHECK_ONLY=0
FORCE=0
KEEP_BACKUPS="${SNOWLUMA_KEEP_BACKUPS:-3}"

usage() {
    cat <<'EOF'
Usage: sudo ./update_snowluma.sh [options]

Options:
  --install-dir PATH  SnowLuma installation directory (default: /opt/SnowLuma)
  --service NAME      systemd service name (default: snowluma.service)
  --version TAG       install a specific release, for example v1.14.17
  --lite              install the lite package instead of the bundled-Node package
  --owner USER:GROUP  owner of the installation after update
  --backup-dir PATH   backup directory (default: <install parent>/snowluma-backups)
  --keep NUMBER       number of completed backups to retain (default: 3)
  --proxy URL         HTTP/SOCKS proxy used only for GitHub downloads
  --check             only show installed/latest versions; do not update
  --force             reinstall even when the version marker matches
  -h, --help          show this help

Environment variables with the same purpose are also supported:
  SNOWLUMA_DIR, SNOWLUMA_SERVICE, SNOWLUMA_OWNER,
  SNOWLUMA_BACKUP_DIR, SNOWLUMA_KEEP_BACKUPS, SNOWLUMA_DOWNLOAD_PROXY
EOF
}

log() {
    printf '[SnowLuma updater] %s\n' "$*"
}

die() {
    printf '[SnowLuma updater] ERROR: %s\n' "$*" >&2
    exit 1
}

while (($# > 0)); do
    case "$1" in
        --install-dir)
            (($# >= 2)) || die "--install-dir requires a value"
            INSTALL_DIR="$2"
            shift 2
            ;;
        --service)
            (($# >= 2)) || die "--service requires a value"
            SERVICE_NAME="$2"
            shift 2
            ;;
        --version)
            (($# >= 2)) || die "--version requires a value"
            REQUESTED_VERSION="$2"
            shift 2
            ;;
        --lite)
            USE_LITE=1
            shift
            ;;
        --owner)
            (($# >= 2)) || die "--owner requires a value"
            OWNER="$2"
            shift 2
            ;;
        --backup-dir)
            (($# >= 2)) || die "--backup-dir requires a value"
            BACKUP_DIR="$2"
            shift 2
            ;;
        --keep)
            (($# >= 2)) || die "--keep requires a value"
            KEEP_BACKUPS="$2"
            shift 2
            ;;
        --proxy)
            (($# >= 2)) || die "--proxy requires a value"
            DOWNLOAD_PROXY="$2"
            shift 2
            ;;
        --check)
            CHECK_ONLY=1
            shift
            ;;
        --force)
            FORCE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1"
            ;;
    esac
done

[[ "$INSTALL_DIR" = /* ]] || die "installation path must be absolute: $INSTALL_DIR"
INSTALL_DIR="$(readlink -m "$INSTALL_DIR")"
[[ "$INSTALL_DIR" != "/" ]] || die "refusing to use / as the installation directory"
[[ "$SERVICE_NAME" =~ ^[A-Za-z0-9_.@-]+$ ]] || die "invalid systemd service name: $SERVICE_NAME"
[[ "$KEEP_BACKUPS" =~ ^[0-9]+$ ]] || die "--keep must be a non-negative integer"
if [[ -n "$REQUESTED_VERSION" ]]; then
    [[ "$REQUESTED_VERSION" =~ ^v[0-9A-Za-z._-]+$ ]] || die "invalid release tag: $REQUESTED_VERSION"
fi

for command_name in curl python3 tar sha256sum readlink find; do
    command -v "$command_name" >/dev/null 2>&1 || die "missing required command: $command_name"
done

case "$(uname -m)" in
    x86_64|amd64)
        RELEASE_ARCH="x64"
        NATIVE_ARCH="x64"
        ;;
    aarch64|arm64)
        RELEASE_ARCH="arm64"
        NATIVE_ARCH="arm64"
        ;;
    *)
        die "unsupported architecture: $(uname -m)"
        ;;
esac

TEMP_DIR="$(mktemp -d -t snowluma-update.XXXXXX)"
RELEASE_JSON="$TEMP_DIR/release.json"
ARCHIVE_PATH="$TEMP_DIR/snowluma.tar.gz"
EXTRACT_DIR="$TEMP_DIR/extracted"
mkdir -p "$EXTRACT_DIR"

cleanup() {
    rm -rf -- "$TEMP_DIR"
}
trap cleanup EXIT

if [[ -n "$REQUESTED_VERSION" ]]; then
    API_URL="https://api.github.com/repos/$REPOSITORY/releases/tags/$REQUESTED_VERSION"
else
    API_URL="https://api.github.com/repos/$REPOSITORY/releases/latest"
fi

log "reading release metadata"
CURL_PROXY_ARGS=()
if [[ -n "$DOWNLOAD_PROXY" ]]; then
    CURL_PROXY_ARGS=(--proxy "$DOWNLOAD_PROXY")
fi
curl -fsSL --retry 3 --retry-delay 2 "${CURL_PROXY_ARGS[@]}" \
    -H 'Accept: application/vnd.github+json' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "$API_URL" -o "$RELEASE_JSON"

PACKAGE_SUFFIX="linux-${RELEASE_ARCH}"
if ((USE_LITE)); then
    PACKAGE_SUFFIX+="-lite"
fi
PACKAGE_SUFFIX+=".tar.gz"

mapfile -t RELEASE_INFO < <(
    python3 - "$RELEASE_JSON" "$PACKAGE_SUFFIX" <<'PY'
import json
import sys

release_path, suffix = sys.argv[1:]
with open(release_path, encoding="utf-8") as release_file:
    release = json.load(release_file)

tag = str(release.get("tag_name") or "")
matches = [
    asset
    for asset in release.get("assets", [])
    if str(asset.get("name") or "").endswith(suffix)
]
if not tag or len(matches) != 1:
    raise SystemExit(f"cannot find exactly one release asset ending with {suffix!r}")

asset = matches[0]
digest = str(asset.get("digest") or "")
if digest.startswith("sha256:"):
    digest = digest.removeprefix("sha256:")
elif digest:
    raise SystemExit(f"unsupported release digest: {digest}")

print(tag)
print(asset["name"])
print(asset["browser_download_url"])
print(digest)
PY
)

((${#RELEASE_INFO[@]} == 4)) || die "failed to parse GitHub release metadata"
LATEST_VERSION="${RELEASE_INFO[0]}"
ASSET_NAME="${RELEASE_INFO[1]}"
DOWNLOAD_URL="${RELEASE_INFO[2]}"
EXPECTED_SHA256="${RELEASE_INFO[3]}"

installed_version="unknown"
if [[ -f "$INSTALL_DIR/.algoquest-snowluma-version" ]]; then
    installed_version="$(head -n 1 "$INSTALL_DIR/.algoquest-snowluma-version" | tr -d '\r\n')"
elif [[ -f "$INSTALL_DIR/package.json" ]]; then
    installed_version="$(python3 - "$INSTALL_DIR/package.json" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as package_file:
        print(json.load(package_file).get("version") or "unknown")
except (OSError, ValueError):
    print("unknown")
PY
)"
fi

log "installed version: $installed_version"
log "selected release:  $LATEST_VERSION ($ASSET_NAME)"

if ((CHECK_ONLY)); then
    exit 0
fi

((EUID == 0)) || die "run the updater as root: sudo ./update_snowluma.sh ..."
command -v systemctl >/dev/null 2>&1 || die "systemctl is required for managed updates"
[[ -d "$INSTALL_DIR" ]] || die "installation directory does not exist: $INSTALL_DIR"
[[ -f "$INSTALL_DIR/launcher.sh" ]] || die "launcher.sh not found in $INSTALL_DIR"

if [[ "$installed_version" == "$LATEST_VERSION" ]] && ((FORCE == 0)); then
    log "already on $LATEST_VERSION; use --force to reinstall"
    exit 0
fi

if [[ -z "$BACKUP_DIR" ]]; then
    BACKUP_DIR="$(dirname "$INSTALL_DIR")/snowluma-backups"
fi
[[ "$BACKUP_DIR" = /* ]] || die "backup path must be absolute: $BACKUP_DIR"
BACKUP_DIR="$(readlink -m "$BACKUP_DIR")"
[[ "$BACKUP_DIR" != "$INSTALL_DIR" ]] || die "backup directory cannot equal the installation directory"

if [[ -z "$OWNER" ]]; then
    service_user="$(systemctl show "$SERVICE_NAME" -p User --value 2>/dev/null || true)"
    if [[ -n "$service_user" && "$service_user" != "root" ]]; then
        service_group="$(id -gn "$service_user")"
        OWNER="$service_user:$service_group"
    else
        OWNER="$(stat -c '%U:%G' "$INSTALL_DIR")"
    fi
fi
[[ "$OWNER" =~ ^[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+$ ]] || die "invalid owner: $OWNER"

log "downloading $DOWNLOAD_URL"
curl -fL --retry 5 --retry-all-errors --retry-delay 3 "${CURL_PROXY_ARGS[@]}" \
    --connect-timeout 20 --max-time 1800 \
    "$DOWNLOAD_URL" -o "$ARCHIVE_PATH"

if [[ -n "$EXPECTED_SHA256" ]]; then
    ACTUAL_SHA256="$(sha256sum "$ARCHIVE_PATH" | awk '{print $1}')"
    [[ "$ACTUAL_SHA256" == "$EXPECTED_SHA256" ]] || die "SHA-256 mismatch for $ASSET_NAME"
    log "SHA-256 verified: $ACTUAL_SHA256"
else
    log "warning: this release does not publish a SHA-256 digest"
fi

tar -xzf "$ARCHIVE_PATH" -C "$EXTRACT_DIR"
SOURCE_DIR="$EXTRACT_DIR"
if [[ ! -f "$SOURCE_DIR/launcher.sh" || ! -f "$SOURCE_DIR/index.mjs" ]]; then
    launcher_path="$(find "$EXTRACT_DIR" -mindepth 2 -maxdepth 2 -type f -name launcher.sh -print -quit)"
    [[ -n "$launcher_path" ]] || die "release archive does not contain launcher.sh"
    SOURCE_DIR="$(dirname "$launcher_path")"
fi

[[ -f "$SOURCE_DIR/index.mjs" ]] || die "release archive does not contain index.mjs"
[[ -f "$SOURCE_DIR/native/snowluma-linux-${NATIVE_ARCH}.node" ]] || \
    die "release archive does not contain the ${NATIVE_ARCH} native module"
chmod +x "$SOURCE_DIR/launcher.sh"

mkdir -p "$BACKUP_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="$BACKUP_DIR/snowluma-${installed_version//[^A-Za-z0-9._-]/_}-${timestamp}.tar.gz"
install_parent="$(dirname "$INSTALL_DIR")"
install_name="$(basename "$INSTALL_DIR")"

log "creating complete backup: $backup_path"
tar -C "$install_parent" -czf "$backup_path" "$install_name"

service_was_active=0
if systemctl is-active --quiet "$SERVICE_NAME"; then
    service_was_active=1
fi

rollback() {
    local failed_dir="${INSTALL_DIR}.failed-${timestamp}"
    trap - ERR
    log "update failed; restoring $backup_path"
    systemctl stop "$SERVICE_NAME" >/dev/null 2>&1 || true
    if [[ -d "$INSTALL_DIR" ]]; then
        mv "$INSTALL_DIR" "$failed_dir"
    fi
    tar -C "$install_parent" -xzf "$backup_path"
    chown -R "$OWNER" "$INSTALL_DIR"
    if ((service_was_active)); then
        systemctl start "$SERVICE_NAME" || true
    fi
    printf '[SnowLuma updater] Failed files were kept at %s\n' "$failed_dir" >&2
}

update_started=0
on_error() {
    local exit_code=$?
    if ((update_started)); then
        rollback
    elif ((service_was_active)); then
        systemctl start "$SERVICE_NAME" >/dev/null 2>&1 || true
    fi
    exit "$exit_code"
}
trap on_error ERR

log "stopping $SERVICE_NAME"
systemctl stop "$SERVICE_NAME"
update_started=1

# Runtime state is intentionally not overwritten even if a future release
# starts shipping directories with the same names.
while IFS= read -r -d '' source_entry; do
    entry_name="$(basename "$source_entry")"
    case "$entry_name" in
        config|data|logs|media|cache|storage|downloads|tmp|temp|*.db|*.sqlite|*.sqlite3)
            log "preserving runtime path: $entry_name"
            continue
            ;;
    esac
    cp -a "$source_entry" "$INSTALL_DIR/"
done < <(find "$SOURCE_DIR" -mindepth 1 -maxdepth 1 -print0)

printf '%s\n' "$LATEST_VERSION" > "$INSTALL_DIR/.algoquest-snowluma-version"
chmod +x "$INSTALL_DIR/launcher.sh"
chown -R "$OWNER" "$INSTALL_DIR"

log "starting $SERVICE_NAME"
systemctl start "$SERVICE_NAME"
for _ in {1..15}; do
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        break
    fi
    sleep 1
done
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    printf '[SnowLuma updater] ERROR: %s did not become active\n' "$SERVICE_NAME" >&2
    false
fi
sleep 2
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    printf '[SnowLuma updater] ERROR: %s exited shortly after startup\n' "$SERVICE_NAME" >&2
    false
fi

update_started=0
trap - ERR

backup_retained=1
if ((KEEP_BACKUPS == 0)); then
    rm -f -- "$backup_path"
    backup_retained=0
else
    mapfile -t OLD_BACKUPS < <(
        find "$BACKUP_DIR" -maxdepth 1 -type f -name 'snowluma-*.tar.gz' -printf '%T@ %p\n' \
            | sort -rn \
            | tail -n "+$((KEEP_BACKUPS + 1))" \
            | cut -d' ' -f2-
    )
    if ((${#OLD_BACKUPS[@]} > 0)); then
        rm -f -- "${OLD_BACKUPS[@]}"
    fi
fi

log "updated successfully to $LATEST_VERSION"
if ((backup_retained)); then
    log "backup retained at $backup_path"
else
    log "backup removed because --keep 0 was selected"
fi
log "view logs with: journalctl -u $SERVICE_NAME -f"
