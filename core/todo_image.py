# -*- coding: utf-8 -*-
"""
todo_image.py — рендер транслитерации (или готового текста тодо бичиг) в
картинку с настоящим вертикальным письмом.

Как устроено вертикальное письмо:
  1. Каждая "логическая строка" рисуется ГОРИЗОНТАЛЬНО как обычно (шрифт
     не поддерживает вертикальный режим сам по себе).
  2. Картинка строки поворачивается на 90° ПО ЧАСОВОЙ стрелке
     (`rotate(-90)` в PIL): левый край становится верхним, чтение
     слева-направо превращается в чтение сверху-вниз.
  3. Если строка не помещается по высоте (после поворота — это высота
     столбца) — переносим по словам на несколько под-строк/столбцов.
  4. Получившиеся столбцы выстраиваются СЛЕВА НАПРАВО.

Перенос — только по пробелу. Символ границы суффикса (узкий
неразрывный пробел, \\u202f) переносить нельзя.

Отличия от исходного скрипта: путь к шрифту берётся из переменной
окружения FONT_PATH (по умолчанию assets/MongolianUniversalWhite.ttf),
добавлены поля вокруг картинки и функция render_todo_bytes(), которая
отдаёт PNG в память — так его удобно сразу слать в Telegram.
"""

import io
import os
import warnings

from PIL import Image, ImageDraw, ImageFont, features

from .translit_todo import translit_to_todo

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_FONT = os.path.join(
    os.path.dirname(_HERE), "assets", "MongolianUniversalWhite.ttf"
)
DEFAULT_TODO_FONT = os.environ.get("FONT_PATH", _DEFAULT_FONT)

_NNBSP = " "


# =============================================================================
# ГЛАВНОЕ ТРЕБОВАНИЕ К ОКРУЖЕНИЮ: Pillow, собранный с Raqm
# =============================================================================
#
# Монгольское письмо (и тодо бичиг вместе с ним) — курсивное: буква имеет
# разные формы в начале, середине и конце слова, и соседние буквы сливаются
# в один вертикальный стержень. Выбор нужной формы делает не шрифт сам по
# себе, а движок раскладки текста — HarfBuzz, к которому Pillow ходит через
# библиотеку Raqm.
#
# Если Raqm в сборке Pillow нет, Pillow МОЛЧА откатывается на примитивную
# раскладку: каждая буква рисуется в изолированной форме, буквы не
# соединяются. Картинка получается похожей на текст, но читать её нельзя —
# это и есть «несвязная хрень». Молча — то есть без единой ошибки, поэтому
# проверяем сами и падаем с внятным сообщением вместо того, чтобы отправить
# пользователю заведомо неправильную картинку.
#
# Проверить в своём окружении:
#     python -c "from PIL import features; print(features.check('raqm'))"
#
# Чаще всего Raqm отсутствует в Pillow из conda/системного пакета. Лечится
# установкой Pillow из PyPI: pip install -U --force-reinstall Pillow

HAS_RAQM = features.check("raqm")

_LAYOUT = (
    ImageFont.Layout.RAQM
    if HAS_RAQM and hasattr(ImageFont, "Layout")
    else getattr(getattr(ImageFont, "Layout", None), "BASIC", None)
)

# аварийный клапан: ALLOW_UNSHAPED=1 разрешает рисовать без Raqm
ALLOW_UNSHAPED = os.environ.get("ALLOW_UNSHAPED", "").lower() in {
    "1", "true", "yes", "on", "да",
}

_NO_RAQM_MESSAGE = (
    "Pillow собран без Raqm — буквы тодо бичиг не будут соединяться "
    "(каждая нарисуется в изолированной форме, читать такую картинку "
    "нельзя). Установите Pillow из PyPI: "
    "pip install -U --force-reinstall Pillow — и проверьте: "
    "python -c \"from PIL import features; print(features.check('raqm'))\""
)


class ShapingUnavailable(RuntimeError):
    """Raqm недоступен — рисовать тодо бичиг нечем."""


def require_shaping() -> None:
    if HAS_RAQM or ALLOW_UNSHAPED:
        return
    raise ShapingUnavailable(_NO_RAQM_MESSAGE)


def shaping_status() -> str:
    if HAS_RAQM:
        return f"Raqm есть (harfbuzz {features.version('harfbuzz')}) — буквы соединяются"
    if ALLOW_UNSHAPED:
        return "Raqm НЕТ, но ALLOW_UNSHAPED=1 — картинки будут несвязными"
    return "Raqm НЕТ — рендер картинок работать не будет"


