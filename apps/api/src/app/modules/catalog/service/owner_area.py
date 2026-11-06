"""The owner's side of a listing (Phase 7, ADR 0063): their PGs, the licence and society permission
they upload for each, and how often each PG's page is opened.

Documents are private media: an owner sees their own, ops see every PG's and say whether each is
good. A page view is counted per PG per day in India, one row a day however busy the page.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core import audit
from app.core.calendar import india_date
from app.core.errors import InvalidTransitionError, NotFoundError
from app.modules.catalog.domain.documents import DocumentKind, DocumentStatus
from app.modules.catalog.domain.listing import PropertyStatus, VerificationStatus, is_public
from app.modules.catalog.errors import DocumentInvalidError
from app.modules.catalog.models import PropertyDocument
from app.modules.catalog.repository import CatalogRepository
from app.modules.catalog.service.lookup import CatalogLookup
from app.modules.media.domain.assets import AssetStatus, Purpose
from app.modules.media.service import MediaLookup

if TYPE_CHECKING:
    import uuid
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.modules.media.ports import ObjectStorage
    from app.modules.media.service import Buckets, MediaRef


@dataclass(frozen=True, slots=True)
class DocumentView:
    public_id: uuid.UUID
    kind: DocumentKind
    status: DocumentStatus
    added_at: datetime
    reviewed_at: datetime | None
    note: str | None
    # Each signed for 5 minutes; none while the file is still being checked.
    files: tuple[tuple[str, str], ...]


class PropertyDocuments:
    def __init__(
        self, db: AsyncSession, clock: Clock, buckets: Buckets, storage: ObjectStorage | None
    ) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogRepository(db)
        self._lookup = CatalogLookup(db)
        self._media = MediaLookup(db, buckets, storage=storage)

    async def mine(self, actor: Actor, property_id: uuid.UUID) -> list[DocumentView]:
        """The owner's own PG's documents, newest first; anyone else's PG is a 404."""
        async with self._db.begin():
            owned = await self._lookup.owned_property(actor.user_id, property_id)
            if owned is None:
                raise NotFoundError
            return await self._views(await self._catalog.documents_of(owned.id))

    async def add(
        self, actor: Actor, property_id: uuid.UUID, *, kind: DocumentKind, media: uuid.UUID
    ) -> DocumentView:
        """The owner's own upload, finished, as one of their PG's documents. 422 DOCUMENT_INVALID
        for a file that isn't theirs, isn't a document, or was rejected. Audited."""
        async with self._db.begin():
            owned = await self._lookup.owned_property(actor.user_id, property_id)
            if owned is None:
                raise NotFoundError
            ref = (await self._media.by_public_id({media})).get(media)
            if ref is None or ref.uploaded_by != actor.user_id:
                raise DocumentInvalidError([f"no such file: {media}"])
            if ref.purpose is not Purpose.DOCUMENT:
                raise DocumentInvalidError([f"{media} wasn't uploaded as a document"])
            if ref.status is AssetStatus.REJECTED:
                raise DocumentInvalidError([f"{media} was refused as a file"])
            document = PropertyDocument(
                property_id=owned.id,
                kind=kind,
                media_asset_id=ref.id,
                uploaded_by=actor.user_id,
                added_at=self._clock.now(),
                status=DocumentStatus.SUBMITTED,
            )
            await self._catalog.add_document(document)
            await self._record(actor, document, "property_document.added")
            return (await self._views([document]))[0]

    async def for_ops(self, property_id: uuid.UUID) -> list[DocumentView]:
        async with self._db.begin():
            found = await self._catalog.property(property_id)
            if found is None:
                raise NotFoundError
            return await self._views(await self._catalog.documents_of(found.id))

    async def review(
        self, actor: Actor, document_id: uuid.UUID, *, accepted: bool, note: str
    ) -> DocumentView:
        """Ops' word on a document, once: 409 INVALID_TRANSITION if it has one. Audited."""
        async with self._db.begin():
            document = await self._catalog.document(document_id, lock=True)
            if document is None:
                raise NotFoundError
            if document.status != DocumentStatus.SUBMITTED:
                raise InvalidTransitionError("This document has been looked at already.")
            document.status = DocumentStatus.ACCEPTED if accepted else DocumentStatus.REJECTED
            document.reviewed_by = actor.user_id
            document.reviewed_at = self._clock.now()
            document.note = note.strip() or None
            await self._record(actor, document, f"property_document.{document.status}")
            return (await self._views([document]))[0]

    async def _views(self, rows: list[PropertyDocument]) -> list[DocumentView]:
        refs = await self._media.by_id({row.media_asset_id for row in rows})
        return [_view(row, refs.get(row.media_asset_id)) for row in rows]

    async def _record(self, actor: Actor, document: PropertyDocument, action: str) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.by(actor),
            action=action,
            entity_type="property_document",
            entity_id=str(document.public_id),
            details={"kind": document.kind, "note": document.note or ""},
        )


def _view(row: PropertyDocument, ref: MediaRef | None) -> DocumentView:
    files = () if ref is None else tuple((each.content_type, each.url) for each in ref.renditions)
    return DocumentView(
        public_id=row.public_id,
        kind=DocumentKind(row.kind),
        status=DocumentStatus(row.status),
        added_at=row.added_at,
        reviewed_at=row.reviewed_at,
        note=row.note,
        files=files,
    )


class ListingViews:
    """Counting a PG page's views, and reading them back."""

    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogRepository(db)

    async def count(self, slug: str) -> None:
        """One view of a live PG's page; any other is a 404."""
        async with self._db.begin():
            found = await self._catalog.property_by_slug(slug)
            if found is None or not is_public(
                PropertyStatus(found.status),
                VerificationStatus(found.verification_status),
                verified_only=False,
            ):
                raise NotFoundError
            await self._catalog.count_view(found.id, india_date(self._clock.now()))

    async def between(self, property_id: int, first: date, last: date) -> int:
        """Views from ``first`` to ``last``, both days in India, in the caller's transaction."""
        return await self._catalog.views_between(property_id, first, last)
