# -*- coding: utf-8 -*-
"""
/settings — цвет текста, цвет фона и размер шрифта для картинки.

Настройки у каждого пользователя свои и лежат в таблице user_settings,
то есть переживают перезапуск бота (в отличие от режима, который живёт в
памяти FSM). На режимы /translit и /todo они не влияют — там текст.

Два поведения, ради которых всё и затевалось:

  • прозрачный фон — картинку с ним нельзя слать как фото: Telegram
    пережмёт PNG в JPEG, и прозрачность станет чёрным прямоугольником.
    Такие картинки уходят документом (см. handlers/translate.py);

  • совпавшие цвета текста и фона — рисовать нечитаемый прямоугольник
    бессмысленно, поэтому рендер откатывается на чёрное по белому и
    честно сообщает об этом под картинкой.
"""

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from core import DEFAULT_FONT_SIZE, FONT_SIZES, ImageOptions
from core.todo_image import color_label

from .. import keyboards, texts
from ..storage import Storage

log = logging.getLogger(__name__)
router = Router(name="settings")

_VALID_COLORS = {key for key, _, _ in keyboards.BG_PALETTE}


async def load_options(storage: Storage, user_id: int) -> ImageOptions:
    """Настройки пользователя -> ImageOptions. Незаполненные поля берут
    значения по умолчанию, мусор из БД игнорируется."""
    saved = await storage.get_settings(user_id)
    opts = ImageOptions()
    if saved.get("fg") in _VALID_COLORS:
        opts.fg = saved["fg"]
    if saved.get("bg") in _VALID_COLORS:
        opts.bg = saved["bg"]
    if saved.get("size") in FONT_SIZES:
        opts.size = saved["size"]
    return opts


def _describe(opts: ImageOptions) -> str:
    return texts.SETTINGS.format(
        fg=color_label(opts.fg),
        bg=color_label(opts.bg),
        size=keyboards.SIZE_LABELS.get(opts.size, opts.size),
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message, storage: Storage) -> None:
    opts = await load_options(storage, message.from_user.id)
    await message.answer(_describe(opts), reply_markup=keyboards.settings_menu(opts))


async def _refresh(callback: CallbackQuery, opts: ImageOptions, markup) -> None:
    try:
        await callback.message.edit_text(_describe(opts), reply_markup=markup)
    except TelegramBadRequest:
        # «message is not modified» — значит показывать уже нечего
        pass


@router.callback_query(F.data.startswith(f"{keyboards.CB_SETTINGS}:"))
async def on_settings(callback: CallbackQuery, storage: Storage) -> None:
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    user_id = callback.from_user.id
    opts = await load_options(storage, user_id)

    if action == "pick":
        field = parts[2]
        if field == "size":
            markup = keyboards.size_picker(opts.size)
        else:
            markup = keyboards.color_picker(field, getattr(opts, field))
        await callback.answer()
        await _refresh(callback, opts, markup)
        return

    if action == "set":
        field, value = parts[2], parts[3]
        ok = (field in ("fg", "bg") and value in _VALID_COLORS) or (
            field == "size" and value in FONT_SIZES
        )
        if not ok:
            await callback.answer()
            return
        await storage.set_setting(user_id, field, value)
        opts = await load_options(storage, user_id)
        # предупреждаем сразу, а не когда человек получит чёрно-белую картинку
        if field in ("fg", "bg") and opts.fg == opts.bg:
            await callback.answer(texts.SETTINGS_SAME_COLOR, show_alert=True)
        else:
            await callback.answer("Сохранил")
        await _refresh(callback, opts, keyboards.settings_menu(opts))
        return

    if action == "back":
        await callback.answer()
        await _refresh(callback, opts, keyboards.settings_menu(opts))
        return

    if action == "reset":
        await storage.reset_settings(user_id)
        opts = ImageOptions()
        await callback.answer("Вернул настройки по умолчанию")
        await _refresh(callback, opts, keyboards.settings_menu(opts))
        return

    await callback.answer()
