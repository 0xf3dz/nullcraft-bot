from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping
from urllib.parse import quote


class TradeDataError(ValueError):
    """Raised when the Data API returns an invalid trade record."""


def _required_text(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TradeDataError(f"Trade field {field} must be a non-empty string")
    return value.strip()


def _optional_text(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    return value.strip() if isinstance(value, str) else ""


def _decimal_field(record: Mapping[str, object], field: str) -> Decimal:
    try:
        value = Decimal(str(record[field]))
    except (KeyError, InvalidOperation, TypeError) as error:
        raise TradeDataError(f"Trade field {field} must be a number") from error
    if not value.is_finite():
        raise TradeDataError(f"Trade field {field} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class Trade:
    transaction_hash: str
    proxy_wallet: str
    asset_id: str
    condition_id: str
    side: str
    size: Decimal
    price: Decimal
    timestamp: int
    title: str
    slug: str
    event_slug: str
    outcome: str
    name: str
    pseudonym: str

    @classmethod
    def from_api(cls, record: Mapping[str, object]) -> Trade:
        side = _required_text(record, "side").upper()
        if side not in {"BUY", "SELL"}:
            raise TradeDataError("Trade field side must be BUY or SELL")

        size = _decimal_field(record, "size")
        price = _decimal_field(record, "price")
        if size <= 0:
            raise TradeDataError("Trade size must be greater than zero")
        if price < 0 or price > 1:
            raise TradeDataError("Trade price must be between zero and one")

        try:
            timestamp = int(record["timestamp"])
        except (KeyError, TypeError, ValueError) as error:
            raise TradeDataError("Trade field timestamp must be an integer") from error
        if timestamp < 0:
            raise TradeDataError("Trade timestamp cannot be negative")

        return cls(
            transaction_hash=_required_text(record, "transactionHash").lower(),
            proxy_wallet=_required_text(record, "proxyWallet").lower(),
            asset_id=_required_text(record, "asset"),
            condition_id=_required_text(record, "conditionId").lower(),
            side=side,
            size=size,
            price=price,
            timestamp=timestamp,
            title=_optional_text(record, "title") or "Unknown market",
            slug=_optional_text(record, "slug"),
            event_slug=_optional_text(record, "eventSlug"),
            outcome=_optional_text(record, "outcome") or "Unknown outcome",
            name=_optional_text(record, "name"),
            pseudonym=_optional_text(record, "pseudonym"),
        )

    @property
    def notional_usd(self) -> Decimal:
        return self.size * self.price

    @property
    def identity(self) -> str:
        source = "\x1f".join(
            (
                self.transaction_hash,
                self.proxy_wallet,
                self.asset_id,
                self.side,
                str(self.size),
                str(self.price),
                str(self.timestamp),
            )
        )
        return hashlib.sha256(source.encode()).hexdigest()

    @property
    def trader_name(self) -> str:
        return self.name or self.pseudonym or "Anonymous"

    @property
    def market_url(self) -> str | None:
        market_slug = self.event_slug or self.slug
        if not market_slug:
            return None
        return f"https://polymarket.com/event/{quote(market_slug, safe='')}"

    @property
    def trader_url(self) -> str:
        return f"https://polymarket.com/profile/{quote(self.proxy_wallet, safe='')}"

    @property
    def transaction_url(self) -> str:
        return f"https://polygonscan.com/tx/{quote(self.transaction_hash, safe='')}"
