from __future__ import annotations

import io
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont
from nonebot.log import logger

from bot.services.branding import app_name, env_template, env_text
from bot.services.problem_random import DIFFICULTIES
from bot.services.submission import get_rank_entries, get_rank_entry_for_user


RANKLIST_DIR = Path("data/submissions/ranklist")

WIDTH = 1180
MARGIN = 42
ROW_HEIGHT = 104
HEADER_HEIGHT = 132
FOOTER_HEIGHT = 44

BG = (241, 245, 249)
CARD = (255, 255, 255)
TEXT = (15, 23, 42)
MUTED = (100, 116, 139)
TEAL = (15, 118, 110)
BLUE = (37, 99, 235)
AMBER = (217, 119, 6)
BORDER = (226, 232, 240)
GREEN_BG = (236, 253, 245)

DIFFICULTY_COLORS: dict[str, tuple[int, int, int]] = {
    "check-in": (20, 184, 166),
    "easy": (34, 197, 94),
    "medium": (59, 130, 246),
    "hard": (245, 158, 11),
    "impossible": (239, 68, 68),
}


async def render_ranklist_image(user_names: dict[str, str] | None = None) -> Path:
    entries = _with_display_ranks(get_rank_entries())
    user_names = user_names or {}
    avatars = await _download_avatars([entry["user_id"] for entry in entries[:30]])

    height = max(360, HEADER_HEIGHT + len(entries[:30]) * ROW_HEIGHT + FOOTER_HEIGHT + MARGIN)
    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)

    font_title = _load_font(38, bold=True)
    font_subtitle = _load_font(18)
    font_rank = _load_font(30, bold=True)
    font_name = _load_font(24, bold=True)
    font_body = _load_font(18)
    font_small = _load_font(15)
    font_badge = _load_font(14, bold=True)

    draw.rounded_rectangle((24, 24, WIDTH - 24, height - 24), radius=24, fill=CARD)
    draw.rectangle((24, 24, WIDTH - 24, 30), fill=BLUE)
    draw.rectangle((24, 30, WIDTH - 24, 36), fill=AMBER)

    _draw_text(draw, (MARGIN, 54), _ranklist_title(), font_title, TEXT)
    _draw_text(draw, (MARGIN, 101), _ranklist_subtitle(), font_subtitle, MUTED)

    if not entries:
        _draw_text(draw, (MARGIN, 178), _ranklist_empty_text(), font_name, MUTED)
    else:
        y = HEADER_HEIGHT
        for rank, entry in enumerate(entries[:30], start=1):
            _draw_rank_row(
                image=image,
                draw=draw,
                y=y,
                rank=int(entry.get("display_rank", rank)),
                entry=entry,
                user_name=user_names.get(entry["user_id"], f"用户 {entry['user_id']}"),
                avatar=avatars.get(entry["user_id"]),
                fonts=(font_rank, font_name, font_body, font_small, font_badge),
            )
            y += ROW_HEIGHT

    footer = _ranklist_footer()
    _draw_text(draw, (MARGIN, height - 52), footer, font_small, MUTED)

    RANKLIST_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RANKLIST_DIR / "ranklist.png"
    image.save(output_path)
    return output_path


