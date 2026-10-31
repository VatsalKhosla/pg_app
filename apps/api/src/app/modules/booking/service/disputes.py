"""Disputes as ops settle them (step 5.7, ADR 0051). Each method is one transaction.

A student opens one from their booking (BookingService.dispute): inside their time to check the
room, why it isn't as shown, in their own words, with their own photos. Ops find it in their
queue, look into it, and refund it (`resolve_refund`: the bed released, the token refunded in
full, help to book again) or uphold it (`resolve_uphold`: the stay goes ahead and the token is
earned), with a note for the record.

The dispute's own row goes with the booking's change, in the same transaction: it is what the
state machine's OpenDispute and CloseDispute ask for.
"""

from typing import TYPE_CHECKING

from app.core.errors import NotFoundError
from app.core.pagination import split_page
from app.modules.booking.domain.disputes import (
    DisputeOutcome,
    DisputeReason,
    DisputeStatus,
    photo_problems,
    resolved,
)
from app.modules.booking.domain.state_machine import BookingEvent, CloseDispute, Party
from app.modules.booking.errors import DisputeInvalidError
from app.modules.booking.repository import BookingRepository, DisputeRepository
from app.modules.booking.schemas import BookingPlace as PlaceSchema
from app.modules.booking.schemas import (
    DisputePhotoView,
    DisputeStudent,
    OpsDispute,
    OpsDisputeItem,
    PhotoSize,
)
from app.modules.booking.service.transitions import Transitions
from app.modules.booking.service.views import BookingViews
from app.modules.catalog.service import CatalogLookup
from app.modules.identity.service import Accounts
from app.modules.media.domain.assets import AssetStatus, Purpose
from app.modules.media.service import MediaLookup

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.pagination import PageRequest
    from app.modules.booking.models import Dispute
    from app.modules.media.ports import ObjectStorage
    from app.modules.media.service import Buckets, MediaRef


class Disputes:
    def __init__(
        self, db: AsyncSession, clock: Clock, *, buckets: Buckets, storage: ObjectStorage
    ) -> None:
        self._db = db
        self._clock = clock
        self._bookings = BookingRepository(db)
        self._disputes = DisputeRepository(db)
        self._transitions = Transitions(db, clock)
        self._views = BookingViews(db)
        self._catalog = CatalogLookup(db)
        self._accounts = Accounts(db)
        # With storage: the photos are private, and only ops are shown them (behind links signed
        # for five minutes).
        self._media = MediaLookup(db, buckets, storage=storage)

    async def page(
        self, request: PageRequest, *, status: DisputeStatus | None
    ) -> tuple[list[OpsDisputeItem], uuid.UUID | None]:
        """Ops' queue: oldest first, of one status if asked. The same few queries, however long
        the page."""
        async with self._db.begin():
            found = await self._disputes.page(
                status=status, after=request.after, limit=request.limit
            )
            items, next_cursor = split_page(found, request, cursor_of=lambda row: row.public_id)
            bookings = await self._bookings.by_ids({dispute.booking_id for dispute in items})
            places = await self._catalog.booking_places(
                {booking.property_id for booking in bookings.values()}, verified_only=False
            )
            photos = await self._disputes.photo_counts({dispute.id for dispute in items})
        views = []
        for dispute in items:
            booking = bookings[dispute.booking_id]
            place = places[booking.property_id]
            views.append(
                OpsDisputeItem(
                    id=dispute.public_id,
                    status=DisputeStatus(dispute.status),
                    reason=DisputeReason(dispute.reason),
                    opened_at=dispute.created_at,
                    booking=booking.code,
                    property=PlaceSchema(slug=place.slug, name=place.name, locality=place.locality),
                    photos=photos.get(dispute.id, 0),
                )
            )
        return views, next_cursor

    async def view(self, dispute_id: uuid.UUID) -> OpsDispute:
        async with self._db.begin():
            dispute = await self._disputes.by_public_id(dispute_id)
            if dispute is None:
                raise NotFoundError
            return await self._ops_view(dispute)

    async def resolve(
        self, actor: Actor, dispute_id: uuid.UUID, *, outcome: DisputeOutcome, notes: str
    ) -> OpsDispute:
        """Ops settle it: refunded, or upheld. 409 INVALID_TRANSITION once it's settled."""
        async with self._db.begin():
            dispute = await self._disputes.by_public_id(dispute_id)
            if dispute is None:
                raise NotFoundError
            # The booking's lock settles one answer at a time: a second finds it settled.
            booking = await self._bookings.by_id(dispute.booking_id, lock=True)
            if booking is None:  # pragma: no cover - a dispute always has its booking
                raise NotFoundError
            place = await self._views.place(booking)
            refund = outcome is DisputeOutcome.REFUND
            event = BookingEvent.RESOLVE_REFUND if refund else BookingEvent.RESOLVE_UPHOLD
            step = await self._transitions.apply(
                booking, event, Party.OPS, place, by=actor.user_id, note=notes.strip()
            )
            assert CloseDispute(refunded=refund) in step.effects  # noqa: S101 - the machine's rule
            dispute.status = resolved(outcome)
            dispute.resolved_at = self._clock.now()
            dispute.resolved_by = actor.user_id
            dispute.notes = notes.strip()
            await self._db.flush()
            return await self._ops_view(dispute)

    async def _ops_view(self, dispute: Dispute) -> OpsDispute:
        booking = await self._bookings.by_id(dispute.booking_id)
        if booking is None:  # pragma: no cover - a dispute always has its booking
            raise NotFoundError
        student = (await self._accounts.many([booking.student_id]))[booking.student_id]
        ordered = await self._disputes.photos_of(dispute.id)
        media = await self._media.by_id(ordered)
        return OpsDispute(
            id=dispute.public_id,
            status=DisputeStatus(dispute.status),
            reason=DisputeReason(dispute.reason),
            description=dispute.description,
            opened_at=dispute.created_at,
            resolved_at=dispute.resolved_at,
            notes=dispute.notes,
            booking=await self._views.managed(booking, await self._views.place(booking)),
            student=DisputeStudent(name=student.name, phone=student.phone_e164),
            photos=[_photo(media[media_id]) for media_id in ordered if media_id in media],
        )


def _photo(ref: MediaRef) -> DisputePhotoView:
    return DisputePhotoView(
        id=ref.public_id,
        captured_at=ref.captured_at,
        sizes=[
            PhotoSize(
                name=rendition.name,
                content_type=rendition.content_type,
                url=rendition.url,
                width=rendition.width,
                height=rendition.height,
            )
            for rendition in ref.renditions
        ],
    )


async def own_photos(media: MediaLookup, actor: Actor, photos: Sequence[uuid.UUID]) -> list[int]:
    """A report's photos as media asset ids, in the student's order. Each must be the student's
    own dispute photo and ready (422 DISPUTE_INVALID otherwise)."""
    problems = photo_problems([str(photo) for photo in photos])
    refs = await media.by_public_id(set(photos))
    for photo in photos:
        ref = refs.get(photo)
        if ref is None or ref.uploaded_by != actor.user_id:
            problems.append(f"no such photo: {photo}")
        elif ref.purpose is not Purpose.DISPUTE_PHOTO:
            problems.append(f"{photo} isn't a photo for a report")
        elif ref.status is not AssetStatus.READY:
            problems.append(f"{photo} is {ref.status}")
    if problems:
        raise DisputeInvalidError(problems)
    return [refs[photo].id for photo in photos]
