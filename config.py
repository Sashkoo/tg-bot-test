import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_chat_id: int
    database_path: str = "bot.db"


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_chat_id_raw = os.getenv("ADMIN_CHAT_ID", "").strip()
    database_path = os.getenv("DATABASE_PATH", "bot.db").strip()

    if not bot_token:
        raise ValueError("Переменная окружения BOT_TOKEN не задана.")

    if not admin_chat_id_raw:
        raise ValueError("Переменная окружения ADMIN_CHAT_ID не задана.")

    try:
        admin_chat_id = int(admin_chat_id_raw)
    except ValueError as exc:
        raise ValueError("ADMIN_CHAT_ID должен быть целым числом.") from exc

    return Settings(
        bot_token=bot_token,
        admin_chat_id=admin_chat_id,
        database_path=database_path or "bot.db",
    )
