from __future__ import annotations

import sqlite3
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

_CENTS = Decimal("0.01")


def usd_to_cents(amount: Decimal) -> int:
    if not amount.is_finite():
        raise ValueError("Amount must be finite")
    return int(amount.quantize(_CENTS, rounding=ROUND_HALF_UP) * 100)


def cents_to_usd(amount: int) -> Decimal:
    return Decimal(amount) / 100


class SubscriptionStore:
    def __init__(self, database_path: Path | str) -> None:
        path = str(database_path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        self._connection = sqlite3.connect(path)
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    chat_id INTEGER PRIMARY KEY,
                    threshold_cents INTEGER NOT NULL CHECK (threshold_cents > 0),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS deliveries (
                    trade_id TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    delivered_at INTEGER NOT NULL,
                    PRIMARY KEY (trade_id, chat_id)
                );

                CREATE INDEX IF NOT EXISTS deliveries_delivered_at
                    ON deliveries (delivered_at);
                """
            )

    def subscribe(self, chat_id: int, default_threshold: Decimal) -> bool:
        now = int(time.time())
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO subscriptions (chat_id, threshold_cents, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (chat_id) DO NOTHING
                """,
                (chat_id, usd_to_cents(default_threshold), now, now),
            )
        return cursor.rowcount == 1

    def unsubscribe(self, chat_id: int) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM subscriptions WHERE chat_id = ?",
                (chat_id,),
            )
        return cursor.rowcount == 1

    def set_threshold(self, chat_id: int, threshold: Decimal) -> None:
        now = int(time.time())
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO subscriptions (chat_id, threshold_cents, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (chat_id) DO UPDATE SET
                    threshold_cents = excluded.threshold_cents,
                    updated_at = excluded.updated_at
                """,
                (chat_id, usd_to_cents(threshold), now, now),
            )

    def get_threshold(self, chat_id: int) -> Decimal | None:
        row = self._connection.execute(
            "SELECT threshold_cents FROM subscriptions WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        return cents_to_usd(row[0]) if row else None

    def minimum_threshold(self) -> Decimal | None:
        row = self._connection.execute(
            "SELECT MIN(threshold_cents) FROM subscriptions"
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return cents_to_usd(row[0])

    def subscribers_for(self, notional_usd: Decimal) -> tuple[int, ...]:
        rows = self._connection.execute(
            """
            SELECT chat_id
            FROM subscriptions
            WHERE threshold_cents <= ?
            ORDER BY chat_id
            """,
            (usd_to_cents(notional_usd),),
        ).fetchall()
        return tuple(row[0] for row in rows)

    def was_delivered(self, trade_id: str, chat_id: int) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM deliveries WHERE trade_id = ? AND chat_id = ?",
            (trade_id, chat_id),
        ).fetchone()
        return row is not None

    def record_delivery(self, trade_id: str, chat_id: int, *, delivered_at: int | None = None) -> None:
        timestamp = delivered_at if delivered_at is not None else int(time.time())
        with self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO deliveries (trade_id, chat_id, delivered_at)
                VALUES (?, ?, ?)
                """,
                (trade_id, chat_id, timestamp),
            )

    def delete_deliveries_before(self, timestamp: int) -> int:
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM deliveries WHERE delivered_at < ?",
                (timestamp,),
            )
        return cursor.rowcount

    def subscription_count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM subscriptions").fetchone()
        return int(row[0])

    def delivery_count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM deliveries").fetchone()
        return int(row[0])

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SubscriptionStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
