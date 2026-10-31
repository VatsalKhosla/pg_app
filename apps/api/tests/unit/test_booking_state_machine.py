"""The booking state machine (step 5.2, ADR 0045), without a database: every (status, event,
party) the table allows and refuses, each guard at its edge, the side effects money and beds
follow, and random event sequences that never break the founders' rules."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from itertools import product

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.calendar import india_date
from app.core.money import rupees
from app.modules.booking.domain.state_machine import (
    ALLOCATED,
    ALLOWED,
    FINAL,
    TOKEN_KEPT,
    ActivateAllocation,
    ApplyLateCancelPolicy,
    AutoConfirm,
    BookingEvent,
    BookingFacts,
    BookingStatus,
    CancelPayment,
    CloseDispute,
    DeactivateAllocation,
    EarnToken,
    Effect,
    FlagOwner,
    IssueOwnerInvoice,
    Moment,
    Notify,
    OpenDispute,
    Party,
    RecordTokenReceived,
    RefundToken,
    RequestPayment,
    SetCheckWindowEnd,
    SetConfirmDeadline,
    SetHoldExpiry,
    SuggestSimilar,
    Transition,
    TransitionRefusedError,
    TruncateAllocation,
    allows,
    check_in_opens_on,
    hold,
    transition,
)
from app.modules.pricing.domain.policies import BookingPolicy, LateCancelPolicy

S = BookingStatus
E = BookingEvent
P = Party

TERMS = BookingPolicy(
    token_paise=rupees(2_000),
    hold_minutes=15,
    free_cancel_days=7,
    check_window_hours=24,
    confirm_deadline_hours=12,
    no_show_days=3,
    late_cancel_policy=LateCancelPolicy.REFUND_FULL,
    max_active_holds_per_user=1,
    max_advance_days=120,
)
TOKEN = rupees(2_000)
MOVE_IN = date(2027, 7, 14)
# 10:30 in India, three weeks before the move-in.
NOW = datetime(2027, 6, 23, 5, 0, tzinfo=UTC)

# §7.2 and §7.4 as the spec writes them: (from, event) -> (to, who may send it).
SPEC: dict[tuple[BookingStatus, BookingEvent], tuple[BookingStatus, set[Party]]] = {
    (S.HELD, E.TOKEN_SECURED): (S.TOKEN_SECURED, {P.SYSTEM}),
    (S.HELD, E.HOLD_EXPIRED): (S.EXPIRED, {P.SYSTEM}),
    (S.HELD, E.CANCEL): (S.CANCELLED, {P.STUDENT}),
    (S.TOKEN_SECURED, E.CONFIRM): (S.CONFIRMED, {P.OWNER, P.OPS, P.SYSTEM}),
    (S.TOKEN_SECURED, E.REJECT): (S.REJECTED, {P.OWNER, P.OPS}),
    (S.TOKEN_SECURED, E.CONFIRM_TIMEOUT): (S.REJECTED, {P.SYSTEM}),
    (S.TOKEN_SECURED, E.CANCEL): (S.CANCELLED, {P.STUDENT}),
    (S.TOKEN_SECURED, E.OWNER_CANCEL): (S.CANCELLED, {P.OWNER, P.OPS}),
    (S.CONFIRMED, E.CANCEL): (S.CANCELLED, {P.STUDENT}),
    (S.CONFIRMED, E.CANCEL_LATE): (S.CANCELLED, {P.STUDENT}),
    (S.CONFIRMED, E.OWNER_CANCEL): (S.CANCELLED, {P.OWNER, P.OPS}),
    (S.CONFIRMED, E.CHECK_IN): (S.CHECKED_IN, {P.STUDENT}),
    (S.CONFIRMED, E.NO_SHOW): (S.NO_SHOW, {P.SYSTEM}),
    (S.CHECKED_IN, E.DISPUTE): (S.DISPUTED, {P.STUDENT}),
    (S.CHECKED_IN, E.WINDOW_ELAPSED): (S.ACTIVE, {P.SYSTEM}),
    (S.DISPUTED, E.RESOLVE_REFUND): (S.REFUNDED, {P.OPS}),
    (S.DISPUTED, E.RESOLVE_UPHOLD): (S.ACTIVE, {P.OPS}),
    (S.ACTIVE, E.MOVE_OUT): (S.COMPLETED, {P.STUDENT, P.OWNER, P.OPS}),
    (S.EXPIRED, E.LATE_PAYMENT_REVIVE): (S.TOKEN_SECURED, {P.SYSTEM}),
    (S.EXPIRED, E.LATE_PAYMENT_REFUND): (S.EXPIRED, {P.SYSTEM}),
}


def at_india(day: date, hour: int, minute: int = 0) -> datetime:
    """``hour:minute`` on ``day`` in India (UTC+05:30), in UTC."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC) - timedelta(
        hours=5, minutes=30
    )


