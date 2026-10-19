"""Queries on the compliance tables. Repositories never commit; services own transactions."""

from typing import TYPE_CHECKING

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from app.core.ids import new_public_id
from app.modules.compliance.domain.requests import DataRequestKind, DataRequestStatus
from app.modules.compliance.models import OPEN_REQUEST, DataExport, DataRequest

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


class DataRequestRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def insert_open(
        self, user_id: int, kind: DataRequestKind, *, now: datetime
    ) -> DataRequest | None:
        """A new open request, or None if the person already has one of this kind open."""
        return await self._db.scalar(
            insert(DataRequest)
            .values(
                public_id=new_public_id(),
                user_id=user_id,
                kind=kind,
                status=DataRequestStatus.RECEIVED,
                requested_at=now,
            )
            .on_conflict_do_nothing(
                # The open-request index's own predicate, word for word: a bound parameter in
                # its place wouldn't match the partial index.
                index_elements=[DataRequest.user_id, DataRequest.kind],
                index_where=text(OPEN_REQUEST),
            )
            .returning(DataRequest)
        )

    async def open_for(self, user_id: int, kind: DataRequestKind) -> DataRequest | None:
        return await self._db.scalar(
            select(DataRequest).where(
                DataRequest.user_id == user_id,
                DataRequest.kind == kind,
                DataRequest.status == DataRequestStatus.RECEIVED,
            )
        )

    async def by_public_id(
        self, public_id: uuid.UUID, *, for_update: bool = False
    ) -> DataRequest | None:
        query = select(DataRequest).where(DataRequest.public_id == public_id)
        return await self._db.scalar(query.with_for_update() if for_update else query)

    async def by_id(self, request_id: int, *, for_update: bool = False) -> DataRequest | None:
        query = select(DataRequest).where(DataRequest.id == request_id)
        return await self._db.scalar(query.with_for_update() if for_update else query)

    async def for_user(self, user_id: int) -> list[DataRequest]:
        rows = await self._db.scalars(
            select(DataRequest)
            .where(DataRequest.user_id == user_id)
            .order_by(DataRequest.public_id)
        )
        return list(rows)

    async def page(
        self,
        *,
        user_id: int | None = None,
        status: DataRequestStatus | None = None,
        after: uuid.UUID | None,
        limit: int,
    ) -> list[DataRequest]:
        """Requests in public-id order (oldest first), ``limit + 1`` at most."""
        query = select(DataRequest).order_by(DataRequest.public_id).limit(limit + 1)
        if user_id is not None:
            query = query.where(DataRequest.user_id == user_id)
        if status is not None:
            query = query.where(DataRequest.status == status)
        if after is not None:
            query = query.where(DataRequest.public_id > after)
        return list(await self._db.scalars(query))

    async def exports_past(self, now: datetime) -> list[DataRequest]:
        """Ready exports whose file should be deleted by now, locked for update."""
        rows = await self._db.scalars(
            select(DataRequest)
            .where(
                DataRequest.kind == DataRequestKind.EXPORT,
                DataRequest.status == DataRequestStatus.READY,
                DataRequest.expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        return list(rows)


class DataExportRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def put(self, data_request_id: int, content: bytes) -> None:
        await self._db.execute(
            insert(DataExport)
            .values(data_request_id=data_request_id, content=content)
            .on_conflict_do_update(
                index_elements=[DataExport.data_request_id], set_={"content": content}
            )
        )

    async def content(self, data_request_id: int) -> bytes | None:
        return await self._db.scalar(
            select(DataExport.content).where(DataExport.data_request_id == data_request_id)
        )

    async def delete_for(self, data_request_ids: Iterable[int]) -> int:
        ids = list(data_request_ids)
        if not ids:
            return 0
        deleted = await self._db.scalars(
            delete(DataExport).where(DataExport.data_request_id.in_(ids)).returning(DataExport.id)
        )
        return len(deleted.all())
