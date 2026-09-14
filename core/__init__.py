# -*- coding: utf-8 -*-
"""Ядро проекта: транслитерация, конвертация в тодо бичиг и рендер картинки.

Тяжёлые импорты (torch, PIL) намеренно НЕ делаются здесь — они подтягиваются
лениво внутри pipeline.process(), чтобы бот стартовал быстро.
"""

from .pipeline import (  # noqa: F401
    MAX_INPUT_CHARS,
    SCRIPT_TITLES,
    TARGET_IMAGE,
    TARGET_TODO,
    TARGET_TRANSLIT,
    PipelineError,
    Result,
    process,
)
from .translit_todo import (  # noqa: F401
    detect_script,
    todo_to_translit,
    translit_to_todo,
)

__all__ = [
    "process",
    "Result",
    "PipelineError",
    "TARGET_TRANSLIT",
    "TARGET_TODO",
    "TARGET_IMAGE",
    "SCRIPT_TITLES",
    "MAX_INPUT_CHARS",
    "detect_script",
    "translit_to_todo",
    "todo_to_translit",
]
