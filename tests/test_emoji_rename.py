import pytest
from nonebot.adapters.onebot.v11 import Message, MessageSegment

from bot.services.emoji_rename import quoted_media, renamed_media


def test_image_preview_is_renamed_without_downloading_or_changing_source(tmp_path):
    original = MessageSegment("image", {"url": "https://cdn.example/image.gif?token=private", "file": "cache-id", "summary": "[动画表情]"})
    renamed = renamed_media(original, "1")
    assert renamed.type == "image"
    assert renamed.data == {"file": original.data["url"], "summary": "1", "sub_type": 1}
    assert original.data["summary"] == "[动画表情]"
    assert not list(tmp_path.iterdir())


def test_market_sticker_can_reuse_its_image_url_or_native_metadata():
    media = MessageSegment("mface", {"emoji_id": "id", "emoji_package_id": "pkg", "key": "key", "url": "https://cdn.example/a.gif"})
    assert renamed_media(media, "测试").type == "image"
    del media.data["url"]
    result = renamed_media(media, "测试")
    assert result.type == "mface" and result.data["summary"] == "测试"
    assert result.data["emoji_package_id"] == "pkg"


@pytest.mark.parametrize("name", ["", "\n", "a\nb", "x" * 81, "x\x00"])
def test_invalid_preview_names_are_rejected(name):
    with pytest.raises(ValueError):
        renamed_media(MessageSegment("image", {"file": "id"}), name)


def test_ambiguous_media_and_missing_file_fail_explicitly():
    with pytest.raises(ValueError):
        quoted_media(Message([MessageSegment.image("a"), MessageSegment.image("b")]))
    assert quoted_media(Message("普通文字")) is None
    with pytest.raises(ValueError):
        renamed_media(MessageSegment("mface", {"emoji_id": "id"}), "1")