def facts(
    status: BookingStatus,
    *,
    instant_confirm: bool = False,
    hold_expires_at: datetime | None = None,
    confirm_by: datetime | None = None,
    check_window_ends_at: datetime | None = None,
) -> BookingFacts:
    return BookingFacts(
        status=status,
        move_in=MOVE_IN,
        token_paise=TOKEN,
        instant_confirm=instant_confirm,
        hold_expires_at=hold_expires_at,
        confirm_by=confirm_by,
        check_window_ends_at=check_window_ends_at,
    )


WINDOW_ENDS = at_india(MOVE_IN, 12)
MOVED_OUT = MOVE_IN + timedelta(days=330)
# A booking and a moment every guard on the pair lets through; any other pair takes Moment(NOW).
PASSING: dict[tuple[BookingStatus, BookingEvent], tuple[BookingFacts, Moment]] = {
    (S.HELD, E.TOKEN_SECURED): (facts(S.HELD), Moment(NOW, paid_paise=TOKEN)),
    (S.HELD, E.HOLD_EXPIRED): (facts(S.HELD, hold_expires_at=NOW), Moment(NOW)),
    (S.TOKEN_SECURED, E.CONFIRM): (facts(S.TOKEN_SECURED, instant_confirm=True), Moment(NOW)),
    (S.TOKEN_SECURED, E.CONFIRM_TIMEOUT): (facts(S.TOKEN_SECURED, confirm_by=NOW), Moment(NOW)),
    (S.CONFIRMED, E.CANCEL_LATE): (
        facts(S.CONFIRMED),
        Moment(at_india(MOVE_IN - timedelta(days=2), 9)),
    ),
    (S.CONFIRMED, E.CHECK_IN): (facts(S.CONFIRMED), Moment(at_india(MOVE_IN, 9))),
    (S.CONFIRMED, E.NO_SHOW): (
        facts(S.CONFIRMED),
        Moment(at_india(MOVE_IN + timedelta(days=4), 10)),
    ),
    (S.CHECKED_IN, E.DISPUTE): (
        facts(S.CHECKED_IN, check_window_ends_at=WINDOW_ENDS),
        Moment(WINDOW_ENDS - timedelta(hours=1)),
    ),
    (S.CHECKED_IN, E.WINDOW_ELAPSED): (
        facts(S.CHECKED_IN, check_window_ends_at=WINDOW_ENDS),
        Moment(WINDOW_ENDS),
    ),
    (S.ACTIVE, E.MOVE_OUT): (
        facts(S.ACTIVE),
        Moment(at_india(MOVED_OUT, 18), moved_out_on=MOVED_OUT),
    ),
    (S.EXPIRED, E.LATE_PAYMENT_REVIVE): (
        facts(S.EXPIRED),
        Moment(NOW, paid_paise=TOKEN, bed_free=True),
    ),
    (S.EXPIRED, E.LATE_PAYMENT_REFUND): (
        facts(S.EXPIRED),
        Moment(NOW, paid_paise=TOKEN, bed_free=False),
    ),
}


def refusal(booking: BookingFacts, event: BookingEvent, party: Party, moment: Moment) -> str:
    with pytest.raises(TransitionRefusedError) as refused:
        transition(booking, event, party, moment, TERMS)
    return refused.value.reason


