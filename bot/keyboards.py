# -*- coding: utf-8 -*-
"""Клавиатуры: постоянное меню режимов внизу и inline-кнопки под ответом."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from core.todo_image import BG_PALETTE, PALETTE, color_label  # noqa: F401

from . import texts

# callback_data:
#   fb:up:<request_id>      — палец вверх
#   fb:down:<request_id>    — палец вниз (дальше бот просит правильный ответ)
#   conv:todo:<request_id>  — «а теперь то же самое в тодо бичиг»
#   conv:image:<request_id>
#   set:pick:<поле>         — открыть палитру/список размеров
#   set:set:<поле>:<знач>   — выбрать значение
#   set:back:-              — вернуться в меню настроек
#   set:reset:-             — сбросить всё на умолчания

CB_FEEDBACK = "fb"
CB_CONVERT = "conv"
CB_SETTINGS = "set"

SIZE_LABELS = {"small": "мелкий", "medium": "средний", "large": "крупный"}


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


def settings_menu(opts) -> InlineKeyboardMarkup:
    """Главный экран /settings: что менять."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🖋 Текст: {color_label(opts.fg)}",
                    callback_data=f"{CB_SETTINGS}:pick:fg",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🎨 Фон: {color_label(opts.bg)}",
                    callback_data=f"{CB_SETTINGS}:pick:bg",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🔠 Размер: {SIZE_LABELS.get(opts.size, opts.size)}",
                    callback_data=f"{CB_SETTINGS}:pick:size",
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩︎ Сбросить всё", callback_data=f"{CB_SETTINGS}:reset:-"
                )
            ],
        ]
    )


def _grid(buttons, per_row=3):
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def color_picker(field: str, current: str) -> InlineKeyboardMarkup:
    """Палитра. Текущий цвет помечен галочкой, чтобы не гадать."""
    palette = BG_PALETTE if field == "bg" else PALETTE
    buttons = [
        InlineKeyboardButton(
            text=f"{chip} {label}" + (" ✓" if key == current else ""),
            callback_data=f"{CB_SETTINGS}:set:{field}:{key}",
        )
        for key, label, chip in palette
    ]
    rows = _grid(buttons, per_row=2)
    rows.append(
        [InlineKeyboardButton(text="‹ Назад", callback_data=f"{CB_SETTINGS}:back:-")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def size_picker(current: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=label + (" ✓" if key == current else ""),
            callback_data=f"{CB_SETTINGS}:set:size:{key}",
        )
        for key, label in SIZE_LABELS.items()
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            buttons,
            [InlineKeyboardButton(text="‹ Назад", callback_data=f"{CB_SETTINGS}:back:-")],
        ]
    )


def rated_keyboard(rating: str) -> InlineKeyboardMarkup:
    """Клавиатура после оценки — кнопки убираем, оставляем отметку."""
    mark = "👍 оценено" if rating == "up" else "👎 оценено"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=mark, callback_data="noop")]]
    )
