import uuid

import pytest

from app.core.actor import Actor, Role
from app.modules.identity.policies import can_end_session, can_list_staff


def _actor(*roles: Role, user_id: int = 1) -> Actor:
    return Actor(
        user_id=user_id,
        user_public_id=uuid.uuid7(),
        roles=frozenset(roles),
        session_id=10,
        session_public_id=uuid.uuid7(),
    )


def test_people_end_only_their_own_sessions_whatever_their_roles() -> None:
    assert can_end_session(_actor(Role.STUDENT, user_id=1), session_user_id=1)
    assert not can_end_session(_actor(Role.STUDENT, user_id=1), session_user_id=2)
    assert not can_end_session(_actor(Role.ADMIN, user_id=1), session_user_id=2)


@pytest.mark.parametrize("role", list(Role))
def test_only_admins_see_the_staff_list(role: Role) -> None:
    assert can_list_staff(_actor(role)) == (role is Role.ADMIN)


def test_without_any_role_nothing_staff_only_is_allowed() -> None:
    assert not can_list_staff(_actor())
