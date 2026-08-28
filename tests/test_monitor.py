import unittest
from decimal import Decimal

from nullcraft.models import Trade
from nullcraft.monitor import TradeMonitor
from nullcraft.storage import SubscriptionStore


class FakeClient:
    def __init__(self, trades=()):
        self.trades = tuple(trades)
        self.requests = []

    async def fetch_trades(self, **parameters):
        self.requests.append(parameters)
        return self.trades


class FakeAlertSender:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.alerts = []

    async def send_trade_alert(self, chat_id, trade):
        if self.fail:
            raise RuntimeError("delivery failed")
        self.alerts.append((chat_id, trade.identity))


def sample_trade(*, size: str = "20000", timestamp: int = 100) -> Trade:
    return Trade(
        transaction_hash="0x" + "a" * 64,
        proxy_wallet="0x" + "b" * 40,
        asset_id="12345",
        condition_id="0x" + "c" * 64,
        side="BUY",
        size=Decimal(size),
        price=Decimal("0.5"),
        timestamp=timestamp,
        title="Test market",
        slug="test-market",
        event_slug="test-event",
        outcome="Yes",
        name="Trader",
        pseudonym="",
    )


def build_monitor(client, store, sender):
    return TradeMonitor(
        client=client,
        store=store,
        alert_sender=sender,
        poll_interval_seconds=2,
        startup_lookback_seconds=30,
        overlap_seconds=10,
        processed_retention_seconds=86400,
    )


class TradeMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = SubscriptionStore(":memory:")

    async def asyncTearDown(self):
        self.store.close()

    async def test_no_subscribers_avoids_a_data_api_request(self):
        client = FakeClient()
        monitor = build_monitor(client, self.store, FakeAlertSender())

        cursor = await monitor.poll_once(50, now=100)

        self.assertEqual(cursor, 100)
        self.assertEqual(client.requests, [])

    async def test_poll_uses_overlap_and_the_lowest_threshold(self):
        self.store.set_threshold(1, Decimal("5000"))
        self.store.set_threshold(2, Decimal("10000"))
        client = FakeClient()
        monitor = build_monitor(client, self.store, FakeAlertSender())

        await monitor.poll_once(90, now=100)

        self.assertEqual(client.requests[0]["start_timestamp"], 80)
        self.assertEqual(client.requests[0]["end_timestamp"], 100)
        self.assertEqual(client.requests[0]["minimum_notional_usd"], Decimal("5000"))

    async def test_alert_is_sent_once_to_each_eligible_chat(self):
        self.store.set_threshold(1, Decimal("5000"))
        self.store.set_threshold(2, Decimal("15000"))
        trade = sample_trade()
        client = FakeClient([trade])
        sender = FakeAlertSender()
        monitor = build_monitor(client, self.store, sender)

        await monitor.poll_once(90, now=100)
        await monitor.poll_once(100, now=110)

        self.assertEqual(sender.alerts, [(1, trade.identity)])
        self.assertTrue(self.store.was_delivered(trade.identity, 1))
        self.assertFalse(self.store.was_delivered(trade.identity, 2))

    async def test_failed_delivery_is_not_marked_as_complete(self):
        self.store.set_threshold(1, Decimal("5000"))
        trade = sample_trade()
        monitor = build_monitor(FakeClient([trade]), self.store, FakeAlertSender(fail=True))

        await monitor.poll_once(90, now=100)

        self.assertFalse(self.store.was_delivered(trade.identity, 1))
        self.assertEqual(monitor.snapshot().alerts_sent, 0)


if __name__ == "__main__":
    unittest.main()
