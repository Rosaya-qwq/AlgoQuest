import hashlib
import io
import json
from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import sys
import tarfile
from urllib.error import HTTPError
from xml.etree import ElementTree as ET
import zipfile

import pytest

from scripts import deploy_support as deploy
from scripts import snowluma_support as snow


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    for key in ("SUPERUSERS", "DEEPSEEK_API_KEY", "PORT", "ALGOQUEST_DATA_DIR", "ALGOQUEST_PING_IMAGE_ENABLED", "ALGOQUEST_PING_IMAGE_PATH"):
        monkeypatch.delenv(key, raising=False)


def test_first_run_config_creation_preserves_existing_secrets(tmp_path, capsys):
    template = 'SUPERUSERS=["123456789"]\nDEEPSEEK_API_KEY=\n'
    (tmp_path / ".env.example").write_text(template)
    assert deploy.validate_config(tmp_path, create=False)
    assert not (tmp_path / ".env").exists()
    errors = deploy.validate_config(tmp_path)
    assert any("SUPERUSERS" in error for error in errors)
    assert any("DEEPSEEK_API_KEY" in error for error in errors)
    private = 'SUPERUSERS=["10000"]\nDEEPSEEK_API_KEY=private-key-do-not-log\nPORT=8080\n'
    (tmp_path / ".env").write_text(private)
    assert not deploy.validate_config(tmp_path)
    assert (tmp_path / ".env").read_text() == private
    assert "private-key-do-not-log" not in capsys.readouterr().out


def test_data_reset_deletes_only_contents_and_keeps_configuration(tmp_path):
    (tmp_path / ".env").write_text("ALGOQUEST_DATA_DIR=\n")
    data = tmp_path / "data"
    (data / "cache").mkdir(parents=True)
    (data / "cache/old.json").write_text("old")
    outside = tmp_path / "source"
    outside.mkdir()
    (outside / "ping.png").write_bytes(b"image")
    if sys.platform != "win32":
        (data / "link").symlink_to(outside, target_is_directory=True)
    deploy.reset_local_directory(tmp_path, "data")
    assert data.is_dir() and not list(data.iterdir())
    assert (outside / "ping.png").read_bytes() == b"image"
    assert (tmp_path / ".env").exists()


def test_data_reset_refuses_external_or_redirected_directory(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "old.json").write_text("keep")
    (tmp_path / ".env").write_text("ALGOQUEST_DATA_DIR=outside\n")
    with pytest.raises(ValueError):
        deploy.reset_local_directory(tmp_path, "data")
    assert (outside / "old.json").exists()
    if sys.platform != "win32":
        (tmp_path / ".env").write_text("ALGOQUEST_DATA_DIR=\n")
        (tmp_path / "data").symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError):
            deploy.reset_local_directory(tmp_path, "data")


def test_windows_service_definition_quotes_paths_and_shares_browser_cache():
    root = PureWindowsPath(r"C:\Algo Quest & test")
    node = ET.fromstring(deploy.winsw_xml(root, "algoquest"))
    assert node.findtext("executable") == str(root / ".venv/Scripts/python.exe")
    assert '"' in node.findtext("arguments")
    assert node.findtext("workingdirectory") == str(root)
    assert node.findtext("startmode") == "Automatic"
    env = {item.attrib["name"]: item.attrib["value"] for item in node.findall("env")}
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == str(root / ".playwright-browsers")
    assert node.find("onfailure").attrib["action"] == "restart"