def test_the_table_is_the_spec() -> None:
    assert set(SPEC) == ALLOWED


@pytest.mark.parametrize(("status", "event", "party"), list(product(S, E, P)))
def test_every_status_event_and_party(
    status: BookingStatus, event: BookingEvent, party: Party
) -> None:
    booking, moment = PASSING.get((status, event), (facts(status), Moment(NOW)))
    allowed = SPEC.get((status, event))
    if allowed is None:
        assert refusal(booking, event, party, moment).startswith(
            f"A {status.replace('_', '-')} booking can't "
        )
    elif party in allowed[1]:
        assert transition(booking, event, party, moment, TERMS).to is allowed[0]
    else:
        assert refusal(booking, event, party, moment) == f"That's not for the {party} to do."


def test_final_statuses_take_nothing_and_every_status_is_reachable() -> None:
    assert not {status for status, _ in ALLOWED} & FINAL
    reached = {S.HELD}
    while frontier := {SPEC[pair][0] for pair in SPEC if pair[0] in reached} - reached:
        reached |= frontier
    assert reached == set(S)


def test_a_hold_holds_the_bed_and_asks_for_the_token() -> None:
    assert hold(now=NOW, policy=TERMS) == Transition(
        S.HELD,
        (ActivateAllocation(), SetHoldExpiry(NOW + timedelta(minutes=15)), RequestPayment()),
    )


@pytest.mark.parametrize("paid", [TOKEN - 1, TOKEN + 100, None])
def test_only_the_bookings_token_secures_it(paid: int | None) -> None:
    for status, event in [(S.HELD, E.TOKEN_SECURED), (S.EXPIRED, E.LATE_PAYMENT_REVIVE)]:
        moment = Moment(NOW, paid_paise=paid, bed_free=True)
        assert refusal(facts(status), event, P.SYSTEM, moment) == (
            "The payment isn't the booking's token."
        )


def test_a_secured_token_is_kept_and_the_owner_has_a_deadline() -> None:
    secured = transition(
        facts(S.HELD), E.TOKEN_SECURED, P.SYSTEM, Moment(NOW, paid_paise=TOKEN), TERMS
    )
    assert secured.effects == (
        RecordTokenReceived(),
        SetConfirmDeadline(NOW + timedelta(hours=12)),
        Notify(P.OWNER),
        Notify(P.OPS),
    )
    instant = transition(
        facts(S.HELD, instant_confirm=True),
        E.TOKEN_SECURED,
        P.SYSTEM,
        Moment(NOW, paid_paise=TOKEN),
        TERMS,
    )
    assert instant.effects == (*secured.effects, AutoConfirm())


def test_only_a_pg_that_confirms_itself_is_confirmed_by_the_system() -> None:
    assert refusal(facts(S.TOKEN_SECURED), E.CONFIRM, P.SYSTEM, Moment(NOW)) == (
        "The owner confirms this PG's bookings."
    )
    for party in (P.OWNER, P.OPS):
        confirmed = transition(facts(S.TOKEN_SECURED), E.CONFIRM, party, Moment(NOW), TERMS)
        assert confirmed == Transition(S.CONFIRMED, (Notify(P.STUDENT),))


def test_a_hold_and_a_confirmation_run_out_at_their_moment() -> None:
    held = facts(S.HELD, hold_expires_at=NOW)
    assert refusal(held, E.HOLD_EXPIRED, P.SYSTEM, Moment(NOW - timedelta(seconds=1))) == (
        "The hold hasn't expired."
    )
    assert transition(held, E.HOLD_EXPIRED, P.SYSTEM, Moment(NOW), TERMS).effects == (
        DeactivateAllocation(),
        CancelPayment(),
    )
    assert (
        refusal(facts(S.HELD), E.HOLD_EXPIRED, P.SYSTEM, Moment(NOW)) == "The hold hasn't expired."
    )

    waiting = facts(S.TOKEN_SECURED, confirm_by=NOW)
    early = Moment(NOW - timedelta(seconds=1))
    assert refusal(waiting, E.CONFIRM_TIMEOUT, P.SYSTEM, early) == (
        "The owner still has time to confirm."
    )
    assert transition(waiting, E.CONFIRM_TIMEOUT, P.SYSTEM, Moment(NOW), TERMS).effects == (
        DeactivateAllocation(),
        RefundToken(),
        SuggestSimilar(),
        Notify(P.STUDENT),
        Notify(P.OWNER),
        Notify(P.OPS),
    )