async def render_user_rank_image(user_id: str, user_names: dict[str, str] | None = None) -> Path:
    entry = get_rank_entry_for_user(user_id)
    user_names = user_names or {}
    entries = [entry] if entry is not None else []
    avatars = await _download_avatars([user_id] if entry is not None else [])

    height = 360
    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)

    font_title = _load_font(38, bold=True)
    font_subtitle = _load_font(18)
    font_rank = _load_font(30, bold=True)
    font_name = _load_font(24, bold=True)
    font_body = _load_font(18)
    font_small = _load_font(15)
    font_badge = _load_font(14, bold=True)

    draw.rounded_rectangle((24, 24, WIDTH - 24, height - 24), radius=24, fill=CARD)
    draw.rectangle((24, 24, WIDTH - 24, 30), fill=BLUE)
    draw.rectangle((24, 30, WIDTH - 24, 36), fill=AMBER)
    title_name = user_names.get(user_id, f"用户 {user_id}")
    title = _fit_text(
        draw,
        _user_rank_title(title_name, user_id),
        font_title,
        WIDTH - MARGIN * 2,
    )
    _draw_text(draw, (MARGIN, 54), title, font_title, TEXT)
    _draw_text(draw, (MARGIN, 101), _user_rank_subtitle(), font_subtitle, MUTED)

    if entries:
        all_entries = _with_display_ranks(get_rank_entries())
        rank = next(
            (int(item.get("display_rank", 1)) for item in all_entries if item["user_id"] == user_id),
            1,
        )
        _draw_rank_row(
            image=image,
            draw=draw,
            y=HEADER_HEIGHT,
            rank=rank,
            entry=entry,
            user_name=user_names.get(user_id, f"用户 {user_id}"),
            avatar=avatars.get(user_id),
            fonts=(font_rank, font_name, font_body, font_small, font_badge),
        )
    else:
        _draw_text(
            draw,
            (MARGIN, 178),
            _user_rank_empty_text(user_names.get(user_id, "用户"), user_id),
            font_name,
            MUTED,
        )

    RANKLIST_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RANKLIST_DIR / f"ranklist_{user_id}.png"
    image.save(output_path)
    return output_path


async def _download_avatars(user_ids: list[str]) -> dict[str, Image.Image]:
    avatars: dict[str, Image.Image] = {}
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for user_id in user_ids:
            try:
                response = await client.get(f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=100")
                response.raise_for_status()
                avatar = Image.open(io.BytesIO(response.content)).convert("RGBA")
                avatars[user_id] = _circle_avatar(avatar.resize((72, 72), Image.LANCZOS))
            except Exception:
                logger.warning(f"Failed to download QQ avatar for {user_id}")
    return avatars


def _draw_rank_row(
    *,
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    y: int,
    rank: int,
    entry: dict[str, Any],
    user_name: str,
    avatar: Image.Image | None,
    fonts: tuple[
        ImageFont.FreeTypeFont,
        ImageFont.FreeTypeFont,
        ImageFont.FreeTypeFont,
        ImageFont.FreeTypeFont,
        ImageFont.FreeTypeFont,
    ],
) -> None:
    font_rank, font_name, font_body, font_small, font_badge = fonts
    x1 = MARGIN
    x2 = WIDTH - MARGIN
    row_fill = (248, 250, 252) if rank % 2 else (255, 255, 255)
    draw.rounded_rectangle((x1, y + 8, x2, y + ROW_HEIGHT - 8), radius=14, fill=row_fill, outline=BORDER)

    medal = {1: (245, 158, 11), 2: (148, 163, 184), 3: (180, 83, 9)}.get(rank, TEAL)
    draw.text((x1 + 24, y + 36), f"#{rank}", font=font_rank, fill=medal)

    avatar_x = x1 + 108
    avatar_y = y + 18
    if avatar is None:
        draw.ellipse(
            (avatar_x, avatar_y, avatar_x + 72, avatar_y + 72),
            fill=GREEN_BG,
            outline=(153, 246, 228),
            width=2,
        )
        draw.text((avatar_x + 22, avatar_y + 22), "U", font=font_body, fill=TEAL)
    else:
        image.paste(avatar, (avatar_x, avatar_y), avatar)

    user_id = entry["user_id"]
    rating = float(entry["rating"])
    total_solved = int(entry["total_solved"])
    display_name = _fit_text(draw, user_name, font_name, 260)
    _draw_text(draw, (avatar_x + 92, y + 19), display_name, font_name, TEXT)
    draw.text((avatar_x + 92, y + 50), f"uid {user_id}", font=font_small, fill=MUTED)
    ratings = entry.get("ratings") or {}
    cf_rating = float(ratings.get("cf", rating))
    at_rating = float(ratings.get("at", 0.0))
    draw.text(
        (avatar_x + 92, y + 72),
        f"CF {cf_rating:.2f} · AT {at_rating:.2f} · "
        f"Solved {total_solved}",
        font=font_body,
        fill=MUTED,
    )

    badge_x = WIDTH - MARGIN - 430
    badge_y = y + 28
    counts = entry["difficulty_solved_counts"]
    for key in DIFFICULTIES:
        value = int(counts.get(key, 0))
        label = _difficulty_label(key)
        color = DIFFICULTY_COLORS[key]
        text = f"{label} {value}"
        text_w = int(draw.textlength(text, font=font_badge))
        width = max(68, text_w + 18)
        draw.rounded_rectangle(
            (badge_x, badge_y, badge_x + width, badge_y + 30),
            radius=15,
            fill=_tint(color),
            outline=color,
        )
        draw.text((badge_x + 9, badge_y + 6), text, font=font_badge, fill=color)
        badge_x += width + 8


def _circle_avatar(avatar: Image.Image) -> Image.Image:
    mask = Image.new("L", avatar.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, avatar.size[0] - 1, avatar.size[1] - 1), fill=255)
    result = Image.new("RGBA", avatar.size, (0, 0, 0, 0))
    result.paste(avatar, (0, 0), mask)
    return result


