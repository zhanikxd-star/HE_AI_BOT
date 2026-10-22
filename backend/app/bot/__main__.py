"""Bot process. Without TELEGRAM_BOT_TOKEN it does not poll Telegram."""

import asyncio
import logging
import time

from app.config import get_settings
from app.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning(
            "TELEGRAM_BOT_TOKEN is unset; Telegram test adapter is active and polling is not started",
            extra={"event": "telegram_mode"},
        )
        while True:
            time.sleep(3600)
    asyncio.run(_poll(settings.telegram_bot_token))


async def _poll(token: str) -> None:
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage

    from app.bot.handlers import router

    bot = Bot(token=token)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    main()
