from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from collections.abc import Sequence

import aiohttp

from nullcraft.config import ConfigurationError, Settings
from nullcraft.monitor import TradeMonitor
from nullcraft.polymarket import PolymarketClient
from nullcraft.storage import SubscriptionStore
from nullcraft.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, stop_event.set)
        except NotImplementedError:
            signal.signal(signal_name, lambda *_: stop_event.set())


async def run_bot(settings: Settings) -> None:
    if settings.telegram_bot_token is None:
        raise ConfigurationError("TELEGRAM_BOT_TOKEN is required")

    timeout = aiohttp.ClientTimeout(total=settings.request_timeout_seconds)
    connector = aiohttp.TCPConnector(limit=20, limit_per_host=10, ttl_dns_cache=300)
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    with SubscriptionStore(settings.database_path) as store:
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            client = PolymarketClient(session, settings.data_api_url)
            monitor: TradeMonitor
            bot = TelegramBot(
                token=settings.telegram_bot_token,
                settings=settings,
                store=store,
                client=client,
                status_provider=lambda: monitor.snapshot(),
            )
            monitor = TradeMonitor(
                client=client,
                store=store,
                alert_sender=bot,
                poll_interval_seconds=settings.poll_interval_seconds,
                startup_lookback_seconds=settings.startup_lookback_seconds,
                overlap_seconds=settings.overlap_seconds,
                processed_retention_seconds=settings.processed_retention_seconds,
            )

            monitor_task: asyncio.Task[None] | None = None
            bot_started = False
            try:
                await bot.start()
                bot_started = True
                monitor_task = asyncio.create_task(monitor.run(stop_event), name="trade-monitor")
                logger.info("Nullcraft bot started")
                await stop_event.wait()
            finally:
                stop_event.set()
                if monitor_task is not None:
                    await monitor_task
                if bot_started:
                    await bot.stop()
                logger.info("Nullcraft bot stopped")


async def run_check(settings: Settings) -> int:
    timeout = aiohttp.ClientTimeout(total=settings.request_timeout_seconds)
    with SubscriptionStore(settings.database_path) as store:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            client = PolymarketClient(session, settings.data_api_url)
            await client.health_check()
            now = int(time.time())
            trades = await client.fetch_trades(
                start_timestamp=max(0, now - settings.startup_lookback_seconds),
                end_timestamp=now,
                minimum_notional_usd=settings.default_threshold_usd,
            )
            print("SQLite storage: OK")
            print("Polymarket Data API: OK")
            print(f"Large trades in lookback window: {len(trades)}")
            print(f"Stored subscriptions: {store.subscription_count()}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nullcraft",
        description="Send Telegram alerts for large Polymarket trades.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check storage and Polymarket access without a Telegram token",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    arguments = parser.parse_args(argv)

    try:
        settings = Settings.from_env(require_bot_token=not arguments.check)
    except ConfigurationError as error:
        parser.error(str(error))
        return

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if arguments.check:
            exit_code = asyncio.run(run_check(settings))
            raise SystemExit(exit_code)
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception:
        logger.exception("Nullcraft stopped after an unrecoverable error")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main(sys.argv[1:])