def _with_display_ranks(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    last_key: str | None = None
    current_rank = 0
    for index, entry in enumerate(entries, start=1):
        key = str(entry.get("solved_rank_key") or "")
        if key != last_key:
            current_rank = index
            last_key = key
        new_entry = dict(entry)
        new_entry["display_rank"] = current_rank
        ranked.append(new_entry)
    return ranked


def _difficulty_label(key: str) -> str:
    return {
        "check-in": "CI",
        "easy": "E",
        "medium": "M",
        "hard": "H",
        "impossible": "IMP",
    }[key]


def _ranklist_title() -> str:
    return env_template("ALGOQUEST_RANKLIST_TITLE", "{app_name} Ranklist", app_name=app_name())


def _ranklist_subtitle() -> str:
    return env_text("ALGOQUEST_RANKLIST_SUBTITLE", "Ranked by solved vector: IMP/H/M/E/CI.")


def _ranklist_empty_text() -> str:
    return env_text("ALGOQUEST_RANKLIST_EMPTY_TEXT", "暂无成功解题记录。")


def _ranklist_footer() -> str:
    return env_text("ALGOQUEST_RANKLIST_FOOTER", "Same solved vector shares rank; rating is shown as reference only.")


def _user_rank_title(user_name: str, user_id: str) -> str:
    return env_template(
        "ALGOQUEST_USER_RANK_TITLE",
        "{user_name}'s {app_name} Card",
        app_name=app_name(),
        user_name=user_name,
        user_id=user_id,
    )


def _user_rank_subtitle() -> str:
    return env_text("ALGOQUEST_USER_RANK_SUBTITLE", "Only your own accepted-solution record is shown.")


def _user_rank_empty_text(user_name: str, user_id: str) -> str:
    return env_template(
        "ALGOQUEST_USER_RANK_EMPTY_TEXT",
        "{user_name} · uid {user_id} 暂无成功解题记录。",
        app_name=app_name(),
        user_name=user_name,
        user_id=user_id,
    )

def _tint(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(int(component + (255 - component) * 0.88) for component in color)


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> str:
    if _text_length(draw, text, font) <= max_width:
        return text
    ellipsis = "..."
    result = text
    while result and _text_length(draw, result + ellipsis, font) > max_width:
        result = result[:-1]
    return (result or text[:1]) + ellipsis


def _draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    base_image = getattr(draw, "_image", None)
    x, y = xy
    for chunk, chunk_font in _font_chunks(text, font):
        if len(chunk) == 1 and _is_emoji_like(chunk) and isinstance(base_image, Image.Image):
            pasted_width = _paste_emoji(base_image, chunk, x, y, font)
            if pasted_width:
                x += pasted_width
                continue
        draw.text((x, y), chunk, font=chunk_font, fill=fill)
        x += int(round(draw.textlength(chunk, font=chunk_font)))


def _text_length(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> float:
    return sum(draw.textlength(chunk, font=chunk_font) for chunk, chunk_font in _font_chunks(text, font))


def _font_chunks(text: str, font: ImageFont.FreeTypeFont) -> list[tuple[str, ImageFont.FreeTypeFont]]:
    chunks: list[tuple[str, ImageFont.FreeTypeFont]] = []
    current_text = ""
    current_font = font
    for char in text:
        char_font = _font_for_char(char, font)
        if current_text and char_font is not current_font:
            chunks.append((current_text, current_font))
            current_text = char
            current_font = char_font
        else:
            current_text += char
            current_font = char_font
    if current_text:
        chunks.append((current_text, current_font))
    return chunks


def _font_for_char(char: str, font: ImageFont.FreeTypeFont) -> ImageFont.FreeTypeFont:
    if _is_emoji_like(char):
        fallback = _load_fallback_font(getattr(font, "size", 18))
        return fallback or font
    if _font_has_glyph(font, char):
        return font
    fallback = _load_fallback_font(getattr(font, "size", 18))
    if fallback is not None and _font_has_glyph(fallback, char):
        return fallback
    return font


def _font_has_glyph(font: ImageFont.FreeTypeFont, char: str) -> bool:
    if char.isspace() or unicodedata.category(char).startswith("C"):
        return True
    try:
        return font.getmask(char).getbbox() is not None
    except Exception:
        return False


def _is_emoji_like(char: str) -> bool:
    if not char:
        return False
    codepoint = ord(char)
    if 0x1F000 <= codepoint <= 0x1FAFF:
        return True
    if 0x2600 <= codepoint <= 0x27BF:
        return True
    return "EMOJI" in unicodedata.name(char, "")


def _paste_emoji(
    base_image: Image.Image,
    char: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
) -> int:
    emoji_font = _load_color_emoji_font()
    if emoji_font is None:
        return 0

    bbox = emoji_font.getbbox(char)
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    canvas = Image.new("RGBA", (width + 8, height + 8), (255, 255, 255, 0))
    canvas_draw = ImageDraw.Draw(canvas)
    canvas_draw.text((4 - bbox[0], 4 - bbox[1]), char, font=emoji_font, embedded_color=True)

    font_bbox = font.getbbox("Hg")
    target_height = max(14, int((font_bbox[3] - font_bbox[1]) * 1.08))
    ratio = target_height / canvas.height
    target_width = max(1, int(canvas.width * ratio))
    resized = canvas.resize((target_width, target_height), Image.LANCZOS)
    baseline_offset = max(0, int((font_bbox[3] - font_bbox[1] - target_height) / 2))
    paste_y = y + baseline_offset + 1
    base_image.paste(resized, (int(x), int(paste_y)), resized)
    return target_width + 2


@lru_cache(maxsize=1)
def _load_color_emoji_font() -> ImageFont.FreeTypeFont | None:
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf",
        "/mnt/c/Windows/Fonts/seguiemj.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if not path.exists():
            continue
        for size in (109, 128, 136, 160):
            try:
                return ImageFont.truetype(str(path), size=size, encoding="utf-8")
            except OSError:
                continue
    return None


@lru_cache(maxsize=32)
def _load_fallback_font(size: int) -> ImageFont.FreeTypeFont | None:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf",
        "/mnt/c/Windows/Fonts/seguiemj.ttf",
        "/mnt/c/Windows/Fonts/seguisym.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if not path.exists():
            continue
        try:
            return ImageFont.truetype(str(path), size=size, encoding="utf-8")
        except OSError:
            continue
    return None


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        [
            "/mnt/c/Windows/Fonts/msyhbd.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            "/mnt/c/Windows/Fonts/msyh.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()