def test_free_cancellation_ends_seven_days_before_the_move_in_by_indias_day() -> None:
    confirmed = facts(S.CONFIRMED)
    last_free_day = MOVE_IN - timedelta(days=7)
    still_free = Moment(at_india(last_free_day, 23, 59))
    too_late = Moment(at_india(last_free_day + timedelta(days=1), 0, 0))

    assert transition(confirmed, E.CANCEL, P.STUDENT, still_free, TERMS).effects == (
        DeactivateAllocation(),
        RefundToken(),
        Notify(P.OWNER),
    )
    assert refusal(confirmed, E.CANCEL_LATE, P.STUDENT, still_free) == "Cancelling now is free."
    assert refusal(confirmed, E.CANCEL, P.STUDENT, too_late) == (
        "Free cancellation ended 7 days before the move-in."
    )
    assert transition(confirmed, E.CANCEL_LATE, P.STUDENT, too_late, TERMS).effects == (
        DeactivateAllocation(),
        ApplyLateCancelPolicy(),
        Notify(P.OWNER),
    )


def test_a_booking_not_yet_confirmed_cancels_for_free_at_any_time() -> None:
    on_the_day = Moment(at_india(MOVE_IN, 9))
    cancelled = transition(facts(S.TOKEN_SECURED), E.CANCEL, P.STUDENT, on_the_day, TERMS)
    assert RefundToken() in cancelled.effects
    assert refusal(facts(S.TOKEN_SECURED), E.CANCEL_LATE, P.STUDENT, on_the_day).startswith(
        "A token-secured booking can't"
    )


@pytest.mark.parametrize("status", [S.TOKEN_SECURED, S.CONFIRMED])
@pytest.mark.parametrize("party", [P.OWNER, P.OPS])
def test_an_owner_who_cancels_refunds_the_student_and_is_flagged(
    status: BookingStatus, party: Party
) -> None:
    cancelled = transition(facts(status), E.OWNER_CANCEL, party, Moment(NOW), TERMS)
    assert cancelled.effects == (
        DeactivateAllocation(),
        RefundToken(),
        SuggestSimilar(),
        FlagOwner(),
        Notify(P.STUDENT),
        Notify(P.OPS),
    )


def test_a_rejection_refunds_and_helps_the_student_book_again() -> None:
    rejected = transition(facts(S.TOKEN_SECURED), E.REJECT, P.OWNER, Moment(NOW), TERMS)
    assert rejected.effects == (
        DeactivateAllocation(),
        RefundToken(),
        SuggestSimilar(),
        Notify(P.STUDENT),
    )


def test_checking_in_opens_the_day_before_the_move_in_and_starts_the_window() -> None:
    confirmed = facts(S.CONFIRMED)
    two_days_before = Moment(at_india(MOVE_IN - timedelta(days=2), 23, 59))
    assert refusal(confirmed, E.CHECK_IN, P.STUDENT, two_days_before) == (
        "Checking in opens the day before the move-in."
    )
    day_before = at_india(MOVE_IN - timedelta(days=1), 0, 0)
    assert transition(confirmed, E.CHECK_IN, P.STUDENT, Moment(day_before), TERMS).effects == (
        SetCheckWindowEnd(day_before + timedelta(hours=24)),
        Notify(P.OWNER),
    )
    a_week_late = Moment(at_india(MOVE_IN + timedelta(days=7), 9))
    assert transition(confirmed, E.CHECK_IN, P.STUDENT, a_week_late, TERMS).to is S.CHECKED_IN


