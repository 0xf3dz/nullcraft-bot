import unittest
from decimal import Decimal

from nullcraft.models import Trade, TradeDataError


def trade_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "transactionHash": "0x" + "a" * 64,
        "proxyWallet": "0x" + "b" * 40,
        "asset": "12345",
        "conditionId": "0x" + "c" * 64,
        "side": "BUY",
        "size": 100,
        "price": 0.25,
        "timestamp": 1_787_900_000,
        "title": "Test market",
        "slug": "test-market",
        "eventSlug": "test-event",
        "outcome": "Yes",
        "name": "Trader",
        "pseudonym": "Fallback",
    }
    record.update(overrides)
    return record


class TradeTests(unittest.TestCase):
    def test_api_record_produces_exact_decimal_notional(self):
        trade = Trade.from_api(trade_record(size="100.25", price="0.4"))

        self.assertEqual(trade.notional_usd, Decimal("40.100"))
        self.assertEqual(trade.side, "BUY")
        self.assertEqual(trade.trader_name, "Trader")

    def test_identity_changes_for_distinct_fills_in_one_transaction(self):
        first = Trade.from_api(trade_record(size="100"))
        second = Trade.from_api(trade_record(size="101"))

        self.assertNotEqual(first.identity, second.identity)
        self.assertEqual(first.identity, Trade.from_api(trade_record(size="100")).identity)

    def test_urls_use_official_market_profile_and_transaction_hosts(self):
        trade = Trade.from_api(trade_record())

        self.assertEqual(trade.market_url, "https://polymarket.com/event/test-event")
        self.assertTrue(trade.trader_url.startswith("https://polymarket.com/profile/"))
        self.assertTrue(trade.transaction_url.startswith("https://polygonscan.com/tx/"))

    def test_invalid_price_is_rejected(self):
        with self.assertRaisesRegex(TradeDataError, "between zero and one"):
            Trade.from_api(trade_record(price="1.1"))

    def test_missing_transaction_hash_is_rejected(self):
        record = trade_record()
        del record["transactionHash"]

        with self.assertRaisesRegex(TradeDataError, "transactionHash"):
            Trade.from_api(record)


if __name__ == "__main__":
    unittest.main()
