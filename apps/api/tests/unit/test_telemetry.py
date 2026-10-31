from collections.abc import Callable
from typing import TYPE_CHECKING, cast

import sentry_sdk
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.core.telemetry import configure_metrics, configure_sentry, configure_tracing, scrub_event

if TYPE_CHECKING:
    from sentry_sdk.types import Event

type SettingsFactory = Callable[..., Settings]


def test_tracing_stays_off_without_an_otlp_endpoint(make_settings: SettingsFactory) -> None:
    settings = make_settings()
    engine = create_async_engine(settings.database_url.get_secret_value())

    assert configure_tracing(settings, engine=engine) is None


def test_metrics_stay_off_without_an_otlp_endpoint(make_settings: SettingsFactory) -> None:
    assert configure_metrics(make_settings(), process="worker") is None


def test_sentry_stays_off_without_a_dsn(make_settings: SettingsFactory) -> None:
    configure_sentry(make_settings())

    assert not sentry_sdk.is_initialized()


def test_sentry_events_have_phone_numbers_masked() -> None:
    event = cast(
        "Event",
        {
            "message": "OTP for +919876543210 failed",
            "extra": {"phone": "9876543210"},
            "exception": {"values": [{"type": "LookupError", "value": "no user 98765 43210"}]},
        },
    )

    scrubbed = str(scrub_event(event, {}))

    assert "9876543210" not in scrubbed
    assert "98765 43210" not in scrubbed
    assert scrubbed.count("******3210") == 3
