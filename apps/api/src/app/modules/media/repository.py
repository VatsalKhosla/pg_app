"""Media persistence. Repositories never commit; the service owns the transaction."""

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.modules.media.models import MediaAsset

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection

    from sqlalchemy.ext.asyncio import AsyncSession


class MediaRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, asset: MediaAsset) -> MediaAsset:
        self._db.add(asset)
        await self._db.flush()
        return asset

    async def get(self, public_id: uuid.UUID, *, lock: bool = False) -> MediaAsset | None:
        query = select(MediaAsset).where(MediaAsset.public_id == public_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def many(self, public_ids: Collection[uuid.UUID]) -> list[MediaAsset]:
        found = await self._db.scalars(
            select(MediaAsset).where(MediaAsset.public_id.in_(public_ids))
        )
        return list(found)

    async def by_ids(self, ids: Collection[int]) -> list[MediaAsset]:
        found = await self._db.scalars(select(MediaAsset).where(MediaAsset.id.in_(ids)))
        return list(found)
