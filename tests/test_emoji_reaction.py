from bot.services.emoji_reaction import extract_emoji_id, is_single_super_emoji_message


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


def test_single_super_emoji_rejects_extra_text() -> None:
    message = [
        {"type": "mface", "data": {"emoji_id": "888"}},
        {"type": "text", "data": {"text": "贴一下"}},
    ]

    assert not is_single_super_emoji_message(message)
