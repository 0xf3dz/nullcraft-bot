from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from html import escape

from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.error import NetworkError, RetryAfter
from telegram.ext import Application, CommandHandler, ContextTypes

from nullcraft.config import Settings
from nullcraft.formatting import format_threshold, format_trade_alert, format_usd
from nullcraft.models import Trade
from nullcraft.monitor import MonitorSnapshot
from nullcraft.polymarket import PolymarketClient
from nullcraft.storage import SubscriptionStore

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(
        self,
        *,
        token: str,
        settings: Settings,
        store: SubscriptionStore,
        client: PolymarketClient,
        status_provider: Callable[[], MonitorSnapshot],
    ) -> None:
        self._settings = settings
        self._store = store
        self._client = client
        self._status_provider = status_provider
        self.application = Application.builder().token(token).build()
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("stop", self.stop_command))
        self.application.add_handler(CommandHandler("setthreshold", self.set_threshold_command))
        self.application.add_handler(CommandHandler("showthreshold", self.show_threshold_command))
        self.application.add_handler(CommandHandler("debug", self.debug_command))
        self.application.add_handler(CommandHandler("apitest", self.api_test_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_error_handler(self._handle_error)

    async def start_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        created = self._store.subscribe(chat_id, self._settings.default_threshold_usd)
        threshold = self._store.get_threshold(chat_id)
        state = "Alerts activated." if created else "Alerts are already active."
        await self._reply(
            update,
            f"{state}\n{format_threshold(threshold or self._settings.default_threshold_usd)}\n"
            "Use /setthreshold <amount> to change it. Use /stop to disable alerts.",
        )

    async def stop_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        removed = self._store.unsubscribe(chat_id)
        message = "Alerts disabled." if removed else "Alerts are already disabled."
        await self._reply(update, message)

    async def set_threshold_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        if len(context.args) != 1:
            await self._reply(update, "Usage: /setthreshold <amount>")
            return

        raw_amount = context.args[0].replace("$", "").replace(",", "")
        try:
            threshold = Decimal(raw_amount)
        except InvalidOperation:
            await self._reply(update, "The threshold must be a number.")
            return

        if not threshold.is_finite() or threshold < self._settings.minimum_threshold_usd:
            await self._reply(
                update,
                f"The minimum threshold is {format_usd(self._settings.minimum_threshold_usd)}.",
            )
            return

        self._store.set_threshold(chat_id, threshold)
        await self._reply(update, f"Alerts activated.\n{format_threshold(threshold)}")

    async def show_threshold_command(
        self,
        update: Update,
        _: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        threshold = self._store.get_threshold(chat_id)
        if threshold is None:
            await self._reply(update, "Alerts are disabled. Use /start to activate them.")
            return
        await self._reply(update, format_threshold(threshold))

    async def debug_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        threshold = self._store.get_threshold(chat_id)
        snapshot = self._status_provider()
        last_error = escape((snapshot.last_error or "None")[:300])
        message = (
            "<b>Nullcraft status</b>\n"
            f"Your alerts: {'active' if threshold is not None else 'disabled'}\n"
            f"Your threshold: {format_usd(threshold) if threshold is not None else 'Not set'}\n"
            f"Monitor: {'active' if snapshot.running else 'stopped'}\n"
            f"Polls: {snapshot.poll_count:,}\n"
            f"Trades seen: {snapshot.trades_seen:,}\n"
            f"Alerts sent: {snapshot.alerts_sent:,}\n"
            f"Subscribers: {self._store.subscription_count():,}\n"
            f"Last error: {last_error}"
        )
        await self._reply(update, message, parse_mode=ParseMode.HTML)

    async def api_test_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            await self._client.health_check()
        except Exception as error:
            logger.warning("Data API health check failed: %s", error)
            await self._reply(update, "Polymarket Data API check failed.")
            return
        await self._reply(update, "Polymarket Data API check passed.")

    async def help_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply(
            update,
            "Commands:\n"
            "/start - activate alerts\n"
            "/stop - disable alerts\n"
            "/setthreshold <amount> - set the minimum trade value\n"
            "/showthreshold - show your current threshold\n"
            "/debug - show bot status\n"
            "/apitest - test the Polymarket Data API",
        )

    async def send_trade_alert(self, chat_id: int, trade: Trade) -> None:
        message = format_trade_alert(trade)
        for attempt in range(3):
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
                return
            except RetryAfter as error:
                retry_after = error.retry_after
                delay = (
                    retry_after.total_seconds()
                    if hasattr(retry_after, "total_seconds")
                    else float(retry_after)
                )
                await asyncio.sleep(delay)
            except NetworkError:
                if attempt == 2:
                    raise
                await asyncio.sleep(2.0**attempt)
        raise RuntimeError("Telegram alert delivery failed after retries")

    async def start(self) -> None:
        await self.application.initialize()
        await self.application.start()
        if self.application.updater is None:
            raise RuntimeError("Telegram updater is unavailable")
        await self.application.updater.start_polling()

    async def stop(self) -> None:
        if self.application.updater is not None and self.application.updater.running:
            await self.application.updater.stop()
        if self.application.running:
            await self.application.stop()
        await self.application.shutdown()

    @staticmethod
    def _chat_id(update: Update) -> int | None:
        return update.effective_chat.id if update.effective_chat is not None else None

    @staticmethod
    async def _reply(
        update: Update,
        text: str,
        *,
        parse_mode: str | None = None,
    ) -> None:
        if update.effective_message is not None:
            await update.effective_message.reply_text(text, parse_mode=parse_mode)

    @staticmethod
    async def _handle_error(_: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Telegram update failed", exc_info=context.error)
