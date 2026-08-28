from __future__ import annotations

import logging
from collections.abc import Mapping
from decimal import Decimal

import aiohttp

from nullcraft.models import Trade, TradeDataError

logger = logging.getLogger(__name__)


class DataAPIError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class PolymarketClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self._session = session
        self._trades_url = f"{base_url.rstrip('/')}/trades"

    async def fetch_trades(
        self,
        *,
        start_timestamp: int,
        minimum_notional_usd: Decimal,
        end_timestamp: int | None = None,
        limit: int = 1_000,
    ) -> tuple[Trade, ...]:
        if start_timestamp < 0:
            raise ValueError("start_timestamp cannot be negative")
        if minimum_notional_usd < 0:
            raise ValueError("minimum_notional_usd cannot be negative")
        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")
        if end_timestamp is not None and end_timestamp < start_timestamp:
            raise ValueError("end_timestamp cannot be below start_timestamp")

        parameters: dict[str, str | int] = {
            "start": start_timestamp,
            "limit": limit,
            "takerOnly": "true",
            "filterType": "CASH",
            "filterAmount": format(minimum_notional_usd, "f"),
        }
        if end_timestamp is not None:
            parameters["end"] = end_timestamp

        async with self._session.get(self._trades_url, params=parameters) as response:
            if response.status != 200:
                body = (await response.text())[:300]
                raise DataAPIError(
                    f"Polymarket Data API returned HTTP {response.status}: {body}",
                    status=response.status,
                )
            try:
                payload = await response.json()
            except (aiohttp.ContentTypeError, ValueError) as error:
                raise DataAPIError("Polymarket Data API returned invalid JSON") from error

        if not isinstance(payload, list):
            raise DataAPIError("Polymarket Data API returned an unexpected response")

        trades: list[Trade] = []
        for index, record in enumerate(payload):
            if not isinstance(record, Mapping):
                logger.warning("Ignored non-object trade at response index %d", index)
                continue
            try:
                trades.append(Trade.from_api(record))
            except TradeDataError as error:
                logger.warning("Ignored invalid trade at response index %d: %s", index, error)

        if len(payload) >= limit and (
            not trades or min(trade.timestamp for trade in trades) >= start_timestamp
        ):
            raise DataAPIError(
                "Polymarket Data API result reached the request limit; "
                "increase the trade threshold"
            )

        trades = [
            trade
            for trade in trades
            if trade.timestamp >= start_timestamp
            and (end_timestamp is None or trade.timestamp <= end_timestamp)
        ]
        trades.sort(key=lambda trade: (trade.timestamp, trade.identity))
        return tuple(trades)

    async def health_check(self) -> None:
        async with self._session.get(
            self._trades_url,
            params={"limit": 1, "takerOnly": "true"},
        ) as response:
            if response.status != 200:
                raise DataAPIError(
                    f"Polymarket Data API health check returned HTTP {response.status}",
                    status=response.status,
                )
            try:
                payload = await response.json()
            except (aiohttp.ContentTypeError, ValueError) as error:
                raise DataAPIError(
                    "Polymarket Data API health check returned invalid JSON"
                ) from error
            if not isinstance(payload, list):
                raise DataAPIError(
                    "Polymarket Data API health check returned an unexpected response"
                )
