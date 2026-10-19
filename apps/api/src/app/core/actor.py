"""Who is acting: the signed-in user, as every module's policies see them (ARCHITECTURE §12).

The identity module builds an ``Actor`` from the session cookie. Policies elsewhere
(``can(actor, action, resource)``) depend only on this type, not on the identity module's tables.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import uuid


class Role(StrEnum):
    STUDENT = "student"
    PARENT = "parent"
    OWNER = "owner"
    FIELD_AGENT = "field_agent"
    OPS = "ops"
    ADMIN = "admin"


# Staff sign in with Google (step 1.3) and get shorter sessions.
STAFF_ROLES: Final = frozenset({Role.FIELD_AGENT, Role.OPS, Role.ADMIN})


@dataclass(frozen=True)
class Actor:
    """A signed-in user and the session they are using."""

    user_id: int
    user_public_id: uuid.UUID
    roles: frozenset[Role]
    session_id: int
    session_public_id: uuid.UUID

    def has_role(self, role: Role) -> bool:
        return role in self.roles

    @property
    def is_staff(self) -> bool:
        return not self.roles.isdisjoint(STAFF_ROLES)
