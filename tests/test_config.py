import logging
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from nullcraft.config import ConfigurationError, Settings


class SettingsTests(unittest.TestCase):
    def test_defaults_require_only_a_telegram_token(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token"}, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.telegram_bot_token, "test-token")
        self.assertEqual(settings.default_threshold_usd, Decimal("10000"))
        self.assertEqual(settings.minimum_threshold_usd, Decimal("100"))
        self.assertEqual(settings.poll_interval_seconds, 2.0)
        self.assertEqual(settings.log_level, logging.INFO)

    def test_check_mode_does_not_require_a_telegram_token(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env(require_bot_token=False)

        self.assertIsNone(settings.telegram_bot_token)

    def test_bot_mode_rejects_a_missing_telegram_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "TELEGRAM_BOT_TOKEN"):
                Settings.from_env()

    def test_default_threshold_cannot_be_below_the_minimum(self):
        environment = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "NULLCRAFT_DEFAULT_THRESHOLD_USD": "99",
            "NULLCRAFT_MINIMUM_THRESHOLD_USD": "100",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "cannot be below"):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
