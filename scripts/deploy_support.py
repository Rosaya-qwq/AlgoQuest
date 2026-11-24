"""Shared validation, service templates and browser checks for the installers."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path, PurePath, PureWindowsPath
import re
import shutil
import subprocess
import sys
from xml.etree import ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def settings(root: Path) -> dict[str, str]:
    from dotenv import dotenv_values

    values = {key: value or "" for key, value in dotenv_values(root / ".env").items()}
    return {**values, **os.environ}


def validate_config(root: Path, *, create: bool = True) -> list[str]:
    path = root / ".env"
    if not path.is_file():
        if not create:
            return ["Missing .env. Copy .env.example and configure it first."]
        shutil.copyfile(root / ".env.example", path)
        if os.name != "nt":
            path.chmod(0o600)
        print("Created .env from .env.example; existing configuration is never overwritten.", flush=True)
    config = settings(root)
    errors: list[str] = []
    try:
        users = json.loads(config.get("SUPERUSERS", "[]"))
        if not isinstance(users, list) or not users or any(not re.fullmatch(r"\d{5,12}", str(user)) or str(user) == "123456789" for user in users):
            raise ValueError
    except (ValueError, TypeError):
        errors.append("Set SUPERUSERS to your real QQ account ID list in .env.")
    if not config.get("DEEPSEEK_API_KEY", "").strip():
        errors.append("Set DEEPSEEK_API_KEY in .env for translation and judging.")
    try:
        if not 1 <= int(config.get("PORT", "8080")) <= 65535:
            raise ValueError
    except ValueError:
        errors.append("PORT must be an integer between 1 and 65535.")
    if config.get("ALGOQUEST_PING_IMAGE_ENABLED", "false").lower() in {"1", "true", "yes", "enabled"}:
        source = config.get("ALGOQUEST_PING_IMAGE_PATH", "").strip()
        if not source:
            errors.append("ALGOQUEST_PING_IMAGE_ENABLED is true but ALGOQUEST_PING_IMAGE_PATH is empty.")
        elif not source.startswith(("https://", "http://")):
            image = Path(source).expanduser()
            if not image.is_absolute():
                image = root / image
            if not image.is_file():
                errors.append("The configured /ping image is missing; copy source/ or fix ALGOQUEST_PING_IMAGE_PATH.")
    return errors


def data_path(root: Path) -> Path:
    raw = settings(root).get("ALGOQUEST_DATA_DIR", "").strip()
    path = Path(raw).expanduser() if raw else root / "data"
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def reset_local_directory(root: Path, kind: str) -> None:
    if kind not in {"data", ".venv"}:
        raise ValueError("Only project/data or project/.venv can be reset")
    expected = root.resolve() / kind
    if kind == "data" and data_path(root) != expected:
        raise ValueError("ALGOQUEST_DATA_DIR points outside project/data; reset that directory explicitly yourself")
    if expected.is_symlink() or expected.resolve() != expected:
        raise ValueError("Refusing to reset a redirected directory")
    if expected.exists():
        for child in expected.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        expected.mkdir()
    print(f"Reset {expected}; no backup was created.", flush=True)


def unit_quote(text: str, *, command: bool = False) -> str:
    if any(char in text for char in "\r\n\0"):
        raise ValueError("Service paths cannot contain control characters")
    text = text.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if command:
        text = text.replace("$", "$$")
    return '"' + text + '"'


def unit_directory(text: str) -> str:
    # WorkingDirectory consumes the entire value; shell-style quotes become
    # literal path characters here. Only systemd specifiers need escaping.
    if any(char in text for char in "\r\n\0"):
        raise ValueError("Service paths cannot contain control characters")
    return text.replace("%", "%%")


def systemd_unit(root: PurePath, user: str) -> str:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]*\$?", user):
        raise ValueError("Invalid Linux service user")
    return "\n".join([
        "# Managed by AlgoQuest deploy.sh", "[Unit]", "Description=AlgoQuest QQ Bot",
        "Wants=network-online.target", "After=network-online.target", "", "[Service]",
        "Type=simple", f"User={user}", f"WorkingDirectory={unit_directory(str(root))}",
        f"ExecStart={unit_quote(str(root / '.venv/bin/python'))} -u {unit_quote(str(root / 'main.py'), command=True)}",
        'Environment="PYTHONUNBUFFERED=1"',
        'Environment="PYTHONIOENCODING=utf-8"',
        f"Environment={unit_quote('PLAYWRIGHT_BROWSERS_PATH=' + str(root / '.playwright-browsers'))}",
        "Restart=on-failure", "RestartSec=5", "TimeoutStopSec=30", "KillMode=control-group",
        "StandardOutput=journal", "StandardError=journal", "", "[Install]", "WantedBy=multi-user.target", "",
    ])


def winsw_xml(root: PureWindowsPath, service: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", service):
        raise ValueError("Invalid Windows service name")
    node = ET.Element("service")
    for key, value in (
        ("id", service), ("name", f"AlgoQuest ({service})"),
        ("description", f"Managed by AlgoQuest deploy.ps1; project={root}"),
        ("executable", str(root / ".venv/Scripts/python.exe")),
        ("arguments", subprocess.list2cmdline(["-u", str(root / "main.py")])),
        ("workingdirectory", str(root)), ("startmode", "Automatic"),
        ("stoptimeout", "30 sec"), ("logpath", str(root / "logs")),
    ):
        ET.SubElement(node, key).text = value
    ET.SubElement(node, "env", {"name": "PYTHONUNBUFFERED", "value": "1"})
    ET.SubElement(node, "env", {"name": "PYTHONUTF8", "value": "1"})
    ET.SubElement(node, "env", {"name": "PYTHONIOENCODING", "value": "utf-8"})
    ET.SubElement(node, "env", {"name": "PLAYWRIGHT_BROWSERS_PATH", "value": str(root / ".playwright-browsers")})
    ET.SubElement(node, "onfailure", {"action": "restart", "delay": "10 sec"})
    ET.SubElement(node, "resetfailure").text = "1 hour"
    log = ET.SubElement(node, "log", {"mode": "roll-by-size"})
    ET.SubElement(log, "sizeThreshold").text = "10240"
    ET.SubElement(log, "keepFiles").text = "8"
    ET.indent(node)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(node, encoding="unicode") + "\n"


def snowluma_unit(directory: PurePath, user: str, user_home: str) -> str:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]*\$?", user):
        raise ValueError("Invalid Linux service user")
    return "\n".join([
        "# Managed by AlgoQuest deploy.sh", "[Unit]", "Description=SnowLuma QQ Bridge",
        "Wants=network-online.target", "After=network-online.target", "", "[Service]",
        "Type=simple", f"User={user}", f"WorkingDirectory={unit_directory(str(directory))}",
        f"ExecStart=/bin/bash {unit_quote(str(directory / 'launcher.sh'), command=True)}",
        f"Environment={unit_quote('HOME=' + user_home)}",
        "AmbientCapabilities=CAP_SYS_PTRACE", "CapabilityBoundingSet=CAP_SYS_PTRACE",
        "Restart=on-failure", "RestartSec=5", "TimeoutStopSec=30", "KillMode=control-group",
        "StandardOutput=journal", "StandardError=journal", "", "[Install]", "WantedBy=multi-user.target", "",
    ])


async def browser_check() -> None:
    from playwright.async_api import async_playwright
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")

    print("Launching headless Chromium...", flush=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
        try:
            page = await browser.new_page()
            await page.set_content("<p>AlgoQuest browser check</p>")
            assert await page.locator("p").inner_text() == "AlgoQuest browser check"
        finally:
            await browser.close()
    # Fetch once before service startup; later rendering can reuse the local SVG bundle.
    sys.path.insert(0, str(PROJECT_ROOT))
    from bot.services.html_render import _mathjax_bundle

    print("Preparing cached MathJax SVG resources (mirrors have timeouts)...", flush=True)
    await _mathjax_bundle()
    print("Chromium and formula rendering resources are ready.", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["config", "systemd", "snowluma-unit", "winsw", "browser-check", "data-path", "reset-data", "reset-venv"])
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--user", default="")
    parser.add_argument("--service", default="algoquest")
    parser.add_argument("--home", default=str(Path.home()))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.action == "config":
        errors = validate_config(root, create=not args.check_only)
        for error in errors:
            print(f"CONFIG: {error}", file=sys.stderr, flush=True)
        if not errors:
            print("Configuration validated; no secret values were printed.", flush=True)
        return 2 if errors else 0
    if args.action in {"systemd", "snowluma-unit", "winsw"}:
        if args.action == "systemd":
            output = systemd_unit(root, args.user)
        elif args.action == "snowluma-unit":
            output = snowluma_unit(root, args.user, args.home)
        else:
            output = winsw_xml(PureWindowsPath(root), args.service)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
    elif args.action == "browser-check":
        asyncio.run(browser_check())
    elif args.action == "data-path":
        print(data_path(root))
    else:
        reset_local_directory(root, "data" if args.action == "reset-data" else ".venv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
