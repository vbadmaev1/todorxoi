# -*- coding: utf-8 -*-
"""Конфигурация бота. Всё читается из переменных окружения (.env)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv не обязателен: на хостинге переменные обычно задаются иначе
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on", "да"}


def _int_list(name: str) -> list:
    raw = os.environ.get(name, "")
    out = []
    for piece in raw.replace(";", ",").split(","):
        piece = piece.strip()
        if piece:
            try:
                out.append(int(piece))
            except ValueError:
                pass
    return out


@dataclass
class Config:
    bot_token: str = ""
    data_dir: Path = BASE_DIR / "data"
    db_path: Path = BASE_DIR / "data" / "todorxoi.sqlite3"
    jsonl_path: Path = BASE_DIR / "data" / "events.jsonl"
    model_path: Path = BASE_DIR / "model" / "translit_model_cyr2lat.pt"
    font_path: Path = BASE_DIR / "assets" / "MongolianUniversalWhite.ttf"
    admin_ids: list = field(default_factory=list)
    log_level: str = "INFO"
    warmup: bool = True
    # показывать кнопки 👍/👎 ещё и под обычной транслитерацией (п.1),
    # а не только под тодо бичиг и картинкой
    feedback_on_translit: bool = True
    font_size: int = 64
    max_column_height: int = 900

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls(
            bot_token=os.environ.get("BOT_TOKEN", "").strip(),
            admin_ids=_int_list("ADMIN_IDS"),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            warmup=_bool("WARMUP", True),
            feedback_on_translit=_bool("FEEDBACK_ON_TRANSLIT", True),
            font_size=int(os.environ.get("FONT_SIZE", "64")),
            max_column_height=int(os.environ.get("MAX_COLUMN_HEIGHT", "900")),
        )
        if os.environ.get("DATA_DIR"):
            cfg.data_dir = Path(os.environ["DATA_DIR"]).expanduser().resolve()
            cfg.db_path = cfg.data_dir / "todorxoi.sqlite3"
            cfg.jsonl_path = cfg.data_dir / "events.jsonl"
        if os.environ.get("DB_PATH"):
            cfg.db_path = Path(os.environ["DB_PATH"]).expanduser().resolve()
        if os.environ.get("JSONL_PATH"):
            cfg.jsonl_path = Path(os.environ["JSONL_PATH"]).expanduser().resolve()
        if os.environ.get("MODEL_PATH"):
            cfg.model_path = Path(os.environ["MODEL_PATH"]).expanduser().resolve()
        if os.environ.get("FONT_PATH"):
            cfg.font_path = Path(os.environ["FONT_PATH"]).expanduser().resolve()

        # ядро читает эти пути из окружения — синхронизируем обратно,
        # чтобы core/ и bot/ точно смотрели в одно и то же место
        os.environ["MODEL_PATH"] = str(cfg.model_path)
        os.environ["FONT_PATH"] = str(cfg.font_path)

        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        return cfg

    def validate(self) -> None:
        if not self.bot_token:
            raise RuntimeError(
                "Не задан BOT_TOKEN. Скопируйте .env.example в .env и "
                "впишите токен из @BotFather."
            )
        if not self.model_path.exists():
            raise RuntimeError(f"Не найден чекпойнт модели: {self.model_path}")
        if not self.font_path.exists():
            raise RuntimeError(f"Не найден шрифт тодо бичиг: {self.font_path}")

    def is_admin(self, user_id: int) -> bool:
        # пока ADMIN_IDS не заполнен, админских команд нет ни у кого —
        # так выгрузку фидбэка не сможет забрать случайный человек
        return user_id in self.admin_ids
