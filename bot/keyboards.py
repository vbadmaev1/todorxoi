# -*- coding: utf-8 -*-
"""Клавиатуры: постоянное меню режимов внизу и inline-кнопки под ответом."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from . import texts

# callback_data:
#   fb:up:<request_id>     — палец вверх
#   fb:down:<request_id>   — палец вниз (дальше бот просит правильный ответ)
#   conv:todo:<request_id> — «а теперь то же самое в тодо бичиг»
#   conv:image:<request_id>

CB_FEEDBACK = "fb"
CB_CONVERT = "conv"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_TRANSLIT), KeyboardButton(text=texts.BTN_TODO)],
            [KeyboardButton(text=texts.BTN_IMAGE), KeyboardButton(text=texts.BTN_HELP)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Пришлите калмыцкий текст…",
    )


def result_keyboard(request_id: int, target: str, with_feedback: bool = True):
    """Кнопки под результатом: продолжить конвертацию + оценка."""
    rows = []

    convert = []
    if target == "translit":
        convert.append(
            InlineKeyboardButton(
                text="→ Тодо бичиг", callback_data=f"{CB_CONVERT}:todo:{request_id}"
            )
        )
    if target in ("translit", "todo"):
        convert.append(
            InlineKeyboardButton(
                text="→ Картинка", callback_data=f"{CB_CONVERT}:image:{request_id}"
            )
        )
    if convert:
        rows.append(convert)

    if with_feedback:
        rows.append(
            [
                InlineKeyboardButton(
                    text="👍", callback_data=f"{CB_FEEDBACK}:up:{request_id}"
                ),
                InlineKeyboardButton(
                    text="👎", callback_data=f"{CB_FEEDBACK}:down:{request_id}"
                ),
            ]
        )

    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rated_keyboard(rating: str) -> InlineKeyboardMarkup:
    """Клавиатура после оценки — кнопки убираем, оставляем отметку."""
    mark = "👍 оценено" if rating == "up" else "👎 оценено"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=mark, callback_data="noop")]]
    )
