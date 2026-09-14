# -*- coding: utf-8 -*-
"""Сборка роутеров.

Порядок подключения важен, aiogram проверяет роутеры сверху вниз:

  1. common   — команды и кнопки меню. Без фильтра по состоянию, поэтому
                работают даже когда бот ждёт текст исправления.
  2. feedback — 👍/👎 и приём исправления (ловит текст в своём состоянии).
  3. settings — /settings и кнопки палитры.
  4. admin    — /stats и /export: должны сработать раньше, чем общий
                обработчик текста примет команду за калмыцкое слово.
  5. translate — всё остальное: любой текст в текущем режиме.
"""

from aiogram import Router

from . import admin, common, feedback, settings, translate


def build_router() -> Router:
    root = Router(name="root")
    root.include_router(common.router)
    root.include_router(feedback.router)
    root.include_router(settings.router)
    root.include_router(admin.router)
    root.include_router(translate.router)
    return root


__all__ = ["build_router"]
