import logging
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from nullcraft.config import Settings
from nullcraft.monitor import MonitorSnapshot
from nullcraft.storage import SubscriptionStore
from nullcraft.telegram_bot import TelegramBot


class FakeClient:
    async def health_check(self):
        return None


def settings() -> Settings:
    return Settings(
        telegram_bot_token="123456:ABCDEF",
        database_path=Path(":memory:"),
        default_threshold_usd=Decimal("10000"),
        minimum_threshold_usd=Decimal("100"),
        poll_interval_seconds=2,
        startup_lookback_seconds=30,
        overlap_seconds=10,
        request_timeout_seconds=15,
        processed_retention_seconds=86400,
        data_api_url="https://data.example",
        log_level=logging.INFO,
    )


def snapshot() -> MonitorSnapshot:
    return MonitorSnapshot(
        running=True,
        cursor_timestamp=100,
        last_poll_at=100,
        last_success_at=100,
        last_error=None,
        poll_count=2,
        trades_seen=3,
        alerts_sent=1,
    )


def update_for(chat_id: int):
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id),
        effective_message=message,
    )


class TelegramCommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = SubscriptionStore(":memory:")
        self.bot = TelegramBot(
            token="123456:ABCDEF",
            settings=settings(),
            store=self.store,
            client=FakeClient(),
            status_provider=snapshot,
        )

    async def asyncTearDown(self):
        self.store.close()

    async def test_start_activates_the_default_threshold(self):
        update = update_for(123)

        await self.bot.start_command(update, SimpleNamespace())

        self.assertEqual(self.store.get_threshold(123), Decimal("10000"))
        reply = update.effective_message.reply_text.await_args.args[0]
        self.assertIn("Alerts activated", reply)

    async def test_set_threshold_activates_the_chat(self):
        update = update_for(123)
        context = SimpleNamespace(args=["$25,000"])

        await self.bot.set_threshold_command(update, context)

        self.assertEqual(self.store.get_threshold(123), Decimal("25000"))

    async def test_threshold_below_the_minimum_is_rejected(self):
        update = update_for(123)
        context = SimpleNamespace(args=["99"])

        await self.bot.set_threshold_command(update, context)

        self.assertIsNone(self.store.get_threshold(123))
        reply = update.effective_message.reply_text.await_args.args[0]
        self.assertIn("minimum threshold", reply)

    async def test_debug_does_not_return_other_chat_identifiers(self):
        self.store.set_threshold(123, Decimal("10000"))
        self.store.set_threshold(987654321, Decimal("10000"))
        update = update_for(123)

        await self.bot.debug_command(update, SimpleNamespace())

        reply = update.effective_message.reply_text.await_args.args[0]
        self.assertNotIn("987654321", reply)
        self.assertIn("Subscribers: 2", reply)


if __name__ == "__main__":
    unittest.main()
