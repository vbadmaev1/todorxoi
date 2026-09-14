# -*- coding: utf-8 -*-
"""Сборка текста ответа: результат + «вход распознан как…» + время работы."""

from html import escape

from core import SCRIPT_TITLES, Result

from . import texts

TARGET_ICONS = {"translit": "🔤", "todo": "ᡐ", "image": "🖼"}

CAPTION_LIMIT = 1024


def fmt_ms(ms: float) -> str:
    """412.7 -> «413 мс», 1234.5 -> «1,23 с» — читается легче, чем голые ms."""
    if ms < 1000:
        return f"{ms:.0f} мс"
    return f"{ms / 1000:.2f} с".replace(".", ",")


def timing_line(res: Result) -> str:
    parts = [f"⏱ {fmt_ms(res.elapsed_ms)}"]
    steps = [f"{name} {fmt_ms(value)}" for name, value in res.steps_ms.items()]
    if steps:
        parts.append(" · ".join(steps))
    line = " · ".join(parts)
    if res.stats:
        d, m = res.stats.get("dict", 0), res.stats.get("model", 0)
        if d or m:
            line += f"\n📚 из словаря: {d} · предсказано моделью: {m}"
    return line


def _header(res: Result) -> str:
    icon = TARGET_ICONS.get(res.target, "•")
    title = texts.MODE_TITLES.get(res.target, res.target).split(" ", 1)[-1]
    script = SCRIPT_TITLES.get(res.source_script, res.source_script)
    return f"{icon} <b>{title}</b>\n<i>вход: {script}</i>"


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
    blocks = [_header(res)]
    if res.translit:
        blocks.append(f"Транслитерация:\n<code>{escape(res.translit)}</code>")
    if not res.shaping_ok:
        from core.todo_image import SHAPING_WARNING

        blocks.append(SHAPING_WARNING)
    blocks.append(timing_line(res))
    return "\n\n".join(blocks)
