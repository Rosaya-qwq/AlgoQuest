"""Install a supplied/selected SnowLuma release and print local/SSH login links."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tarfile
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import zipfile

DEFAULT_FALLBACK = "https://git.hoshizukimio.com/HoshizukiMio/SnowLuma"


def archive_suffix(system: str, machine: str) -> str:
    if system == "Windows" and machine.lower() in {"amd64", "x86_64"}:
        return "win-x64.zip"
    if system == "Linux":
        architecture = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(machine.lower())
        if architecture:
            return f"linux-{architecture}.tar.gz"
    raise ValueError(f"Unsupported SnowLuma platform: {system}/{machine}")


def release_api(repo: str, version: str = "") -> str:
    if repo.startswith("https://"):
        parsed = urlsplit(repo)
        slug = parsed.path.strip("/").removesuffix(".git")
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Invalid SnowLuma release source URL")
        origin = f"https://{parsed.netloc}"
        if parsed.hostname == "github.com":
            origin = "https://api.github.com"
        else:
            origin += "/api/v1"
    else:
        slug, origin = repo, "https://api.github.com"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", slug):
        raise ValueError("Invalid release repository; use owner/repository or an HTTPS repository URL")
    if version and not re.fullmatch(r"v?[0-9A-Za-z_.-]+", version):
        raise ValueError("Invalid release version")
    endpoint = "tags/" + version if version else "latest"
    return f"{origin}/repos/{slug}/releases/{endpoint}"


def release_asset(repo: str, suffix: str, version: str = "", fallback: str = DEFAULT_FALLBACK) -> dict:
    sources = list(dict.fromkeys(source for source in (repo, fallback) if source))
    for source in sources:
        endpoint = release_api(source, version)
        print(f"Reading SnowLuma releases from {source}...", flush=True)
        try:
            request = Request(endpoint, headers={"User-Agent": "AlgoQuest-deploy", "Accept": "application/json"})
            with urlopen(request, timeout=20) as response:
                payload = json.load(response)
            matches = [asset for asset in payload.get("assets", []) if str(asset.get("name", "")).endswith(suffix)]
            if len(matches) != 1:
                raise ValueError(f"No unique full release ending in {suffix}")
            asset = dict(matches[0])
            if not str(asset.get("digest", "")).startswith("sha256:"):
                checksums = next((entry for entry in payload.get("assets", []) if entry.get("name") == "checksums.sha256"), None)
                if checksums:
                    with urlopen(Request(checksums["browser_download_url"], headers={"User-Agent": "AlgoQuest-deploy"}), timeout=20) as response:
                        checksum_text = response.read(1024 * 1024).decode("utf-8")
                    for line in checksum_text.splitlines():
                        match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?(.+)", line.strip())
                        if match and match.group(2) == asset["name"]:
                            asset["digest"] = "sha256:" + match.group(1).lower()
                            break
                    if not asset.get("digest"):
                        raise ValueError("Release checksum file does not list the selected archive")
            print(f"Selected release source: {source}; package: {asset['name']}", flush=True)
            return asset
        except (OSError, ValueError) as exc:
            reason = f"HTTP {exc.code}" if isinstance(exc, HTTPError) else type(exc).__name__
            print(f"Release source unavailable ({reason}); trying the configured backup if available.", flush=True)
    raise ValueError("All configured SnowLuma sources failed; supply a local full archive or reuse an existing installation directory")


def download(asset: dict, target: Path) -> None:
    print(f"Downloading {asset['name']}...", flush=True)
    request = Request(asset["browser_download_url"], headers={"User-Agent": "AlgoQuest-deploy"})
    digest = hashlib.sha256()
    size, last_report = 0, 0.0
    with urlopen(request, timeout=30) as response, target.open("wb") as output:
        total = int(response.headers.get("Content-Length", "0"))
        while chunk := response.read(256 * 1024):
            output.write(chunk)
            digest.update(chunk)
            size += len(chunk)
            if time.monotonic() - last_report >= 1:
                percent = f" {100 * size / total:.1f}%" if total else ""
                print(f"SnowLuma download:{percent} {size / 1048576:.1f} MiB", flush=True)
                last_report = time.monotonic()
    expected = str(asset.get("digest") or "")
    if expected.startswith("sha256:") and digest.hexdigest() != expected[7:]:
        raise ValueError("SnowLuma download checksum mismatch")
    print(f"Download complete: {size / 1048576:.1f} MiB" + ("; SHA-256 verified." if expected.startswith("sha256:") else "."), flush=True)


def _inside(directory: Path, name: str) -> Path:
    target = (directory / name.replace("\\", "/")).resolve()
    if not target.is_relative_to(directory.resolve()):
        raise ValueError("Archive entry escapes its extraction directory")
    return target


def extract(archive: Path, directory: Path) -> None:
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                _inside(directory, member.filename)
            bundle.extractall(directory)
    else:
        with tarfile.open(archive) as bundle:
            for member in bundle:
                destination = _inside(directory, member.name)
                if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                    raise ValueError("Unsupported special file in SnowLuma archive")
                if member.issym():
                    _inside(directory, str(destination.parent.relative_to(directory) / member.linkname))
                if member.islnk():
                    _inside(directory, member.linkname)
                if hasattr(tarfile, "data_filter"):
                    bundle.extract(member, directory, filter="data")
                else:
                    bundle.extract(member, directory)


def install(directory: Path, archive: Path | None, repo: str, version: str) -> None:
    directory = directory.absolute()
    launcher = "launcher.bat" if platform.system() == "Windows" else "launcher.sh"
    if directory.is_symlink():
        raise ValueError("Refusing a redirected SnowLuma install directory")
    if (directory / launcher).is_file():
        print(f"Reusing existing SnowLuma: {directory}; login/configuration retained.", flush=True)
        return
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("SnowLuma directory is non-empty but has no launcher; select a fresh or complete installation directory")
    directory.parent.mkdir(parents=True, exist_ok=True)
    suffix = archive_suffix(platform.system(), platform.machine())
    with tempfile.TemporaryDirectory(prefix="snowluma-install-", dir=directory.parent) as temporary:
        staging = Path(temporary)
        if archive is None:
            asset = release_asset(repo, suffix, version)
            archive = staging / asset["name"]
            download(asset, archive)
        else:
            archive = archive.expanduser().resolve()
            if not archive.is_file():
                raise ValueError("The supplied SnowLuma archive does not exist")
            print(f"Using supplied SnowLuma archive: {archive.name}", flush=True)
        unpacked = staging / "unpacked"
        unpacked.mkdir()
        print("Extracting SnowLuma...", flush=True)
        extract(archive, unpacked)
        candidates = [unpacked] if (unpacked / launcher).is_file() else [p.parent for p in unpacked.glob(f"*/{launcher}")]
        if len(candidates) != 1:
            raise ValueError(f"Archive must contain one top-level {launcher}")
        source = candidates[0]
        if not (source / "index.mjs").is_file():
            raise ValueError("Archive is missing SnowLuma index.mjs; use a full release package")
        shutil.copytree(source, directory, dirs_exist_ok=True, symlinks=True)
        if os.name != "nt":
            (directory / launcher).chmod((directory / launcher).stat().st_mode | 0o111)
            for binary in directory.rglob("node"):
                if binary.is_file():
                    binary.chmod(binary.stat().st_mode | 0o111)
    print(f"SnowLuma installed: {directory}", flush=True)


def webui_port(directory: Path, fallback: int) -> int:
    for filename in ("config/webui.json", "config/config.json", "config.json"):
        try:
            payload = json.loads((directory / filename).read_text(encoding="utf-8"))
            web = payload.get("webui", {})
            candidate = web.get("port") if isinstance(web, dict) else None
            candidate = candidate or payload.get("webuiPort") or (payload.get("port") if "webui.json" in filename else None)
            if candidate and 1 <= int(candidate) <= 65535:
                return int(candidate)
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    return fallback


def login_links(directory: Path, port: int, ssh_target: str) -> list[str]:
    port = webui_port(directory, port)
    if not 1 <= port <= 65535:
        raise ValueError("Invalid WebUI port")
    if not re.fullmatch(r"[A-Za-z0-9_.@:\[\]-]+", ssh_target) or ssh_target.startswith("-"):
        raise ValueError("Invalid SSH target")
    return [
        f"SnowLuma WebUI / first login: http://127.0.0.1:{port}/",
        "Initial account: admin. The initial password is printed in SnowLuma startup logs.",
        f"Remote host: run on your own computer: ssh -L {port}:127.0.0.1:{port} {ssh_target}",
        f"Then open this LOCAL URL: http://127.0.0.1:{port}/",
        "If SnowLuma logs report a different WebUI port, use that port in the URL and SSH tunnel.",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "links"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--repo", default="SnowLuma/SnowLuma")
    parser.add_argument("--version", default="")
    parser.add_argument("--webui-port", type=int, default=5099)
    parser.add_argument("--ssh-target", default="user@SERVER_IP")
    args = parser.parse_args()
    if args.action == "install":
        install(args.directory, args.archive, args.repo, args.version)
    else:
        for line in login_links(args.directory, args.webui_port, args.ssh_target):
            print(line, flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(f"SnowLuma setup: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(2)
