# -*- coding: utf-8 -*-
"""Три основных сценария: транслитерация, тодо бичиг, картинка.

Тяжёлая часть (модель + рендер) уезжает в поток через asyncio.to_thread,
иначе один длинный запрос подвесил бы всех остальных пользователей.
"""

import asyncio
import logging

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import core

from .. import formatting, keyboards, texts
from ..config import Config
from ..state import get_mode
from ..storage import Storage

log = logging.getLogger(__name__)
router = Router(name="translate")

# соотношение сторон, после которого Telegram уже не примет картинку как фото
_PHOTO_MAX_RATIO = 19


async def handle_text(
    message: Message,
    text: str,
    target: str,
    storage: Storage,
    config: Config,
    user=None,
) -> None:
    """Общая точка: посчитать, записать в БД, ответить с кнопками.

    user передаётся явно, когда запрос пришёл нажатием inline-кнопки:
    у message в этом случае from_user — сам бот, а не человек."""
    action = ChatAction.UPLOAD_PHOTO if target == core.TARGET_IMAGE else ChatAction.TYPING
    await message.bot.send_chat_action(message.chat.id, action)

    user = user or message.from_user
    base = {
        "user_id": user.id if user else None,
        "username": user.username if user else None,
        "chat_id": message.chat.id,
        "target": target,
        "input_text": text,
    }

    try:
        res = await asyncio.to_thread(core.process, text, target)
    except core.PipelineError as exc:
        await storage.save_request(ok=False, error=str(exc), **base)
        await message.answer(f"⚠️ {exc}")
        return
    except Exception:
        log.exception("сбой обработки: target=%s text=%r", target, text[:80])
        await storage.save_request(ok=False, error="internal", **base)
        await message.answer(texts.ERROR_GENERIC)
        return

    request_id = await storage.save_request(
        source_script=res.source_script,
        translit=res.translit,
        todo=res.todo,
        elapsed_ms=res.elapsed_ms,
        steps=res.steps_ms,
        ok=True,
        **base,
    )

    with_feedback = target != core.TARGET_TRANSLIT or config.feedback_on_translit
    markup = keyboards.result_keyboard(request_id, target, with_feedback)

    if target == core.TARGET_IMAGE:
        await _send_image(message, res, markup)
    else:
        await message.answer(formatting.render_result(res), reply_markup=markup)


async def _send_image(message: Message, res, markup) -> None:
    photo = BufferedInputFile(res.image.getvalue(), filename="todo_bichig.png")
    caption = formatting.render_caption(res)
    w, h = res.image_size or (0, 0)
    too_thin = h and (max(w, h) / max(1, min(w, h))) > _PHOTO_MAX_RATIO
    if too_thin:
        # очень вытянутую картинку Telegram как фото не примет — шлём файлом
        await message.answer_document(photo, caption=caption, reply_markup=markup)
    else:
        await message.answer_photo(photo, caption=caption, reply_markup=markup)


@router.message(StateFilter(None), F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer(
        "Не знаю такой команды. Список — /help.\n"
        "Если это был текст для перевода, пришлите его без ведущего «/»."
    )


@router.message(StateFilter(None), F.text)
async def any_text(
    message: Message, state: FSMContext, storage: Storage, config: Config
) -> None:
    """Любой обычный текст — обрабатываем в текущем режиме."""
    mode = await get_mode(state)
    await handle_text(message, message.text, mode, storage, config)


@router.message(StateFilter(None), ~F.text)
async def non_text(message: Message) -> None:
    await message.answer(
        "Я работаю только с текстом: пришлите калмыцкую кириллицу, "
        "транслитерацию или тодо бичиг."
    )


@router.callback_query(F.data.startswith(f"{keyboards.CB_CONVERT}:"))
async def convert_further(
    callback: CallbackQuery, storage: Storage, config: Config
) -> None:
    """Кнопки «→ Тодо бичиг» и «→ Картинка» под готовым ответом."""
    try:
        _, target, raw_id = callback.data.split(":", 2)
        request_id = int(raw_id)
    except ValueError:
        await callback.answer()
        return

    row = await storage.get_request(request_id)
    if not row:
        await callback.answer(texts.UNKNOWN_REQUEST, show_alert=True)
        return

    await callback.answer()
    await handle_text(
        callback.message, row["input_text"], target, storage, config,
        user=callback.from_user,
    )


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
