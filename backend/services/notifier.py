"""Outbound Telegram messages. The bot token never leaves the server process."""

import logging

from backend.bot import runtime

logger = logging.getLogger("fazo")


class Notifier:
    def __init__(self) -> None:
        self.outbox: list[dict] = []

    async def send_message(self, telegram_id: int, text: str, reply_markup=None, link_preview_options=None) -> None:
        self.outbox.append({"telegram_id": telegram_id, "text": text, "kind": "message"})
        bot = runtime.bot
        if bot is None or not telegram_id:
            return
        try:
            await bot.send_message(
                telegram_id,
                text,
                reply_markup=reply_markup,
                link_preview_options=link_preview_options,
            )
        except Exception:
            logger.exception("notify failed telegram_id=%s", telegram_id)

    async def send_photo(self, telegram_id: int, photo, caption: str, reply_markup=None):
        self.outbox.append({"telegram_id": telegram_id, "text": caption, "kind": "photo"})
        bot = runtime.bot
        if bot is None or not telegram_id:
            return None
        try:
            return await bot.send_photo(telegram_id, photo, caption=caption, reply_markup=reply_markup)
        except Exception:
            logger.exception("photo notify failed telegram_id=%s", telegram_id)
            return None


_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    global _notifier
    if _notifier is None:
        _notifier = Notifier()
    return _notifier
