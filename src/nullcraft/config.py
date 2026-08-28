from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when an environment value cannot produce a safe configuration."""


def _decimal_from_env(name: str, default: str) -> Decimal:
    raw_value = os.getenv(name, default)
    try:
        return Decimal(raw_value)
    except InvalidOperation as error:
        raise ConfigurationError(f"{name} must be a number") from error


def _float_from_env(name: str, default: str) -> float:
    raw_value = os.getenv(name, default)
    try:
        return float(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a number") from error


def _int_from_env(name: str, default: str) -> int:
    raw_value = os.getenv(name, default)
    try:
        return int(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer") from error


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str | None
    database_path: Path
    default_threshold_usd: Decimal
    minimum_threshold_usd: Decimal
    poll_interval_seconds: float
    startup_lookback_seconds: int
    overlap_seconds: int
    request_timeout_seconds: float
    processed_retention_seconds: int
    data_api_url: str
    log_level: int

    @classmethod
    def from_env(cls, *, require_bot_token: bool = True) -> Settings:
        load_dotenv()

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
        if require_bot_token and token is None:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN is required")

        default_threshold = _decimal_from_env("NULLCRAFT_DEFAULT_THRESHOLD_USD", "10000")
        minimum_threshold = _decimal_from_env("NULLCRAFT_MINIMUM_THRESHOLD_USD", "100")
        poll_interval = _float_from_env("NULLCRAFT_POLL_INTERVAL_SECONDS", "2")
        startup_lookback = _int_from_env("NULLCRAFT_STARTUP_LOOKBACK_SECONDS", "30")
        overlap = _int_from_env("NULLCRAFT_OVERLAP_SECONDS", "10")
        request_timeout = _float_from_env("NULLCRAFT_REQUEST_TIMEOUT_SECONDS", "15")
        processed_retention = _int_from_env("NULLCRAFT_PROCESSED_RETENTION_SECONDS", "86400")

        if minimum_threshold <= 0:
            raise ConfigurationError("NULLCRAFT_MINIMUM_THRESHOLD_USD must be greater than zero")
        if default_threshold < minimum_threshold:
            raise ConfigurationError(
                "NULLCRAFT_DEFAULT_THRESHOLD_USD cannot be below the minimum threshold"
            )
        if poll_interval <= 0:
            raise ConfigurationError("NULLCRAFT_POLL_INTERVAL_SECONDS must be greater than zero")
        if startup_lookback < 0:
            raise ConfigurationError("NULLCRAFT_STARTUP_LOOKBACK_SECONDS cannot be negative")
        if overlap < 0:
            raise ConfigurationError("NULLCRAFT_OVERLAP_SECONDS cannot be negative")
        if request_timeout <= 0:
            raise ConfigurationError("NULLCRAFT_REQUEST_TIMEOUT_SECONDS must be greater than zero")
        if processed_retention <= 0:
            raise ConfigurationError(
                "NULLCRAFT_PROCESSED_RETENTION_SECONDS must be greater than zero"
            )

        log_level_name = os.getenv("NULLCRAFT_LOG_LEVEL", "INFO").upper()
        log_level = logging.getLevelNamesMapping().get(log_level_name)
        if not isinstance(log_level, int):
            raise ConfigurationError(f"Unsupported NULLCRAFT_LOG_LEVEL: {log_level_name}")

        return cls(
            telegram_bot_token=token,
            database_path=Path(
                os.getenv("NULLCRAFT_DATABASE_PATH", "data/nullcraft.db")
            ).expanduser(),
            default_threshold_usd=default_threshold,
            minimum_threshold_usd=minimum_threshold,
            poll_interval_seconds=poll_interval,
            startup_lookback_seconds=startup_lookback,
            overlap_seconds=overlap,
            request_timeout_seconds=request_timeout,
            processed_retention_seconds=processed_retention,
            data_api_url=os.getenv(
                "NULLCRAFT_DATA_API_URL", "https://data-api.polymarket.com"
            ).rstrip("/"),
            log_level=log_level,
        )
