import io
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.core.audit import Actor, AuditLog, record
from app.core.clock import FrozenClock
from app.core.flags import FLAGS, FeatureFlag, FeatureFlags, Flag, set_flag
from app.manage import main

if TYPE_CHECKING:
    from tests.integration.conftest import RunDb, Sessionmaker

pytestmark = pytest.mark.integration

START = datetime(2027, 7, 1, 4, 30, tzinfo=UTC)


async def _record_one(sessionmaker: Sessionmaker, entity: str) -> None:
    async with sessionmaker() as session, session.begin():
        await record(
            session,
            clock=FrozenClock(START),
            actor=Actor("staff", 7),
            action="refund.approve",
            entity_type="refund",
            entity_id=entity,
            details={"note": "called +919876543210", "amountPaise": 200_000},
            request_id="web-0192f6d4",
            ip_address="203.0.113.7",
        )


def test_audit_entries_are_written_with_phone_numbers_masked(run_db: RunDb) -> None:
    entity = f"rf-{uuid.uuid4().hex}"

    async def scenario(sessionmaker: Sessionmaker) -> AuditLog:
        await _record_one(sessionmaker, entity)
        async with sessionmaker() as session:
            query = select(AuditLog).where(AuditLog.entity_id == entity)
            return (await session.scalars(query)).one()

    entry = run_db(scenario)

    assert (entry.actor_type, entry.actor_id, entry.action) == ("staff", 7, "refund.approve")
    assert entry.occurred_at == START
    assert entry.details == {"note": "called ******3210", "amountPaise": 200_000}
    assert str(entry.ip_address) == "203.0.113.7"


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_logs SET action = 'tampered' WHERE entity_id = :entity",
        "DELETE FROM audit_logs WHERE entity_id = :entity",
        "TRUNCATE audit_logs",
    ],
)
def test_the_database_refuses_to_change_or_remove_audit_entries(
    run_db: RunDb, statement: str
) -> None:
    entity = f"rf-{uuid.uuid4().hex}"

    async def scenario(sessionmaker: Sessionmaker) -> tuple[str, str]:
        await _record_one(sessionmaker, entity)
        async with sessionmaker() as session:
            parameters = {"entity": entity} if ":entity" in statement else {}
            with pytest.raises(DBAPIError) as refused:
                await session.execute(text(statement), parameters)
            await session.rollback()
            remaining = (
                await session.scalars(select(AuditLog.action).where(AuditLog.entity_id == entity))
            ).one()
        return str(refused.value), remaining

    error, remaining = run_db(scenario)

    assert "audit_logs is append-only" in error
    assert remaining == "refund.approve"


@pytest.fixture
def restore_flags(run_db: RunDb) -> Iterator[None]:
    yield

    async def reset(sessionmaker: Sessionmaker) -> None:
        async with sessionmaker() as session, session.begin():
            for flag, spec in FLAGS.items():
                await session.execute(
                    update(FeatureFlag)
                    .where(FeatureFlag.key == flag.value)
                    .values(value=spec.default)
                )

    run_db(reset)


async def _store(sessionmaker: Sessionmaker, flag: Flag, value: object) -> None:
    async with sessionmaker() as session, session.begin():
        await session.execute(
            update(FeatureFlag).where(FeatureFlag.key == flag.value).values(value=value)
        )


def test_the_seeded_flags_are_the_declared_defaults(run_db: RunDb) -> None:
    async def scenario(sessionmaker: Sessionmaker) -> dict[str, object]:
        async with sessionmaker() as session:
            rows = await session.execute(select(FeatureFlag.key, FeatureFlag.value))
            return {row.key: row.value for row in rows.all()}

    assert run_db(scenario) == {flag.value: spec.default for flag, spec in FLAGS.items()}


def test_flag_changes_show_once_the_cache_expires(run_db: RunDb, restore_flags: None) -> None:
    clock = FrozenClock(START)

    async def scenario(sessionmaker: Sessionmaker) -> tuple[bool, bool, bool]:
        flags = FeatureFlags(sessionmaker, clock)
        before = await flags.is_enabled(Flag.REVIEWS_ENABLED)
        await _store(sessionmaker, Flag.REVIEWS_ENABLED, value=True)
        cached = await flags.is_enabled(Flag.REVIEWS_ENABLED)
        clock.advance(timedelta(seconds=31))
        return before, cached, await flags.is_enabled(Flag.REVIEWS_ENABLED)

    assert run_db(scenario) == (False, False, True)


def test_a_stored_value_of_the_wrong_type_falls_back_to_the_default(
    run_db: RunDb, restore_flags: None
) -> None:
    async def scenario(sessionmaker: Sessionmaker) -> tuple[str, bool]:
        await _store(sessionmaker, Flag.TOKEN_MODE, "cash")
        await _store(sessionmaker, Flag.HIDE_OWNER_CONTACT, "no")
        flags = FeatureFlags(sessionmaker, FrozenClock(START))
        return await flags.choice(Flag.TOKEN_MODE), await flags.is_enabled(Flag.HIDE_OWNER_CONTACT)

    assert run_db(scenario) == ("payment", True)


def test_an_operator_sets_a_flag_with_an_audit_entry_and_a_restart_adds_no_more(
    make_settings: Callable[..., Settings],
    database_url: str,
    run_db: RunDb,
    restore_flags: None,
) -> None:
    settings = make_settings(database_url=database_url)
    clock = FrozenClock(START)

    def manage(*args: str) -> tuple[int, str]:
        out = io.StringIO()
        code = main(["flags", "set", *args], settings=settings, clock=clock, out=out)
        return code, out.getvalue()

    async def audited(sessionmaker: Sessionmaker) -> list[dict[str, object]]:
        async with sessionmaker() as session:
            rows = await session.scalars(
                select(AuditLog.details)
                .where(AuditLog.entity_id == "reviews_enabled", AuditLog.occurred_at == START)
                .order_by(AuditLog.id)
            )
            return list(rows)

    async def current(sessionmaker: Sessionmaker) -> bool:
        return await FeatureFlags(sessionmaker, clock).is_enabled(Flag.REVIEWS_ENABLED)

    assert manage("reviews_enabled", "true") == (0, "reviews_enabled is true.\n")
    assert run_db(current) is True
    assert manage("reviews_enabled", "true") == (0, "reviews_enabled was true already.\n")
    assert manage("reviews_enabled", "maybe") == (
        1,
        "Not done: reviews_enabled doesn't take 'maybe'.\n",
    )
    assert manage("token_mode", "nonsense") == (
        1,
        "Not done: token_mode doesn't take 'nonsense'.\n",
    )
    assert manage("reviews_enabled", "false") == (0, "reviews_enabled is false.\n")
    assert run_db(current) is False
    assert run_db(audited) == [{"from": False, "to": True}, {"from": True, "to": False}]


def test_a_flag_with_no_row_gets_one_when_its_set(run_db: RunDb, restore_flags: None) -> None:
    async def scenario(sessionmaker: Sessionmaker) -> tuple[bool, object]:
        async with sessionmaker() as session, session.begin():
            await session.execute(delete(FeatureFlag).where(FeatureFlag.key == "reviews_enabled"))
        async with sessionmaker() as session, session.begin():
            changed = await set_flag(session, Flag.REVIEWS_ENABLED, False, clock=FrozenClock(START))
        async with sessionmaker() as session:
            value = await session.scalar(
                select(FeatureFlag.value).where(FeatureFlag.key == "reviews_enabled")
            )
        return changed, value

    assert run_db(scenario) == (True, False)
