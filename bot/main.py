# -*- coding: utf-8 -*-
"""
Точка входа. Запуск:  python -m bot.main

Режим — long polling: не нужен ни домен, ни сертификат, бот сам ходит за
апдейтами. Для хостинга этого достаточно; если когда-нибудь понадобится
webhook, менять придётся только эту функцию, хэндлеры останутся как есть.
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from .config import Config
from .handlers import build_router
from .storage import Storage

log = logging.getLogger("todorxoi")

COMMANDS = [
    BotCommand(command="translit", description="Кириллица → транслитерация"),
    BotCommand(command="todo", description="→ тодо бичиг"),
    BotCommand(command="image", description="→ картинка"),
    BotCommand(command="mode", description="Текущий режим"),
    BotCommand(command="help", description="Как работает бот"),
    BotCommand(command="cancel", description="Отменить ввод исправления"),
]


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def _warmup() -> None:
    """Прогреваем модель заранее: иначе первый же пользователь будет ждать
    загрузку чекпойнта (несколько секунд) прямо в чате."""
    from core.transliterate import model_info, warmup

    try:
        await asyncio.to_thread(warmup)
        log.info("модель прогрета: %s", model_info())
    except Exception:
        log.exception("прогрев модели не удался — бот продолжит работу")


def _check_shaping() -> None:
    """Монгольское письмо курсивное: формы букв выбирает движок раскладки
    (HarfBuzz через Raqm). Без Raqm Pillow молча рисует изолированные формы —
    картинка выходит нечитаемой. Проверяем на старте, а не когда первый
    пользователь получит несвязный набор букв."""
    from core.todo_image import HAS_RAQM, shaping_status

    if HAS_RAQM:
        log.info("рендер картинок: %s", shaping_status())
    else:
        log.error("РЕНДЕР КАРТИНОК СЛОМАН: %s", shaping_status())
        log.error(
            "Починить: pip install -U --force-reinstall Pillow, затем "
            "python -c \"from PIL import features; print(features.check('raqm'))\" "
            "должно напечатать True. Режимы /translit и /todo работают и так."
        )


async def main() -> None:
    config = Config.from_env()
    setup_logging(config.log_level)
    config.validate()
    _check_shaping()

    storage = Storage(config.db_path, config.jsonl_path)
    storage.connect()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp["storage"] = storage
    dp["config"] = config
    dp.include_router(build_router())

    if config.warmup:
        await _warmup()

    await bot.set_my_commands(COMMANDS)
    me = await bot.get_me()
    log.info("бот запущен: @%s", me.username)

    try:
        # старые накопившиеся апдейты после долгого простоя не нужны
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        storage.close()
        await bot.session.close()
        log.info("бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
