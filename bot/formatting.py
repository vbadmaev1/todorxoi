# -*- coding: utf-8 -*-
"""Сборка текста ответа: результат + «вход распознан как…» + время работы."""

from html import escape

from core import Result

from . import texts

TARGET_ICONS = {"translit": "🔤", "todo": "ᡐ", "image": "🖼"}

CAPTION_LIMIT = 1024


def fmt_ms(ms: float) -> str:
    """412.7 -> «413 мс», 1234.5 -> «1,23 с» — читается легче, чем голые ms."""
    if ms < 1000:
        return f"{ms:.0f} мс"
    return f"{ms / 1000:.2f} с".replace(".", ",")


def timing_line(res: Result) -> str:
    """Только общее время. Разбивка по шагам и статистика «сколько слов из
    словаря» — внутренняя кухня: она есть в БД для анализа, но человеку в
    чате не нужна."""
    return f"⏱ {fmt_ms(res.elapsed_ms)}"


def _header(res: Result) -> str:
    icon = TARGET_ICONS.get(res.target, "•")
    title = texts.MODE_TITLES.get(res.target, res.target).split(" ", 1)[-1]
    return f"{icon} <b>{title}</b>"


def render_result(res: Result) -> str:
    """Текст ответа для режимов «транслитерация» и «тодо бичиг»."""
    blocks = [_header(res)]

    if res.target == "translit":
        blocks.append(f"<code>{escape(res.translit or '')}</code>")
    else:
        if res.translit:
            blocks.append(
                f"Транслитерация:\n<code>{escape(res.translit)}</code>"
            )
        blocks.append(f"Тодо бичиг:\n<code>{escape(res.todo or '')}</code>")

    blocks.append(timing_line(res))
    return "\n\n".join(blocks)


def render_caption(res: Result) -> str:
    """Подпись под картинкой — то же самое, но с оглядкой на лимит в 1024."""
    text = render_result(res) if res.target != "image" else _image_caption(res)
    if len(text) <= CAPTION_LIMIT:
        return text
    return text[: CAPTION_LIMIT - 1] + "…"


def _image_caption(res: Result) -> str:
    # под картинкой транслитерацию не дублируем: кому она нужна, тот
    # спросит её отдельно командой /translit
    blocks = [_header(res)]
    if not res.shaping_ok:
        from core.todo_image import SHAPING_WARNING

        blocks.append(SHAPING_WARNING)
    if res.color_fallback:
        blocks.append(texts.COLOR_FALLBACK_NOTE)
    blocks.append(timing_line(res))
    return "\n\n".join(blocks)
