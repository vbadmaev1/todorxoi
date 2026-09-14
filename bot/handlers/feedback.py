# -*- coding: utf-8 -*-
"""Обратная связь: 👍 / 👎 и приём правильного варианта после 👎.

Логика:
  • 👍 — сразу пишем оценку в БД, кнопки заменяем на отметку «оценено»;
  • 👎 — пишем оценку и переводим пользователя в состояние
    Feedback.waiting_correction, запомнив id запроса. Следующее текстовое
    сообщение уходит не в перевод, а в поле correction того же запроса;
  • /cancel — выходим из состояния, минус при этом остаётся: даже без
    правильного варианта информация «этот ответ плохой» полезна.
"""

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts
from ..state import Feedback
from ..storage import Storage

log = logging.getLogger(__name__)
router = Router(name="feedback")


@router.callback_query(F.data.startswith(f"{keyboards.CB_FEEDBACK}:"))
async def on_rating(
    callback: CallbackQuery, state: FSMContext, storage: Storage
) -> None:
    try:
        _, rating, raw_id = callback.data.split(":", 2)
        request_id = int(raw_id)
    except ValueError:
        await callback.answer()
        return

    if rating not in ("up", "down"):
        await callback.answer()
        return

    row = await storage.get_request(request_id)
    if not row:
        await callback.answer(texts.UNKNOWN_REQUEST, show_alert=True)
        return

    user = callback.from_user
    await storage.save_feedback(
        request_id=request_id,
        user_id=user.id,
        username=user.username,
        rating=rating,
    )

    try:
        await callback.message.edit_reply_markup(
            reply_markup=keyboards.rated_keyboard(rating)
        )
    except TelegramBadRequest:
        pass  # сообщение уже отредактировано/устарело — не страшно

    if rating == "up":
        await callback.answer(texts.FEEDBACK_THANKS_UP)
        return

    await callback.answer()
    await state.set_state(Feedback.waiting_correction)
    await state.update_data(correction_request_id=request_id)
    await callback.message.answer(texts.FEEDBACK_ASK_CORRECTION)


@router.message(Feedback.waiting_correction, Command("cancel"))
async def cancel_correction(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await state.update_data(correction_request_id=None)
    await message.answer(texts.FEEDBACK_CANCELLED)


@router.message(Command("cancel"))
async def nothing_to_cancel(message: Message) -> None:
    await message.answer(texts.NOTHING_TO_CANCEL)


@router.message(Feedback.waiting_correction, F.text)
async def save_correction(
    message: Message, state: FSMContext, storage: Storage
) -> None:
    data = await state.get_data()
    request_id = data.get("correction_request_id")
    if not request_id:
        await state.set_state(None)
        await message.answer(texts.NOTHING_TO_CANCEL)
        return

    user = message.from_user
    await storage.save_feedback(
        request_id=int(request_id),
        user_id=user.id,
        username=user.username,
        rating="down",
        correction=message.text.strip(),
    )
    await state.set_state(None)
    await state.update_data(correction_request_id=None)
    await message.answer(texts.FEEDBACK_SAVED)


@router.message(Feedback.waiting_correction)
async def correction_must_be_text(message: Message) -> None:
    await message.answer(
        "Жду правильный вариант текстом. Если передумали — /cancel."
    )
