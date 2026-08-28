import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from nullcraft.storage import SubscriptionStore


class SubscriptionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "nullcraft.db"
        self.store = SubscriptionStore(database_path)

    def tearDown(self):
        self.store.close()
        self.temporary_directory.cleanup()

    def test_subscribe_does_not_replace_an_existing_threshold(self):
        self.assertTrue(self.store.subscribe(100, Decimal("10000")))
        self.store.set_threshold(100, Decimal("25000"))

        self.assertFalse(self.store.subscribe(100, Decimal("10000")))
        self.assertEqual(self.store.get_threshold(100), Decimal("25000"))

    def test_threshold_update_also_activates_a_new_chat(self):
        self.store.set_threshold(-200, Decimal("1500.25"))

        self.assertEqual(self.store.get_threshold(-200), Decimal("1500.25"))
        self.assertEqual(self.store.subscription_count(), 1)

    def test_subscriber_selection_uses_each_chat_threshold(self):
        self.store.set_threshold(1, Decimal("1000"))
        self.store.set_threshold(2, Decimal("5000"))

        self.assertEqual(self.store.minimum_threshold(), Decimal("1000"))
        self.assertEqual(self.store.subscribers_for(Decimal("4999.99")), (1,))
        self.assertEqual(self.store.subscribers_for(Decimal("5000")), (1, 2))

    def test_delivery_deduplication_is_scoped_to_each_chat(self):
        self.store.record_delivery("trade-one", 1, delivered_at=100)

        self.assertTrue(self.store.was_delivered("trade-one", 1))
        self.assertFalse(self.store.was_delivered("trade-one", 2))
        self.assertEqual(self.store.delivery_count(), 1)

    def test_old_delivery_records_are_removed(self):
        self.store.record_delivery("old", 1, delivered_at=100)
        self.store.record_delivery("current", 1, delivered_at=200)

        self.assertEqual(self.store.delete_deliveries_before(200), 1)
        self.assertFalse(self.store.was_delivered("old", 1))
        self.assertTrue(self.store.was_delivered("current", 1))


if __name__ == "__main__":
    unittest.main()
