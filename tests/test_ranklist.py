from pathlib import Path

from PIL import Image, ImageDraw

from bot.services import ranklist


def test_ranklist_draw_text_handles_emoji(tmp_path: Path) -> None:
    image = Image.new("RGB", (360, 90), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = ranklist._load_font(24, bold=True)

    ranklist._draw_text(draw, (12, 24), "蓝毛😡真可爱✨", font, (15, 23, 42))

    output = tmp_path / "emoji.png"
    image.save(output)
    assert output.stat().st_size > 0
