"""The current actor, for the routes of every module (ARCHITECTURE §12).

``CurrentActor`` is the signed-in user, and answers 401 without a live session. ``OptionalActor``
is None instead, for routes anyone may call that tell a signed-in user more. Modules depend on
this, never on the identity module: the composition root (app/main.py) sets
``app.state.authenticate`` to the identity module's session check.

Authorization is then up to each route: it asks one of its module's policy functions and raises
ForbiddenError (403) for a role the session doesn't carry, or NotFoundError (404) for someone
else's record, so nobody learns it exists.
"""

from typing import TYPE_CHECKING, Annotated, Protocol

from fastapi import Depends, Request, Response

from app.core.actor import Actor
from app.core.clock import ClockDep
from app.core.db import DbSession
from app.core.errors import UnauthenticatedError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock


class Authenticate(Protocol):
    async def __call__(
        self, request: Request, response: Response, *, db: AsyncSession, clock: Clock
    ) -> Actor | None:
        """The actor behind the request's session, or None. May send the session cookie again
        on ``response`` when its expiry moves."""
        ...


async def get_optional_actor(
    request: Request, response: Response, db: DbSession, clock: ClockDep
) -> Actor | None:
    authenticate: Authenticate = request.app.state.authenticate
    return await authenticate(request, response, db=db, clock=clock)


OptionalActor = Annotated[Actor | None, Depends(get_optional_actor)]


async def get_actor(actor: OptionalActor) -> Actor:
    if actor is None:
        raise UnauthenticatedError
    return actor


CurrentActor = Annotated[Actor, Depends(get_actor)]