def test_a_page_offers_a_change_exactly_when_the_machine_takes_it() -> None:
    confirmed = facts(S.CONFIRMED)
    opens = at_india(check_in_opens_on(MOVE_IN), 0, 0)
    assert check_in_opens_on(MOVE_IN) == date(2027, 7, 13)
    assert not allows(confirmed, E.CHECK_IN, P.STUDENT, Moment(opens - timedelta(seconds=1)), TERMS)
    assert allows(confirmed, E.CHECK_IN, P.STUDENT, Moment(opens), TERMS)
    # Not the owner's to say, nor a booking that isn't confirmed.
    assert not allows(confirmed, E.CHECK_IN, P.OWNER, Moment(opens), TERMS)
    assert not allows(facts(S.TOKEN_SECURED), E.CHECK_IN, P.STUDENT, Moment(opens), TERMS)


def test_a_no_show_waits_the_terms_days_after_the_move_in() -> None:
    confirmed = facts(S.CONFIRMED)
    last_day = Moment(at_india(MOVE_IN + timedelta(days=3), 23, 59))
    assert refusal(confirmed, E.NO_SHOW, P.SYSTEM, last_day) == (
        "A student has 3 days after the move-in to arrive."
    )
    after = Moment(at_india(MOVE_IN + timedelta(days=4), 0, 0))
    assert transition(confirmed, E.NO_SHOW, P.SYSTEM, after, TERMS).effects == (
        DeactivateAllocation(),
        ApplyLateCancelPolicy(),
        Notify(P.STUDENT),
        Notify(P.OWNER),
    )


def test_the_check_window_ends_at_exactly_its_moment() -> None:
    ends_at = at_india(MOVE_IN, 12)
    checked_in = facts(S.CHECKED_IN, check_window_ends_at=ends_at)
    last_second = Moment(ends_at - timedelta(seconds=1))

    assert transition(checked_in, E.DISPUTE, P.STUDENT, last_second, TERMS).effects == (
        OpenDispute(),
        Notify(P.OPS),
        Notify(P.OWNER),
    )
    assert refusal(checked_in, E.WINDOW_ELAPSED, P.SYSTEM, last_second) == (
        "The time to report a problem with the room hasn't passed."
    )
    assert refusal(checked_in, E.DISPUTE, P.STUDENT, Moment(ends_at)) == (
        "The time to report a problem with the room has passed."
    )
    assert transition(checked_in, E.WINDOW_ELAPSED, P.SYSTEM, Moment(ends_at), TERMS).effects == (
        EarnToken(),
        IssueOwnerInvoice(),
        Notify(P.STUDENT),
        Notify(P.OWNER),
    )
    no_window = facts(S.CHECKED_IN)
    assert refusal(no_window, E.DISPUTE, P.STUDENT, last_second).startswith("The time to report")
    assert refusal(no_window, E.WINDOW_ELAPSED, P.SYSTEM, last_second).startswith("The time to")


def test_ops_resolve_a_dispute_either_way() -> None:
    disputed = facts(S.DISPUTED)
    assert transition(disputed, E.RESOLVE_REFUND, P.OPS, Moment(NOW), TERMS) == Transition(
        S.REFUNDED,
        (
            CloseDispute(refunded=True),
            DeactivateAllocation(),
            RefundToken(),
            SuggestSimilar(),
            Notify(P.STUDENT),
            Notify(P.OWNER),
        ),
    )
    assert transition(disputed, E.RESOLVE_UPHOLD, P.OPS, Moment(NOW), TERMS) == Transition(
        S.ACTIVE,
        (
            CloseDispute(refunded=False),
            EarnToken(),
            IssueOwnerInvoice(),
            Notify(P.STUDENT),
            Notify(P.OWNER),
        ),
    )


@pytest.mark.parametrize(
    ("moved_out_on", "problem"),
    [
        (None, "A move-out comes after the move-in."),
        (MOVE_IN, "A move-out comes after the move-in."),
        (MOVE_IN + timedelta(days=31), "A move-out is recorded once it has happened."),
    ],
)
def test_a_move_out_is_a_day_after_the_move_in_that_has_come(
    moved_out_on: date | None, problem: str
) -> None:
    today = at_india(MOVE_IN + timedelta(days=30), 10)
    moment = Moment(today, moved_out_on=moved_out_on)
    assert refusal(facts(S.ACTIVE), E.MOVE_OUT, P.OWNER, moment) == problem


