from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

from nullcraft.models import Trade
from nullcraft.polymarket import PolymarketClient
from nullcraft.storage import SubscriptionStore

logger = logging.getLogger(__name__)


class AlertSender(Protocol):
    async def send_trade_alert(self, chat_id: int, trade: Trade) -> None: ...


@dataclass(frozen=True, slots=True)
class MonitorSnapshot:
    running: bool
    cursor_timestamp: int | None
    last_poll_at: int | None
    last_success_at: int | None
    last_error: str | None
    poll_count: int
    trades_seen: int
    alerts_sent: int


class TradeMonitor:
    def __init__(
        self,
        *,
        client: PolymarketClient,
        store: SubscriptionStore,
        alert_sender: AlertSender,
        poll_interval_seconds: float,
        startup_lookback_seconds: int,
        overlap_seconds: int,
        processed_retention_seconds: int,
    ) -> None:
        self._client = client
        self._store = store
        self._alert_sender = alert_sender
        self._poll_interval_seconds = poll_interval_seconds
        self._startup_lookback_seconds = startup_lookback_seconds
        self._overlap_seconds = overlap_seconds
        self._processed_retention_seconds = processed_retention_seconds
        self._running = False
        self._cursor_timestamp: int | None = None
        self._last_poll_at: int | None = None
        self._last_success_at: int | None = None
        self._last_error: str | None = None
        self._poll_count = 0
        self._trades_seen = 0
        self._alerts_sent = 0
        self._last_cleanup_at = 0

    def snapshot(self) -> MonitorSnapshot:
        return MonitorSnapshot(
            running=self._running,
            cursor_timestamp=self._cursor_timestamp,
            last_poll_at=self._last_poll_at,
            last_success_at=self._last_success_at,
            last_error=self._last_error,
            poll_count=self._poll_count,
            trades_seen=self._trades_seen,
            alerts_sent=self._alerts_sent,
        )

    async def poll_once(self, cursor_timestamp: int, *, now: int | None = None) -> int:
        poll_time = now if now is not None else int(time.time())
        minimum_threshold = self._store.minimum_threshold()
        self._last_poll_at = poll_time
        self._poll_count += 1

        if minimum_threshold is None:
            self._last_success_at = poll_time
            self._last_error = None
            return poll_time

        start_timestamp = max(0, cursor_timestamp - self._overlap_seconds)
        trades = await self._client.fetch_trades(
            start_timestamp=start_timestamp,
            end_timestamp=poll_time,
            minimum_notional_usd=minimum_threshold,
        )
        self._trades_seen += len(trades)

        for trade in trades:
            for chat_id in self._store.subscribers_for(trade.notional_usd):
                if self._store.was_delivered(trade.identity, chat_id):
                    continue
                try:
                    await self._alert_sender.send_trade_alert(chat_id, trade)
                except Exception:
                    logger.exception("Failed to deliver trade alert")
                    continue
                self._store.record_delivery(trade.identity, chat_id, delivered_at=poll_time)
                self._alerts_sent += 1

        if poll_time - self._last_cleanup_at >= 1800:
            cutoff = poll_time - self._processed_retention_seconds
            removed = self._store.delete_deliveries_before(cutoff)
            if removed:
                logger.info("Removed %d expired alert-delivery records", removed)
            self._last_cleanup_at = poll_time

        self._last_success_at = poll_time
        self._last_error = None
        return poll_time

    async def run(self, stop_event: asyncio.Event) -> None:
        self._running = True
        self._cursor_timestamp = int(time.time()) - self._startup_lookback_seconds
        consecutive_errors = 0
        logger.info("Trade monitor started")

        try:
            while not stop_event.is_set():
                try:
                    self._cursor_timestamp = await self.poll_once(self._cursor_timestamp)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    consecutive_errors += 1
                    self._last_error = str(error)
                    delay = min(60.0, 2.0**consecutive_errors)
                    logger.exception("Trade poll failed; retry in %.1f seconds", delay)
                else:
                    consecutive_errors = 0
                    delay = self._poll_interval_seconds

                with suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
        finally:
            self._running = False
            logger.info("Trade monitor stopped")
