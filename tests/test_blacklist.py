from pathlib import Path

from bot.services import blacklist


def test_normalize_uid_accepts_numeric_qq_id() -> None:
    assert blacklist.normalize_uid(" 123456789 ") == "123456789"
    assert blacklist.normalize_uid("abc") is None
    assert blacklist.normalize_uid("123") is None


def test_add_and_remove_blacklist_user(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(blacklist, "BLACKLIST_PATH", tmp_path / "users.json")

    assert blacklist.add_to_blacklist("123456789") is True
    assert blacklist.add_to_blacklist("123456789") is False
    assert blacklist.is_blacklisted("123456789") is True

    assert blacklist.remove_from_blacklist("123456789") is True
    assert blacklist.remove_from_blacklist("123456789") is False
    assert blacklist.is_blacklisted("123456789") is False
