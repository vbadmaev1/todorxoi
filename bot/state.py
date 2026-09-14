# -*- coding: utf-8 -*-
"""Состояния FSM и хранение выбранного режима.

Режим держим в данных FSM-состояния: при MemoryStorage он живёт до
рестарта бота, при RedisStorage переживёт и рестарт. Ничего страшного,
если сбросится — по умолчанию включается транслитерация.
"""

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

DEFAULT_MODE = "translit"
MODES = ("translit", "todo", "image")


class Feedback(StatesGroup):
    # бот ждёт от пользователя правильный вариант после нажатия 👎
    waiting_correction = State()


async def get_mode(state: FSMContext) -> str:
    data = await state.get_data()
    mode = data.get("mode", DEFAULT_MODE)
    return mode if mode in MODES else DEFAULT_MODE


async def set_mode(state: FSMContext, mode: str) -> None:
    await state.update_data(mode=mode)