def test_a_move_out_cuts_the_bed_short_on_its_day() -> None:
    moved_out_on = MOVE_IN + timedelta(days=30)
    moment = Moment(at_india(moved_out_on, 10), moved_out_on=moved_out_on)
    assert transition(facts(S.ACTIVE), E.MOVE_OUT, P.STUDENT, moment, TERMS) == Transition(
        S.COMPLETED, (TruncateAllocation(moved_out_on),)
    )


def test_a_late_payment_takes_the_bed_if_its_free_or_goes_straight_back() -> None:
    expired = facts(S.EXPIRED)
    free = Moment(NOW, paid_paise=TOKEN, bed_free=True)
    gone = Moment(NOW, paid_paise=TOKEN, bed_free=False)
    unknown = Moment(NOW, paid_paise=TOKEN)

    revived = transition(expired, E.LATE_PAYMENT_REVIVE, P.SYSTEM, free, TERMS)
    assert revived.to is S.TOKEN_SECURED
    assert revived.effects[:2] == (ActivateAllocation(), RecordTokenReceived())
    assert refusal(expired, E.LATE_PAYMENT_REVIVE, P.SYSTEM, gone) == "The bed has gone."
    assert refusal(expired, E.LATE_PAYMENT_REVIVE, P.SYSTEM, unknown) == "The bed has gone."

    assert transition(expired, E.LATE_PAYMENT_REFUND, P.SYSTEM, gone, TERMS) == Transition(
        S.EXPIRED, (RecordTokenReceived(), RefundToken(), SuggestSimilar(), Notify(P.STUDENT))
    )
    for moment in (free, unknown):
        assert refusal(expired, E.LATE_PAYMENT_REFUND, P.SYSTEM, moment) == (
            "The bed is still free, so the booking takes the payment."
        )
    wrong = Moment(NOW, paid_paise=TOKEN - 1, bed_free=False)
    assert refusal(expired, E.LATE_PAYMENT_REFUND, P.SYSTEM, wrong) == (
        "The payment isn't the booking's token."
    )


# Random histories: whatever arrives, in whatever order, money and beds follow the rules.

MINUTE = timedelta(minutes=1)
STEPS = [
    timedelta(0),
    MINUTE,
    15 * MINUTE,
    timedelta(hours=12),
    timedelta(days=1),
    timedelta(days=8),
]


class Booking:
    """A booking's history as the services would carry it out, checking every effect."""

    def __init__(self, *, move_in: date, instant_confirm: bool) -> None:
        self.facts = BookingFacts(
            status=S.HELD, move_in=move_in, token_paise=TOKEN, instant_confirm=instant_confirm
        )
        self.now = NOW
        self.allocated = False
        # Tokens received and not yet earned, given back or settled by the late-cancel rule.
        self.kept = 0
        self.earned = 0
        self.invoices = 0
        self.been_active = False
        self.carry_out(hold(now=self.now, policy=TERMS))

    def send(self, event: BookingEvent, party: Party, moment: Moment) -> bool:
        try:
            step = transition(self.facts, event, party, moment, TERMS)
        except TransitionRefusedError:
            return False
        self.carry_out(step)
        return True

    def carry_out(self, step: Transition) -> None:
        # Rule 8: a booking makes money only on its way into ACTIVE.
        if {EarnToken(), IssueOwnerInvoice()} & set(step.effects):
            assert step.to is S.ACTIVE
        self.facts = replace(self.facts, status=step.to)
        for effect in step.effects:
            self.apply(effect)
        self.been_active |= step.to is S.ACTIVE
        assert self.allocated is (step.to in ALLOCATED)
        assert self.kept == (1 if step.to in TOKEN_KEPT else 0)
        assert self.earned == self.invoices == (1 if self.been_active else 0)
        instant = step.to is S.TOKEN_SECURED and self.facts.instant_confirm
        assert (AutoConfirm() in step.effects) is instant
        if instant:
            # The service confirms straight after, as the system.
            self.carry_out(transition(self.facts, E.CONFIRM, P.SYSTEM, Moment(self.now), TERMS))

    def apply(self, effect: Effect) -> None:
        match effect:
            case ActivateAllocation():
                assert not self.allocated
                self.allocated = True
            case DeactivateAllocation():
                assert self.allocated
                self.allocated = False
            case TruncateAllocation(on=on):
                assert self.allocated
                assert self.facts.move_in < on <= india_date(self.now)
            case SetHoldExpiry(at=at):
                self.facts = replace(self.facts, hold_expires_at=self.deadline(at))
            case SetConfirmDeadline(at=at):
                self.facts = replace(self.facts, confirm_by=self.deadline(at))
            case SetCheckWindowEnd(at=at):
                self.facts = replace(self.facts, check_window_ends_at=self.deadline(at))
            case RecordTokenReceived():
                self.kept += 1
            case RefundToken() | ApplyLateCancelPolicy():
                assert self.kept == 1
                self.kept -= 1
            case EarnToken():
                assert self.kept == 1
                self.kept -= 1
                self.earned += 1
            case IssueOwnerInvoice():
                self.invoices += 1
            case _:
                pass

    def deadline(self, at: datetime) -> datetime:
        # Countdowns only for a real deadline, still to come (rule 7).
        assert at > self.now
        return at


