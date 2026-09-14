# -*- coding: utf-8 -*-
"""Админские команды: статистика и выгрузка собранного фидбэка.

Доступны только тем, чьи telegram-id перечислены в ADMIN_IDS. Пока эта
переменная пустая, команды не работают ни у кого — чтобы выгрузку не мог
скачать случайный пользователь.
"""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from .. import texts
from ..config import Config
from ..formatting import fmt_ms
from ..storage import Storage

log = logging.getLogger(__name__)
router = Router(name="admin")


@router.message(Command("stats"))
async def cmd_stats(message: Message, storage: Storage, config: Config) -> None:
    if not config.is_admin(message.from_user.id):
        await message.answer(texts.NOT_ADMIN)
        return
    s = await storage.stats()
    by_target = ", ".join(f"{k}: {v}" for k, v in sorted(s["by_target"].items())) or "—"
    total_votes = s["up"] + s["down"]
    share = f"{s['up'] / total_votes * 100:.0f}%" if total_votes else "—"
    await message.answer(
        "<b>Статистика</b>\n\n"
        f"Запросов: {s['requests']} (ошибок: {s['errors']})\n"
        f"По режимам: {by_target}\n"
        f"Уникальных пользователей: {s['users']}\n"
        f"Среднее время: {fmt_ms(s['avg_ms'])}\n\n"
        f"👍 {s['up']} · 👎 {s['down']} · доля 👍: {share}\n"
        f"Присланных исправлений: {s['corrections']}"
    )


@router.message(Command("export"))
async def cmd_export(
    message: Message, command: CommandObject, storage: Storage, config: Config
) -> None:
    """/export — весь фидбэк; /export corrections — только исправления."""
    if not config.is_admin(message.from_user.id):
        await message.answer(texts.NOT_ADMIN)
        return
    only_corrections = (command.args or "").strip().lower().startswith("corr")
    data = await storage.export_csv(only_corrections=only_corrections)
    name = "corrections.csv" if only_corrections else "feedback.csv"
    await message.answer_document(
        BufferedInputFile(data, filename=name),
        caption=(
            "Только исправления" if only_corrections else "Весь собранный фидбэк"
        ),
    )
