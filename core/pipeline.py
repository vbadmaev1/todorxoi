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


def process(text: str, target: str) -> Result:
    """Основная функция. Синхронная и не быстрая (модель) — в боте её
    нужно звать через asyncio.to_thread."""
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
        from .todo_image import ShapingUnavailable, render_todo_bytes, require_shaping

        try:
            require_shaping()
        except ShapingUnavailable as exc:
            # окружение не умеет соединять буквы — лучше честно сказать об
            # этом, чем прислать картинку, которую невозможно прочитать
            raise PipelineError(
                "Картинку сейчас не собрать: окружение не умеет соединять "
                "буквы тодо бичиг. Подробности — в логах бота."
            ) from exc

        if script == SCRIPT_TODO:
            res.todo = text
        else:
            res.translit = _to_translit(text, script, res)
            t0 = time.perf_counter()
            res.todo = translit_to_todo(res.translit)
            res.steps_ms["translit→тодо"] = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        res.image, res.image_size = render_todo_bytes(
            res.todo,
            font_size=int(os.environ.get("FONT_SIZE", "64")),
            max_column_height=int(os.environ.get("MAX_COLUMN_HEIGHT", "900")),
        )
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