# =============================================================================
# Цвета — по словам, RU и EN, с прозрачным фоном отдельным вариантом.
# =============================================================================

BASE_COLORS = {
    "black": (0, 0, 0, 255), "чёрный": (0, 0, 0, 255), "черный": (0, 0, 0, 255),
    "white": (255, 255, 255, 255), "белый": (255, 255, 255, 255),
    "red": (214, 39, 40, 255), "красный": (214, 39, 40, 255),
    "green": (44, 160, 44, 255), "зелёный": (44, 160, 44, 255), "зеленый": (44, 160, 44, 255),
    "blue": (31, 119, 180, 255), "синий": (31, 119, 180, 255),
    "yellow": (230, 200, 0, 255), "жёлтый": (230, 200, 0, 255), "желтый": (230, 200, 0, 255),
    "orange": (255, 127, 14, 255), "оранжевый": (255, 127, 14, 255),
    "purple": (148, 103, 189, 255), "фиолетовый": (148, 103, 189, 255),
    "gray": (128, 128, 128, 255), "grey": (128, 128, 128, 255), "серый": (128, 128, 128, 255),
    "brown": (140, 86, 75, 255), "коричневый": (140, 86, 75, 255),
    "pink": (227, 119, 194, 255), "розовый": (227, 119, 194, 255),
    "cyan": (23, 190, 207, 255), "голубой": (23, 190, 207, 255),
    "gold": (212, 175, 55, 255), "золотой": (212, 175, 55, 255),
    "cream": (247, 242, 230, 255), "кремовый": (247, 242, 230, 255),
}

_TRANSPARENT_NAMES = {"transparent", "прозрачный", "none", "нет"}

DEFAULT_FG = BASE_COLORS["black"]
DEFAULT_BG = BASE_COLORS["white"]


def resolve_color(name, fallback, allow_transparent=False):
    """Название цвета (по-русски или по-английски) -> RGBA. Если имя не
    из базового набора — берём fallback."""
    if name is None:
        return fallback
    if not isinstance(name, str):
        return name  # уже готовый tuple/цвет — пропускаем как есть
    key = name.strip().lower()
    if allow_transparent and key in _TRANSPARENT_NAMES:
        return (0, 0, 0, 0)
    if key in BASE_COLORS:
        return BASE_COLORS[key]
    warnings.warn(f"цвет «{name}» не из базового набора, беру цвет по умолчанию")
    return fallback


def _resolve_fg_bg(fg, bg):
    fg_rgba = resolve_color(fg, DEFAULT_FG)
    bg_rgba = resolve_color(bg, DEFAULT_BG, allow_transparent=True)
    if fg_rgba == bg_rgba:
        # одинаковые цвета -> текста не видно, откатываемся на чёрное-на-белом
        return DEFAULT_FG, DEFAULT_BG
    return fg_rgba, bg_rgba


def _load_font(font_path, font_size):
    if font_path is None:
        try:
            return ImageFont.load_default(size=font_size)
        except TypeError:
            # старые версии Pillow не умеют load_default(size=...)
            return ImageFont.load_default()
    # layout_engine указываем явно: без него Pillow сам решает, чем рисовать,
    # и при отсутствии Raqm тихо берёт примитивную раскладку
    if _LAYOUT is not None:
        return ImageFont.truetype(font_path, font_size, layout_engine=_LAYOUT)
    return ImageFont.truetype(font_path, font_size)


def _text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox


def _wrap_line(line, font, max_column_height, draw):
    """Разбивает одну строку тодо-бичиг текста на под-строки так, чтобы
    каждая под-строка при горизонтальном рендере не превышала по ширине
    max_column_height (это и есть будущая высота столбца после поворота).
    Перенос — по обычному пробелу; \\u202f внутри "слова" не трогаем."""
    words = line.split(" ")
    sublines = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        w, _, _ = _text_size(draw, candidate, font)
        if w <= max_column_height or not current:
            current = candidate
        else:
            sublines.append(current)
            current = word
    if current:
        sublines.append(current)
    return sublines


