# -*- coding: utf-8 -*-
"""
pipeline.py — единая точка входа для бота: «дай текст и скажи, что нужно
на выходе». Здесь же замеряется время работы каждого шага.

Три сценария (ровно те, что в ТЗ бота):
  1. TARGET_TRANSLIT — калмыцкая кириллица -> транслитерация на латинице
  2. TARGET_TODO     — кириллица / транслитерация -> тодо бичиг (юникод)
  3. TARGET_IMAGE    — кириллица / транслитерация / тодо бичиг -> картинка

Тип входного текста определяется автоматически (detect_script), так что
пользователю не нужно ничего указывать руками.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

from .translit_todo import (
    SCRIPT_CYRILLIC,
    SCRIPT_TODO,
    SCRIPT_TRANSLIT,
    SCRIPT_UNKNOWN,
    detect_script,
    todo_to_translit,
    translit_to_todo,
)

TARGET_TRANSLIT = "translit"
TARGET_TODO = "todo"
TARGET_IMAGE = "image"

MAX_INPUT_CHARS = 1000

FONT_SIZES = {"small": 44, "medium": 64, "large": 96}
DEFAULT_FONT_SIZE = "medium"


@dataclass
class ImageOptions:
    """Как рисовать картинку. У каждого пользователя свои — хранятся в БД,
    меняются командой /settings."""

    fg: str = "black"
    bg: str = "white"
    size: str = DEFAULT_FONT_SIZE

    @property
    def font_size(self) -> int:
        return FONT_SIZES.get(self.size, FONT_SIZES[DEFAULT_FONT_SIZE])

    @property
    def max_column_height(self) -> int:
        # высота столбца соразмерна кеглю, иначе крупный шрифт ломает
        # перенос: на строку влезает слишком мало букв
        return int(os.environ.get("MAX_COLUMN_HEIGHT", "900")) * self.font_size // 64

    def as_dict(self) -> dict:
        return {"fg": self.fg, "bg": self.bg, "size": self.size}


class PipelineError(Exception):
    """Ошибка, текст которой можно показать пользователю как есть."""


@dataclass
class Result:
    target: str
    source_text: str
    source_script: str
    translit: Optional[str] = None
    todo: Optional[str] = None
    image: Optional[object] = None  # io.BytesIO с PNG
    image_size: Optional[Tuple[int, int]] = None
    # False — картинка нарисована без шейпинга: буквы не соединены
    shaping_ok: bool = True
    # прозрачный фон: такую картинку надо слать документом, не фото
    transparent: bool = False
    # цвета текста и фона совпали, пришлось откатиться на чёрное по белому
    color_fallback: bool = False
    elapsed_ms: float = 0.0
    steps_ms: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)

    @property
    def text_output(self) -> str:
        """Главный текстовый результат — то, что пойдёт в БД и в ответ."""
        if self.target == TARGET_TRANSLIT:
            return self.translit or ""
        return self.todo or ""


def _check_input(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise PipelineError("Пустой текст — пришлите слово или предложение.")
    if len(text) > MAX_INPUT_CHARS:
        raise PipelineError(
            f"Слишком длинный текст: {len(text)} символов, "
            f"максимум {MAX_INPUT_CHARS}."
        )
    return text


def _to_translit(text: str, script: str, res: Result) -> str:
    """Приводит любой вход к транслитерации проекта."""
    if script == SCRIPT_TRANSLIT:
        return text
    if script == SCRIPT_TODO:
        t0 = time.perf_counter()
        out = todo_to_translit(text)
        res.steps_ms["todo→translit"] = (time.perf_counter() - t0) * 1000
        return out
    if script == SCRIPT_CYRILLIC:
        # импорт здесь, а не наверху: torch тянется только когда реально нужен
        from .transliterate import transliterate_with_stats

        t0 = time.perf_counter()
        out, stats = transliterate_with_stats(text)
        res.steps_ms["модель"] = (time.perf_counter() - t0) * 1000
        res.stats.update(stats)
        return out
    raise PipelineError(
        "Не удалось распознать текст. Пришлите калмыцкую кириллицу, "
        "транслитерацию на латинице или тодо бичиг."
    )


def process(text: str, target: str, options: Optional[ImageOptions] = None) -> Result:
    """Основная функция. Синхронная и не быстрая (модель) — в боте её
    нужно звать через asyncio.to_thread.

    options — настройки картинки конкретного пользователя; для режимов
    транслитерации и тодо бичиг не используются."""
    opts = options or ImageOptions()
    text = _check_input(text)
    script = detect_script(text)
    if script == SCRIPT_UNKNOWN:
        raise PipelineError(
            "Не удалось распознать текст. Пришлите калмыцкую кириллицу, "
            "транслитерацию на латинице или тодо бичиг."
        )

    res = Result(target=target, source_text=text, source_script=script)
    started = time.perf_counter()

    if target == TARGET_TRANSLIT:
        res.translit = _to_translit(text, script, res)

    elif target == TARGET_TODO:
        if script == SCRIPT_TODO:
            raise PipelineError(
                "Этот текст уже записан тодо бичиг. Если нужна картинка — "
                "используйте /image."
            )
        res.translit = _to_translit(text, script, res)
        t0 = time.perf_counter()
        res.todo = translit_to_todo(res.translit)
        res.steps_ms["translit→тодо"] = (time.perf_counter() - t0) * 1000

    elif target == TARGET_IMAGE:
        from .todo_image import (
            SHAPING_OK,
            ShapingUnavailable,
            render_todo_bytes,
            require_shaping,
        )

        try:
            require_shaping()
        except ShapingUnavailable as exc:
            # сюда попадаем только при STRICT_SHAPING=1
            raise PipelineError(
                "Рендер картинок отключён: окружение не умеет соединять "
                "буквы тодо бичиг (STRICT_SHAPING=1). Подробности — в логах."
            ) from exc
        # без движка раскладки картинку всё равно рисуем, но честно помечаем
        # результат, чтобы никто не принял несоединённые буквы за письмо
        res.shaping_ok = SHAPING_OK

        if script == SCRIPT_TODO:
            res.todo = text
        else:
            res.translit = _to_translit(text, script, res)
            t0 = time.perf_counter()
            res.todo = translit_to_todo(res.translit)
            res.steps_ms["translit→тодо"] = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        res.image, res.image_size, meta = render_todo_bytes(
            res.todo,
            font_size=opts.font_size,
            max_column_height=opts.max_column_height,
            fg=opts.fg,
            bg=opts.bg,
        )
        res.transparent = meta["transparent"]
        res.color_fallback = meta["color_fallback"]
        res.steps_ms["рендер"] = (time.perf_counter() - t0) * 1000

    else:
        raise PipelineError(f"Неизвестная операция: {target}")

    res.elapsed_ms = (time.perf_counter() - started) * 1000
    return res


SCRIPT_TITLES = {
    SCRIPT_CYRILLIC: "калмыцкая кириллица",
    SCRIPT_TRANSLIT: "транслитерация (латиница)",
    SCRIPT_TODO: "тодо бичиг",
    SCRIPT_UNKNOWN: "не определено",
}
