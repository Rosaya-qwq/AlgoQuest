from bot.services.emoji_reaction import (
    auto_unicode_binding_action,
    emoji_binding_for,
    emoji_bindings,
    extract_emoji_id,
    extract_notice_emoji_id,
    is_single_super_emoji_message,
    parse_emoji_binding_action,
    remove_unicode_emoji_binding,
    set_unicode_emoji_binding,
    unicode_emoji_decimal_id,
    validate_emoji_binding,
)


def test_extract_builtin_face_id() -> None:
    message = [{"type": "face", "data": {"id": "14"}}]

    assert extract_emoji_id(message) == "14"


def test_extract_super_emoji_id_from_mface() -> None:
    message = [{"type": "mface", "data": {"emoji_id": "123456"}}]

    assert extract_emoji_id(message) == "123456"


def test_extract_super_emoji_id_from_image_segment() -> None:
    message = [{"type": "image", "data": {"emojiId": "654321"}}]

    assert extract_emoji_id(message) == "654321"


def test_extract_cq_code_face_id_from_text() -> None:
    message = [{"type": "text", "data": {"text": "[CQ:face,id=66]"}}]

    assert extract_emoji_id(message) == "66"


def test_extract_cq_code_super_emoji_id_from_text() -> None:
    message = [{"type": "text", "data": {"text": "[CQ:mface,emoji_id=777,key=abc]"}}]

    assert extract_emoji_id(message) == "777"


def test_single_super_emoji_allows_blank_text_around_it() -> None:
    message = [
        {"type": "text", "data": {"text": " "}},
        {"type": "mface", "data": {"emoji_id": "888"}},
        {"type": "text", "data": {"text": "\n"}},
    ]

    assert is_single_super_emoji_message(message)


def test_single_super_emoji_rejects_builtin_face() -> None:
    message = [{"type": "face", "data": {"id": "14"}}]

    assert not is_single_super_emoji_message(message)


def test_single_super_emoji_accepts_face_type_three() -> None:
    message = [
        {
            "type": "face",
            "data": {
                "id": "368",
                "raw": {"faceIndex": 368, "faceText": "/奥特笑哭", "faceType": 3},
            },
        }
    ]

    assert is_single_super_emoji_message(message)
    assert extract_emoji_id(message, allow_text=False) == "368"


def test_single_super_emoji_rejects_extra_text() -> None:
    message = [
        {"type": "mface", "data": {"emoji_id": "888"}},
        {"type": "text", "data": {"text": "贴一下"}},
    ]

    assert not is_single_super_emoji_message(message)


def test_extract_notice_emoji_id_from_latest_like() -> None:
    likes = [{"emoji_id": "12951", "count": 4}, {"emoji_id": "368", "count": 1}]

    assert extract_notice_emoji_id(likes) == "368"


def test_extract_notice_emoji_id_rejects_invalid_payload() -> None:
    assert extract_notice_emoji_id({"emoji_id": "12951"}) is None


def test_unicode_emoji_binding_persists_mappings(tmp_path, monkeypatch) -> None:
    from bot.services import emoji_reaction

    monkeypatch.setattr(emoji_reaction, "EMOJI_BINDINGS_PATH", tmp_path / "bindings.json")
    monkeypatch.setattr(emoji_reaction, "DEFAULT_TEXT_EMOJI_ID_BINDINGS", {})

    assert set_unicode_emoji_binding("😀", "101")
    assert not set_unicode_emoji_binding("😀", "101")
    assert set_unicode_emoji_binding("😡", "102")
    assert not set_unicode_emoji_binding("not-emoji", "103")
    assert emoji_binding_for("😀") == "101"
    assert emoji_bindings() == {"😀": "101", "😡": "102"}
    assert remove_unicode_emoji_binding("😀", "101")
    assert not remove_unicode_emoji_binding("😀", "101")
    assert emoji_bindings() == {"😡": "102"}