def _render_column(subline, font, draw_probe, fg, bg, pad=6):
    """Рисует одну под-строку горизонтально, затем поворачивает на 90°
    по часовой — получается один готовый вертикальный столбец."""
    w, h, bbox = _text_size(draw_probe, subline, font)
    strip = Image.new("RGBA", (w + pad * 2, h + pad * 2), bg)
    ImageDraw.Draw(strip).text(
        (pad - bbox[0], pad - bbox[1]), subline, font=font, fill=fg
    )
    return strip.rotate(-90, expand=True)


def render_todo_paragraph(
    lines,
    out_path=None,
    font_size=64,
    max_column_height=900,
    column_gap=14,
    line_gap=40,
    margin=36,
    fg="black",
    bg="white",
    font_path=DEFAULT_TODO_FONT,
):
    """
    lines    — текст УЖЕ в юникоде тодо бичиг: одна строка (можно с \\n
               внутри) или список строк.
    fg, bg   — название цвета словом (см. BASE_COLORS), не hex-код.
               bg="transparent"/"прозрачный" — пустой фон.
    out_path — если задан, картинка ещё и сохраняется на диск.
    Возвращает объект PIL.Image.
    """
    require_shaping()

    if isinstance(lines, str):
        lines = lines.split("\n")

    fg, bg = _resolve_fg_bg(fg, bg)
    font = _load_font(font_path, font_size)
    probe = Image.new("RGBA", (10, 10))
    draw_probe = ImageDraw.Draw(probe)

    columns = []  # (image, is_first_subline_of_its_logical_line)
    for line in lines:
        line = line.strip("\n")
        if not line.strip():
            continue
        sublines = _wrap_line(line, font, max_column_height, draw_probe)
        for i, subline in enumerate(sublines):
            col = _render_column(subline, font, draw_probe, fg, bg)
            columns.append((col, i == 0))

    if not columns:
        raise ValueError("нечего рендерить — пустой текст")

    total_width = sum(c.width for c, _ in columns)
    total_width += column_gap * (len(columns) - 1)
    total_width += (line_gap - column_gap) * sum(
        1 for i, (_, is_new) in enumerate(columns) if is_new and i > 0
    )
    max_height = max(c.height for c, _ in columns)

    canvas = Image.new(
        "RGBA", (total_width + margin * 2, max_height + margin * 2), bg
    )
    x = margin
    for i, (col, is_new_line) in enumerate(columns):
        if i > 0:
            x += line_gap if is_new_line else column_gap
        canvas.paste(col, (x, margin), col)
        x += col.width

    if out_path:
        canvas.save(out_path)
    return canvas


def render_todo_image(text, out_path=None, **kwargs):
    """
    text — транслитерация проекта (не тодо бичиг, не кириллица). Можно
    несколько строк через \\n или списком — конвертирует каждую и зовёт
    render_todo_paragraph.
    """
    lines = text.split("\n") if isinstance(text, str) else text
    todo_lines = [translit_to_todo(line) for line in lines]
    return render_todo_paragraph(todo_lines, out_path=out_path, **kwargs)


MAX_SIDE = 2600  # у Telegram сумма сторон фото ограничена, да и смысла нет


def render_todo_bytes(todo_text, max_side=MAX_SIDE, **kwargs):
    """Готовый текст тодо бичиг -> PNG в памяти (io.BytesIO).
    Именно этим пользуется бот: файл на диск не пишется.

    Возвращает (BytesIO, (ширина, высота)). Слишком большая картинка
    (длинный текст = много столбцов) ужимается по большей стороне."""
    img = render_todo_paragraph(todo_text, out_path=None, **kwargs)
    if max_side and max(img.size) > max_side:
        scale = max_side / max(img.size)
        img = img.resize(
            (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
            Image.LANCZOS,
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf, img.size


if __name__ == "__main__":
    print("Раскладка текста:", shaping_status())
    sentence = "xalimaq ulus ger-yēn naran üde xalīlγaǰi baridaq"
    render_todo_image(sentence, out_path="demo_sentence.png", max_column_height=260)
    print("сохранено: demo_sentence.png")

    paragraph = [
        "ene yertünci dü mini oron",
        "eberē amidural yin ecen bi",
        "külüg yin mini kacar-yēn tatači bayikuši bi",
        "küsel yēn dakāqd sanā bēn cingnēd",
    ]
    render_todo_paragraph(
        [translit_to_todo(line) for line in paragraph],
        out_path="demo_paragraph.png", max_column_height=500,
    )
    print("сохранено: demo_paragraph.png")
