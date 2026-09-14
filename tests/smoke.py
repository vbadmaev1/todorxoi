# -*- coding: utf-8 -*-
"""
Прогон бота «на сухую», без подключения к Telegram: подменяем сессию
Bot API заглушкой и скармливаем диспетчеру настоящие Update. Проверяем,
что хэндлеры вообще подхватываются, порядок роутеров не перепутан и
кнопки/состояния отрабатывают.

Запуск (токен не нужен, сеть тоже):

    python -m tests.smoke

Никаких внешних зависимостей, кроме тех, что и так нужны боту.
"""

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ.setdefault("ADMIN_IDS", "5")
os.environ.setdefault("WARMUP", "false")

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.types import (  # noqa: E402
    CallbackQuery,
    Chat,
    Message,
    Update,
    User,
)

from bot.config import Config  # noqa: E402
from bot.handlers import build_router  # noqa: E402
from bot.storage import Storage  # noqa: E402

USER = User(id=5, is_bot=False, first_name="Тест", username="tester")
CHAT = Chat(id=5, type="private")


class FakeSession(BaseSession):
    """Ничего никуда не шлёт — только записывает, что бот собирался отправить."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        self.calls.append((name, method))
        if name in ("SendMessage", "SendPhoto", "SendDocument"):
            return Message(
                message_id=1000 + len(self.calls),
                date=datetime.now(timezone.utc),
                chat=CHAT,
                from_user=User(id=7, is_bot=True, first_name="bot", username="b"),
                text=getattr(method, "text", None),
                caption=getattr(method, "caption", None),
            )
        if name == "GetMe":
            return User(id=7, is_bot=True, first_name="bot", username="testbot")
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    def last(self, kind=None):
        for name, method in reversed(self.calls):
            if kind is None or name == kind:
                return name, method
        return None, None


_uid = [0]


def _next_id():
    _uid[0] += 1
    return _uid[0]


def msg(text):
    return Update(
        update_id=_next_id(),
        message=Message(
            message_id=_next_id(),
            date=datetime.now(timezone.utc),
            chat=CHAT,
            from_user=USER,
            text=text,
        ),
    )


def cb(data, message_id=1001):
    return Update(
        update_id=_next_id(),
        callback_query=CallbackQuery(
            id=str(_next_id()),
            from_user=USER,
            chat_instance="x",
            data=data,
            message=Message(
                message_id=message_id,
                date=datetime.now(timezone.utc),
                chat=CHAT,
                from_user=User(id=7, is_bot=True, first_name="bot", username="b"),
                text="—",
            ),
        ),
    )


def check(condition, label):
    mark = "OK " if condition else "FAIL"
    print(f"  [{mark}] {label}")
    if not condition:
        check.failed += 1


check.failed = 0


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="todorxoi-smoke-"))
    config = Config.from_env()
    config.db_path = tmp / "db.sqlite3"
    config.jsonl_path = tmp / "events.jsonl"
    config.validate()

    storage = Storage(config.db_path, config.jsonl_path)
    storage.connect()

    session = FakeSession()
    bot = Bot(
        token="123456:TEST",
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp["storage"] = storage
    dp["config"] = config
    dp.include_router(build_router())

    print("\n0. Окружение")
    from core.todo_image import SHAPING_ENGINE, SHAPING_OK, shaping_status

    check(SHAPING_OK, f"буквы тодо бичиг соединяются — {shaping_status()}")
    check(
        SHAPING_ENGINE == "harfbuzz",
        "используется HarfBuzz напрямую (не зависит от сборки Pillow)",
    )

    print("\n1. Команды и меню")
    await dp.feed_update(bot, msg("/start"))
    _, m = session.last("SendMessage")
    check(m and "Тодо Бичиг бот" in m.text, "/start отвечает приветствием")

    await dp.feed_update(bot, msg("/help"))
    _, m = session.last("SendMessage")
    check("Три режима" in m.text, "/help описывает логику")

    await dp.feed_update(bot, msg("/mode"))
    _, m = session.last("SendMessage")
    check("Транслитерация" in m.text, "/mode показывает режим по умолчанию")

    print("\n2. Транслитерация (п.1)")
    await dp.feed_update(bot, msg("Хальмг улс"))
    _, m = session.last("SendMessage")
    check("Транслитерация" in m.text, "кириллица обработана в режиме translit")
    check("⏱" in m.text, "в ответе есть время работы")
    check(m.reply_markup is not None, "под ответом есть кнопки")

    print("\n3. Тодо бичиг (п.2)")
    await dp.feed_update(bot, msg("/todo хальмг улс"))
    _, m = session.last("SendMessage")
    check("Тодо бичиг" in m.text, "команда с текстом сразу обработана")
    check(any("᠀" <= ch <= "᢯" for ch in m.text), "в ответе есть тодо бичиг")
    buttons = [b.text for row in m.reply_markup.inline_keyboard for b in row]
    check("👍" in buttons and "👎" in buttons, "есть кнопки 👍/👎")

    print("\n4. Картинка (п.3)")
    await dp.feed_update(bot, msg("/image хальмг улс"))
    name, m = session.last()
    check(name in ("SendPhoto", "SendDocument"), f"пришла картинка ({name})")
    check("⏱" in (m.caption or ""), "в подписи к картинке есть время работы")

    print("\n5. Фидбэк: 👍")
    row = await storage.get_request(1)
    await dp.feed_update(bot, cb(f"fb:up:{row['id']}"))
    stats = await storage.stats()
    check(stats["up"] == 1, "палец вверх записан в базу")

    print("\n6. Фидбэк: 👎 и исправление")
    await dp.feed_update(bot, cb("fb:down:2"))
    _, m = session.last("SendMessage")
    check("правильный ответ" in m.text, "после 👎 бот просит правильный вариант")

    await dp.feed_update(bot, msg("xalimaq ulus"))
    _, m = session.last("SendMessage")
    check("исправление сохранил" in m.text, "исправление принято")
    stats = await storage.stats()
    check(stats["corrections"] == 1, "исправление лежит в базе")
    check(stats["down"] == 1, "минус записан")

    print("\n7. Исправление не перехватывает обычный текст дальше")
    await dp.feed_update(bot, msg("хальмг"))
    # режим на этот момент — «картинка» (его включили в п.4), поэтому
    # смотрим на последний вызов любого типа, а не только SendMessage
    name, m = session.last()
    body = getattr(m, "text", None) or getattr(m, "caption", None) or ""
    check("⏱" in body, f"следующее сообщение снова идёт в перевод ({name})")

    print("\n8. /cancel")
    await dp.feed_update(bot, cb("fb:down:1"))
    await dp.feed_update(bot, msg("/cancel"))
    _, m = session.last("SendMessage")
    check("Минус записан" in m.text, "/cancel выходит из ожидания исправления")

    print("\n9. Кнопка «→ Картинка» под готовым ответом")
    before = len(session.calls)
    await dp.feed_update(bot, cb("conv:image:1"))
    name, m = session.last()
    check(name in ("SendPhoto", "SendDocument"), "кнопка конвертации отдала картинку")
    check(len(session.calls) > before, "запрос действительно обработан")

    print("\n10. Админские команды")
    await dp.feed_update(bot, msg("/stats"))
    _, m = session.last("SendMessage")
    check("Статистика" in m.text, "/stats доступен админу")
    name, _ = None, None
    await dp.feed_update(bot, msg("/export corrections"))
    name, m = session.last()
    check(name == "SendDocument", "/export отдаёт CSV файлом")

    print("\n11. Мусор на входе")
    await dp.feed_update(bot, msg("12345"))
    _, m = session.last("SendMessage")
    check("Не удалось распознать" in m.text, "непонятный текст — понятная ошибка")

    await dp.feed_update(bot, msg("/nosuchcommand"))
    _, m = session.last("SendMessage")
    check("Не знаю такой команды" in m.text, "неизвестная команда не уходит в перевод")

    storage.close()
    await bot.session.close()

    print()
    if check.failed:
        print(f"❌ провалено проверок: {check.failed}")
        sys.exit(1)
    print("✅ все проверки прошли")


if __name__ == "__main__":
    asyncio.run(main())