# How a booking goes when all is well (§7.1), with the other ends of a move-in, a dispute and a
# late payment.
FORWARD: dict[BookingStatus, list[BookingEvent]] = {
    S.HELD: [E.TOKEN_SECURED],
    S.TOKEN_SECURED: [E.CONFIRM],
    S.CONFIRMED: [E.CHECK_IN, E.NO_SHOW],
    S.CHECKED_IN: [E.WINDOW_ELAPSED, E.DISPUTE],
    S.DISPUTED: [E.RESOLVE_UPHOLD, E.RESOLVE_REFUND],
    S.ACTIVE: [E.MOVE_OUT],
    S.EXPIRED: [E.LATE_PAYMENT_REVIVE, E.LATE_PAYMENT_REFUND],
}


# A step of a history: the time that passes, which events to pick from (the way forward, those
# the status takes, or any from anyone), which of them and who sends it, and what comes with it:
# the amount paid, whether the bed is free, and the move-out day (none, the move-in, today or
# yesterday). Each step is one draw from them all, which keeps 10,000 histories quick in CI.
STEP = st.sampled_from(
    list(
        product(
            STEPS,
            ["forward", "forward", "takes", "anything"],
            range(len(E)),
            range(len(P)),
            [TOKEN, TOKEN - 1, None],
            [True, False, None],
            range(4),
        )
    )
)
type Step = tuple[timedelta, str, int, int, int | None, bool | None, int]


@given(
    days_ahead=st.integers(0, 20),
    instant_confirm=st.booleans(),
    history=st.lists(STEP, min_size=10, max_size=40),
)
def test_random_histories_never_break_the_rules(
    days_ahead: int, instant_confirm: bool, history: list[Step]
) -> None:
    booking = Booking(
        move_in=NOW.date() + timedelta(days=days_ahead), instant_confirm=instant_confirm
    )
    for wait, how, which, who, paid, bed_free, moved_out in history:
        booking.now += wait
        today = india_date(booking.now)
        status = booking.facts.status
        takes = sorted(event for each, event in SPEC if each is status)
        if how == "forward" and status in FORWARD:
            events = FORWARD[status]
        elif how == "takes" and takes:
            events = takes
        else:
            events = list(E)
        event = events[which % len(events)]
        allowed = SPEC.get((status, event))
        senders = sorted(P) if how == "anything" or allowed is None else sorted(allowed[1])
        moment = Moment(
            booking.now,
            paid_paise=paid,
            bed_free=bed_free,
            moved_out_on=[None, booking.facts.move_in, today, today - timedelta(days=1)][moved_out],
        )
        booking.send(event, senders[who % len(senders)], moment)
        if booking.facts.status in FINAL:
            assert not any(booking.send(*each, moment) for each in product(E, P))
            break
