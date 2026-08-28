import unittest
from decimal import Decimal

from nullcraft.polymarket import DataAPIError, PolymarketClient


class FakeResponse:
    def __init__(self, *, status=200, payload=None, body=""):
        self.status = status
        self.payload = payload
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def json(self):
        return self.payload

    async def text(self):
        return self.body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, *, params):
        self.requests.append((url, params))
        return self.responses.pop(0)


def trade_record(*, timestamp: int, transaction_hash: str) -> dict[str, object]:
    return {
        "transactionHash": transaction_hash,
        "proxyWallet": "0x" + "b" * 40,
        "asset": "12345",
        "conditionId": "0x" + "c" * 64,
        "side": "BUY",
        "size": 100,
        "price": 0.5,
        "timestamp": timestamp,
        "title": "Test market",
        "slug": "test-market",
        "outcome": "Yes",
    }


class PolymarketClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_requests_filtered_taker_trades_and_sorts_them(self):
        newer = trade_record(timestamp=200, transaction_hash="0x" + "2" * 64)
        older = trade_record(timestamp=100, transaction_hash="0x" + "1" * 64)
        session = FakeSession([FakeResponse(payload=[newer, older])])
        client = PolymarketClient(session, "https://data.example")

        trades = await client.fetch_trades(
            start_timestamp=90,
            end_timestamp=210,
            minimum_notional_usd=Decimal("10000"),
        )

        self.assertEqual([trade.timestamp for trade in trades], [100, 200])
        url, parameters = session.requests[0]
        self.assertEqual(url, "https://data.example/trades")
        self.assertEqual(parameters["takerOnly"], "true")
        self.assertEqual(parameters["filterType"], "CASH")
        self.assertEqual(parameters["filterAmount"], "10000")
        self.assertEqual(parameters["start"], 90)
        self.assertEqual(parameters["end"], 210)

    async def test_invalid_records_do_not_hide_valid_records(self):
        valid = trade_record(timestamp=100, transaction_hash="0x" + "1" * 64)
        session = FakeSession([FakeResponse(payload=[{"side": "BUY"}, valid])])
        client = PolymarketClient(session, "https://data.example")

        trades = await client.fetch_trades(
            start_timestamp=90,
            minimum_notional_usd=Decimal("100"),
        )

        self.assertEqual(len(trades), 1)

    async def test_http_error_preserves_the_status(self):
        session = FakeSession([FakeResponse(status=429, body="rate limited")])
        client = PolymarketClient(session, "https://data.example")

        with self.assertRaises(DataAPIError) as context:
            await client.fetch_trades(
                start_timestamp=90,
                minimum_notional_usd=Decimal("100"),
            )

        self.assertEqual(context.exception.status, 429)

    async def test_result_limit_prevents_silent_trade_loss(self):
        record = trade_record(timestamp=100, transaction_hash="0x" + "1" * 64)
        session = FakeSession([FakeResponse(payload=[record])])
        client = PolymarketClient(session, "https://data.example")

        with self.assertRaisesRegex(DataAPIError, "request limit"):
            await client.fetch_trades(
                start_timestamp=90,
                minimum_notional_usd=Decimal("100"),
                limit=1,
            )


if __name__ == "__main__":
    unittest.main()