def test_systemd_template_is_valid_for_spaces_percent_and_dollar(tmp_path):
    if not shutil.which("systemd-analyze") or sys.platform == "win32":
        pytest.skip("systemd-analyze not available")
    root = tmp_path / "Algo Quest 100% $test"
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/bin/python").symlink_to(sys.executable)
    (root / "main.py").write_text("")
    unit = tmp_path / "algoquest-test.service"
    unit.write_text(deploy.systemd_unit(root, "root"))
    result = subprocess.run(["systemd-analyze", "verify", str(unit)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    text = unit.read_text()
    assert "100%% $$test" in text
    assert "Restart=on-failure" in text


def test_snowluma_systemd_allows_hooking_without_accepting_terms_automatically(tmp_path):
    text = deploy.snowluma_unit(tmp_path, "root", "/root")
    assert "AmbientCapabilities=CAP_SYS_PTRACE" in text
    assert "SNOWLUMA_ACCEPT_EULA" not in text
    assert "SNOWLUMA_ACCEPT_PRIVACY" not in text


def test_snowluma_source_falls_back_to_selected_gitea_and_reads_checksum(monkeypatch):
    name = "SnowLuma-v2.4.2-linux-x64.tar.gz"
    checksum = "a" * 64
    calls = []

    def request(url, **kwargs):
        value = url.full_url
        calls.append(value)
        if "api.github.com" in value:
            raise HTTPError(value, 404, "Not Found", {}, None)
        if value.endswith("checksums.sha256"):
            return io.BytesIO(f"{checksum}  {name}\n".encode())
        return io.BytesIO(json.dumps({"assets": [
            {"name": name, "browser_download_url": "https://example/archive"},
            {"name": "checksums.sha256", "browser_download_url": "https://example/checksums.sha256"},
            {"name": name.replace(".tar.gz", "-lite.tar.gz"), "browser_download_url": "https://example/lite"},
        ]}).encode())

    monkeypatch.setattr(snow, "urlopen", request)
    asset = snow.release_asset("SnowLuma/SnowLuma", "linux-x64.tar.gz")
    assert asset["name"] == name and asset["digest"] == "sha256:" + checksum
    assert calls[1] == "https://git.hoshizukimio.com/api/v1/repos/HoshizukiMio/SnowLuma/releases/latest"


@pytest.mark.parametrize("entry", ["../escape", "..\\escape", "/absolute"])
def test_zip_archives_cannot_escape_the_install_directory(tmp_path, entry):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(entry, "bad")
    destination = tmp_path / "unpack"
    destination.mkdir()
    with pytest.raises(ValueError):
        snow.extract(archive, destination)


def test_tar_symlink_cannot_escape_install_directory(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        item = tarfile.TarInfo("link")
        item.type = tarfile.SYMTYPE
        item.linkname = "../../outside"
        bundle.addfile(item)
    target = tmp_path / "unpack"
    target.mkdir()
    with pytest.raises(ValueError):
        snow.extract(archive, target)


def test_existing_snowluma_is_reused_and_local_archive_installs(tmp_path, monkeypatch):
    monkeypatch.setattr(snow.platform, "system", lambda: "Linux")
    monkeypatch.setattr(snow.platform, "machine", lambda: "x86_64")
    archive = tmp_path / "full.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("SnowLuma/launcher.sh", "#!/bin/bash\n")
        bundle.writestr("SnowLuma/index.mjs", "// app")
    target = tmp_path / "SnowLuma"
    snow.install(target, archive, "SnowLuma/SnowLuma", "")
    (target / "private-login.json").write_text("keep-session")
    monkeypatch.setattr(snow, "release_asset", lambda *_: pytest.fail("Existing install must not download or replace login data"))
    snow.install(target, None, "SnowLuma/SnowLuma", "")
    assert (target / "private-login.json").read_text() == "keep-session"


def test_webui_link_matches_existing_port_and_omits_password(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/webui.json").write_text('{"port": 6050, "password": "do-not-copy"}')
    links = "\n".join(snow.login_links(tmp_path, 5099, "ubuntu@1.2.3.4"))
    assert "http://127.0.0.1:6050/" in links
    assert "ssh -L 6050:127.0.0.1:6050 ubuntu@1.2.3.4" in links
    assert "do-not-copy" not in links


def test_linux_plan_is_read_only_and_accepts_clean_redeployment_options(tmp_path):
    if not shutil.which("bash"):
        pytest.skip("bash unavailable")
    script = tmp_path / "deploy.sh"
    shutil.copyfile(Path(deploy.__file__).resolve().parents[1] / "deploy.sh", script)
    result = subprocess.run(["bash", str(script), "--plan", "--reset-data", "--rebuild-venv", "--snowluma-dir", "/opt/SnowLuma"], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "reset_data=true" in result.stdout
    assert list(tmp_path.iterdir()) == [script]
