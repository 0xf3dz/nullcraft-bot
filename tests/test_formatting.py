import unittest
from decimal import Decimal

from nullcraft.formatting import format_trade_alert, format_usd
from nullcraft.models import Trade


class AlertFormattingTests(unittest.TestCase):
    def test_dynamic_trade_text_is_escaped_for_telegram_html(self):
        trade = Trade(
            transaction_hash="0x" + "a" * 64,
            proxy_wallet="0x" + "b" * 40,
            asset_id="12345",
            condition_id="0x" + "c" * 64,
            side="BUY",
            size=Decimal("20000"),
            price=Decimal("0.5"),
            timestamp=100,
            title="<b>Injected title</b>",
            slug="test-market",
            event_slug="test-event",
            outcome="Yes & No",
            name='Trader <a href="bad">name</a>',
            pseudonym="",
        )

        message = format_trade_alert(trade)

        self.assertIn("&lt;b&gt;Injected title&lt;/b&gt;", message)
        self.assertIn("Yes &amp; No", message)
        self.assertIn("Trader &lt;a href=&quot;bad&quot;&gt;name&lt;/a&gt;", message)
        self.assertNotIn('<a href="bad">', message)

    def test_usd_values_have_two_decimal_places(self):
        self.assertEqual(format_usd(Decimal("12345.678")), "$12,345.68")


if __name__ == "__main__":
    unittest.main()
