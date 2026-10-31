"""A report that the room isn't as shown, without a database (step 5.7, ADR 0051): its photos'
own rules and what each of ops' decisions settles it as. When one may be opened or settled is
the state machine's, tested with it."""

import pytest

from app.modules.booking.domain.disputes import (
    MAX_PHOTOS,
    DisputeStatus,
    Outcome,
    photo_problems,
    resolved,
)


@pytest.mark.parametrize("count", [0, 1, MAX_PHOTOS])
def test_a_report_takes_up_to_six_photos(count: int) -> None:
    assert photo_problems([f"photo-{index}" for index in range(count)]) == []


def test_a_report_takes_no_more_than_six_photos_each_once() -> None:
    assert photo_problems([f"photo-{index}" for index in range(MAX_PHOTOS + 1)]) == [
        "at most 6 photos"
    ]
    assert photo_problems(["photo-1", "photo-1"]) == ["each photo once"]


def test_each_outcome_settles_the_dispute_its_own_way() -> None:
    assert resolved(Outcome.REFUND) is DisputeStatus.RESOLVED_REFUND
    assert resolved(Outcome.UPHOLD) is DisputeStatus.RESOLVED_UPHOLD
