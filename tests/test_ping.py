import pytest

from bot.services import ping


def test_ping_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ALGOQUEST_PING_IMAGE_ENABLED", "false")
    monkeypatch.setenv("ALGOQUEST_PING_IMAGE_PATH", "missing.png")
    assert ping.ping_image() is None


def test_ping_relative_path_uses_project_root_and_sticker_mode(monkeypatch, tmp_path):
    image = tmp_path / "source/ping.png"
    image.parent.mkdir()
    image.write_bytes(b"image")
    monkeypatch.setattr(ping, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("ALGOQUEST_PING_IMAGE_ENABLED", "true")
    monkeypatch.setenv("ALGOQUEST_PING_IMAGE_PATH", "source/ping.png")
    monkeypatch.setenv("ALGOQUEST_PING_IMAGE_SUMMARY", "测试摘要")
    segment = ping.ping_image()
    assert segment.data == {"file": image.as_uri(), "summary": "测试摘要", "sub_type": 1}


def test_ping_reports_missing_file_and_supports_remote_image(monkeypatch):
    monkeypatch.setenv("ALGOQUEST_PING_IMAGE_ENABLED", "true")
    monkeypatch.setenv("ALGOQUEST_PING_IMAGE_PATH", "missing-image-for-test.png")
    with pytest.raises(FileNotFoundError):
        ping.ping_image()
    monkeypatch.setenv("ALGOQUEST_PING_IMAGE_PATH", "https://cdn.example/pong.gif")
    assert ping.ping_image().data["file"] == "https://cdn.example/pong.gif"
