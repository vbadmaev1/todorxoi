# -*- coding: utf-8 -*-
"""/start, /help, переключение режимов, /mode.

Этот роутер подключается ПЕРВЫМ: у его хэндлеров нет фильтра по состоянию,
поэтому команды и кнопки меню работают даже тогда, когда бот ждёт от
пользователя текст исправления.
"""

import logging
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from core import MAX_INPUT_CHARS

from .. import keyboards, texts
from ..config import Config
from ..state import get_mode, set_mode
from ..storage import Storage
from .translate import handle_text

log = logging.getLogger(__name__)
router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    mode = await get_mode(state)
    await message.answer(
        texts.START.format(mode=texts.MODE_TITLES[mode]),
        reply_markup=keyboards.main_menu(),
    )


@router.message(Command("help"))
@router.message(F.text == texts.BTN_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(
        texts.HELP.format(max_chars=MAX_INPUT_CHARS),
        reply_markup=keyboards.main_menu(),
    )


@router.message(Command("mode"))
async def cmd_mode(message: Message, state: FSMContext) -> None:
    mode = await get_mode(state)
    await message.answer(texts.MODE_CURRENT.format(mode=texts.MODE_TITLES[mode]))


async def _switch(
    message: Message,
    state: FSMContext,
    mode: str,
    payload: Optional[str],
    storage: Storage,
    config: Config,
) -> None:
    # переключение режима отменяет незаконченный ввод исправления,
    # но не сбрасывает данные состояния (в них лежит выбранный режим)
    await state.set_state(None)
    await set_mode(state, mode)
    if payload and payload.strip():
        # текст пришёл сразу вместе с командой — обрабатываем, не переспрашивая
        await handle_text(message, payload.strip(), mode, storage, config)
        return
    await message.answer(
        texts.MODE_SWITCHED.format(mode=texts.MODE_TITLES[mode]),
        reply_markup=keyboards.main_menu(),
    )


@router.message(Command("translit"))
async def cmd_translit(
    message: Message, command: CommandObject, state: FSMContext,
    storage: Storage, config: Config,
) -> None:
    await _switch(message, state, "translit", command.args, storage, config)


@router.message(Command("todo"))
async def cmd_todo(
    message: Message, command: CommandObject, state: FSMContext,
    storage: Storage, config: Config,
) -> None:
    await _switch(message, state, "todo", command.args, storage, config)


@router.message(Command("image"))
async def cmd_image(
    message: Message, command: CommandObject, state: FSMContext,
    storage: Storage, config: Config,
) -> None:
    await _switch(message, state, "image", command.args, storage, config)


@router.message(F.text == texts.BTN_TRANSLIT)
async def btn_translit(
    message: Message, state: FSMContext, storage: Storage, config: Config
) -> None:
    await _switch(message, state, "translit", None, storage, config)


@router.message(F.text == texts.BTN_TODO)
async def btn_todo(
    message: Message, state: FSMContext, storage: Storage, config: Config
) -> None:
    await _switch(message, state, "todo", None, storage, config)


@router.message(F.text == texts.BTN_IMAGE)
async def btn_image(
    message: Message, state: FSMContext, storage: Storage, config: Config
) -> None:
    await _switch(message, state, "image", None, storage, config)
