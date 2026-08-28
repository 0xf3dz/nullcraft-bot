from __future__ import annotations

from decimal import Decimal
from html import escape

from nullcraft.models import Trade


def format_usd(value: Decimal) -> str:
    return f"${value:,.2f}"


def format_threshold(value: Decimal) -> str:
    return f"Alert threshold: {format_usd(value)}"


def format_trade_alert(trade: Trade) -> str:
    title = escape(trade.title[:180])
    outcome = escape(trade.outcome[:100])
    trader_name = escape(trade.trader_name[:100])
    side = escape(trade.side)

    lines = [
        "<b>Large Polymarket trade</b>",
        f"<b>{title}</b>",
        f"{side} {outcome} at ${trade.price:.4f}",
        f"{trade.size:,.2f} shares · <b>{format_usd(trade.notional_usd)}</b>",
        f'Trader: <a href="{trade.trader_url}">{trader_name}</a>',
    ]

    links = [f'<a href="{trade.transaction_url}">Transaction</a>']
    if trade.market_url is not None:
        links.insert(0, f'<a href="{trade.market_url}">Market</a>')
    lines.append(" · ".join(links))
    return "\n".join(lines)
