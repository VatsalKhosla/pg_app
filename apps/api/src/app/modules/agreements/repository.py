"""The agreements module's queries, on its own tables only (ADR 0070). Nothing here commits."""

from typing import TYPE_CHECKING

from sqlalchemy import delete, func, or_, select, update

from app.modules.agreements.models import (
    AgreementSignature,
    RentalAgreement,
    SigningCode,
    TenantVerification,
)

if TYPE_CHECKING:
    from collections.abc import Collection
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


class AgreementRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, agreement: RentalAgreement) -> RentalAgreement:
        self._db.add(agreement)
        await self._db.flush()
        return agreement

    async def of_booking(self, booking_id: int, *, lock: bool = False) -> RentalAgreement | None:
        """The booking's agreement. A locked read is about the row as it is now, not a copy this
        session read before the lock."""
        query = select(RentalAgreement).where(RentalAgreement.booking_id == booking_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return await self._db.scalar(query)

    async def of_student(self, user_id: int) -> list[RentalAgreement]:
        rows = await self._db.scalars(
            select(RentalAgreement)
            .where(RentalAgreement.student_id == user_id)
            .order_by(RentalAgreement.id)
        )
        return list(rows)

    async def by_ids(self, agreement_ids: Collection[int]) -> dict[int, RentalAgreement]:
        if not agreement_ids:
            return {}
        rows = await self._db.scalars(
            select(RentalAgreement).where(RentalAgreement.id.in_(agreement_ids))
        )
        return {row.id: row for row in rows}

    # Signatures.

    async def sign(self, signature: AgreementSignature) -> None:
        self._db.add(signature)
        await self._db.flush()

    async def signatures_of(self, agreement_id: int) -> list[AgreementSignature]:
        rows = await self._db.scalars(
            select(AgreementSignature)
            .where(AgreementSignature.agreement_id == agreement_id)
            .order_by(AgreementSignature.signed_at, AgreementSignature.id)
        )
        return list(rows)

    async def signatures_by(self, user_id: int) -> list[AgreementSignature]:
        rows = await self._db.scalars(
            select(AgreementSignature)
            .where(AgreementSignature.user_id == user_id)
            .order_by(AgreementSignature.id)
        )
        return list(rows)

    # Signing codes.

    def add_code(self, code: SigningCode) -> None:
        self._db.add(code)

    async def last_requested_at(self, agreement_id: int, user_id: int) -> datetime | None:
        return await self._db.scalar(
            select(func.max(SigningCode.requested_at)).where(
                SigningCode.agreement_id == agreement_id, SigningCode.user_id == user_id
            )
        )

    async def supersede_open(
        self, agreement_id: int, user_id: int, *, signer: str, now: datetime
    ) -> None:
        await self._db.execute(
            update(SigningCode)
            .where(
                SigningCode.agreement_id == agreement_id,
                SigningCode.user_id == user_id,
                SigningCode.signer == signer,
                SigningCode.consumed_at.is_(None),
                SigningCode.superseded_at.is_(None),
            )
            .values(superseded_at=now)
        )

    async def latest_code(
        self, agreement_id: int, user_id: int, *, signer: str
    ) -> SigningCode | None:
        """The newest code this person asked for to sign as ``signer``, locked."""
        return await self._db.scalar(
            select(SigningCode)
            .where(
                SigningCode.agreement_id == agreement_id,
                SigningCode.user_id == user_id,
                SigningCode.signer == signer,
            )
            .order_by(SigningCode.requested_at.desc(), SigningCode.id.desc())
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def delete_code(self, code_id: int) -> None:
        await self._db.execute(delete(SigningCode).where(SigningCode.id == code_id))

    async def delete_codes_requested_before(self, before: datetime) -> int:
        deleted = await self._db.scalars(
            delete(SigningCode).where(SigningCode.requested_at < before).returning(SigningCode.id)
        )
        return len(deleted.all())

    # Police verification.

    async def add_verification(self, verification: TenantVerification) -> None:
        self._db.add(verification)
        await self._db.flush()

    async def verification_of(
        self, agreement_id: int, *, lock: bool = False
    ) -> TenantVerification | None:
        query = select(TenantVerification).where(TenantVerification.agreement_id == agreement_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return await self._db.scalar(query)

    async def verifications_of(
        self, agreement_ids: Collection[int]
    ) -> dict[int, TenantVerification]:
        if not agreement_ids:
            return {}
        rows = await self._db.scalars(
            select(TenantVerification).where(TenantVerification.agreement_id.in_(agreement_ids))
        )
        return {row.agreement_id: row for row in rows}

    async def erase_details(
        self, *, verified_before: datetime, ended_before: datetime, now: datetime
    ) -> int:
        """Retention: forget the sealed details of verifications the police finished before
        ``verified_before``, or whose booking ended before ``ended_before``."""
        ended = select(RentalAgreement.id).where(RentalAgreement.booking_ended_at < ended_before)
        erased = await self._db.scalars(
            update(TenantVerification)
            .where(
                TenantVerification.details_sealed.is_not(None),
                or_(
                    TenantVerification.verified_at < verified_before,
                    TenantVerification.agreement_id.in_(ended),
                ),
            )
            .values(details_sealed=None, erased_at=now)
            .returning(TenantVerification.id)
        )
        return len(erased.all())
