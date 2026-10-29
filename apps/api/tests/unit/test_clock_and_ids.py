import uuid
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.calendar import india_date
from app.core.clock import FrozenClock, SystemClock, today_in_india
from app.core.ids import (
    BOOKING_CODE_PATTERN,
    TICKET_NUMBER_PATTERN,
    new_booking_code,
    new_public_id,
    new_ticket_number,
    normalize_booking_code,
    normalize_ticket_number,
)

# ---------------------------------------------------------------------------------------------
# Clock and calendar
# ---------------------------------------------------------------------------------------------


def test_the_system_clock_is_timezone_aware_utc() -> None:
    assert SystemClock().now().tzinfo is UTC


def test_a_frozen_clock_stands_still_until_moved() -> None:
    clock = FrozenClock(datetime(2027, 7, 1, 9, 0, tzinfo=UTC))

    assert clock.now() == clock.now()
    clock.advance(timedelta(hours=25))
    assert clock.now() == datetime(2027, 7, 2, 10, 0, tzinfo=UTC)
    clock.set(datetime(2027, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))))
    assert clock.now() == datetime(2026, 12, 31, 18, 30, tzinfo=UTC)


def test_clocks_refuse_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FrozenClock(datetime(2027, 7, 1))  # noqa: DTZ001 - the point of the test


def test_india_dates_roll_over_at_midnight_india_time() -> None:
    # 18:29 UTC is 23:59 in India; 18:30 UTC is already the next day there.
    assert india_date(datetime(2027, 6, 30, 18, 29, tzinfo=UTC)) == date(2027, 6, 30)
    assert india_date(datetime(2027, 6, 30, 18, 30, tzinfo=UTC)) == date(2027, 7, 1)
    assert today_in_india(FrozenClock(datetime(2027, 6, 30, 19, 0, tzinfo=UTC))) == date(2027, 7, 1)


# ---------------------------------------------------------------------------------------------
# Public ids and booking codes
# ---------------------------------------------------------------------------------------------


def test_public_ids_are_uuid7_in_creation_order() -> None:
    ids = [new_public_id() for _ in range(1_000)]

    assert {public_id.version for public_id in ids} == {7}
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert isinstance(ids[0], uuid.UUID)


def test_booking_codes_have_the_documented_shape() -> None:
    codes = {new_booking_code() for _ in range(2_000)}

    assert all(BOOKING_CODE_PATTERN.fullmatch(code) for code in codes)
    assert len(codes) == 2_000  # 2^40 possible codes: a repeat here would be astonishing


@pytest.mark.parametrize(
    ("typed", "canonical"),
    [
        ("BK-7F3K2Q9M", "BK-7F3K2Q9M"),
        ("bk-7f3k2q9m", "BK-7F3K2Q9M"),
        (" BK 7F3K 2Q9M ", "BK-7F3K2Q9M"),
        ("7F3K2Q9M", "BK-7F3K2Q9M"),
        ("BK-7F3K2Q9O", "BK-7F3K2Q90"),  # O read as zero
        ("BK-IL3K2Q9M", "BK-113K2Q9M"),  # I and L read as one
        ("BK123456", "BK-BK123456"),  # eight characters: the body, even if it starts with BK
        ("BKBK123456", "BK-BK123456"),
    ],
)
def test_typed_booking_codes_are_normalised(typed: str, canonical: str) -> None:
    assert normalize_booking_code(typed) == canonical


@pytest.mark.parametrize(
    "typed", ["", "BK-", "BK-7F3K2Q9", "BK-7F3K2Q9MX", "BK-7F3K2Q9U", "BK-7F3K!Q9M"]
)
def test_things_that_cannot_be_booking_codes_are_rejected(typed: str) -> None:
    assert normalize_booking_code(typed) is None


@given(st.builds(new_booking_code))
def test_new_codes_are_already_canonical(code: str) -> None:
    assert normalize_booking_code(code) == code


def test_grievance_ticket_numbers_are_codes_of_their_own() -> None:
    numbers = {new_ticket_number() for _ in range(2_000)}

    assert all(TICKET_NUMBER_PATTERN.fullmatch(number) for number in numbers)
    assert len(numbers) == 2_000
    assert normalize_ticket_number("gr 4m8q 2t7k") == "GR-4M8Q2T7K"
    assert normalize_ticket_number("4M8Q2T7K") == "GR-4M8Q2T7K"
    # A booking code isn't a ticket number, nor the other way round.
    assert normalize_ticket_number("BK-4M8Q2T7K") is None
    assert normalize_booking_code("GR-4M8Q2T7K") is None


@given(st.builds(new_ticket_number))
def test_new_ticket_numbers_are_already_canonical(number: str) -> None:
    assert normalize_ticket_number(number) == number