def test_unicode_emoji_binding_normalizes_variant_selector(tmp_path, monkeypatch) -> None:
    from bot.services import emoji_reaction

    monkeypatch.setattr(emoji_reaction, "EMOJI_BINDINGS_PATH", tmp_path / "bindings.json")
    monkeypatch.setattr(emoji_reaction, "DEFAULT_TEXT_EMOJI_ID_BINDINGS", {})

    assert set_unicode_emoji_binding("😈️", "210")
    assert set_unicode_emoji_binding("😈", "216")
    assert emoji_binding_for("😈️") == "216"
    assert emoji_bindings() == {"😈": "216"}


def test_validate_emoji_binding_rejects_non_single_emoji_and_non_numeric_id() -> None:
    assert validate_emoji_binding("😈", "0216") is not None
    assert validate_emoji_binding("😈😡", "210") is None
    assert validate_emoji_binding("👨‍👩‍👧‍👦", "210") is None
    assert validate_emoji_binding("A", "210") is None
    assert validate_emoji_binding("😈", "abc") is None


def test_parse_emoji_binding_action() -> None:
    bind = parse_emoji_binding_action([{"type": "text", "data": {"text": "😀️=101"}}])
    remove = parse_emoji_binding_action([{"type": "text", "data": {"text": "😀️!=101"}}])

    assert bind is not None
    assert bind.action == "bind"
    assert bind.emoji == "😀"
    assert bind.emoji_id == "101"
    assert remove is not None
    assert remove.action == "remove"
    assert remove.emoji == "😀"
    assert remove.emoji_id == "101"


def test_extract_unicode_emoji_id_from_binding(tmp_path, monkeypatch) -> None:
    from bot.services import emoji_reaction

    monkeypatch.setattr(emoji_reaction, "EMOJI_BINDINGS_PATH", tmp_path / "bindings.json")
    monkeypatch.setattr(emoji_reaction, "DEFAULT_TEXT_EMOJI_ID_BINDINGS", {})
    set_unicode_emoji_binding("😀", "101")

    assert extract_emoji_id([{"type": "text", "data": {"text": "😀"}}]) == "101"


def test_extract_unicode_emoji_id_from_decimal_codepoint(tmp_path, monkeypatch) -> None:
    from bot.services import emoji_reaction

    monkeypatch.setattr(emoji_reaction, "EMOJI_BINDINGS_PATH", tmp_path / "bindings.json")
    monkeypatch.setattr(emoji_reaction, "DEFAULT_TEXT_EMOJI_ID_BINDINGS", {})

    assert unicode_emoji_decimal_id("❌") == "10060"
    assert unicode_emoji_decimal_id("☑️") == "9745"
    assert unicode_emoji_decimal_id("😈️") == "128520"
    assert extract_emoji_id([{"type": "text", "data": {"text": "❌"}}]) == "10060"


def test_auto_unicode_binding_action_uses_decimal_codepoint(tmp_path, monkeypatch) -> None:
    from bot.services import emoji_reaction

    monkeypatch.setattr(emoji_reaction, "EMOJI_BINDINGS_PATH", tmp_path / "bindings.json")
    monkeypatch.setattr(emoji_reaction, "DEFAULT_TEXT_EMOJI_ID_BINDINGS", {})

    action = auto_unicode_binding_action([{"type": "text", "data": {"text": "❌"}}])

    assert action is not None
    assert action.action == "bind"
    assert action.emoji == "❌"
    assert action.emoji_id == "10060"


def test_emoji_bindings_are_sorted_by_unicode_codepoint(tmp_path, monkeypatch) -> None:
    from bot.services import emoji_reaction

    monkeypatch.setattr(emoji_reaction, "EMOJI_BINDINGS_PATH", tmp_path / "bindings.json")
    monkeypatch.setattr(emoji_reaction, "DEFAULT_TEXT_EMOJI_ID_BINDINGS", {})

    set_unicode_emoji_binding("😀", "128512")
    set_unicode_emoji_binding("❌", "10060")
    set_unicode_emoji_binding("☑️", "9745")

    assert list(emoji_bindings()) == ["☑", "❌", "😀"]
