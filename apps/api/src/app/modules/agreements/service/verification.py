"""The tenant's police verification (ADR 0070): the student gives the details the Delhi Police form
asks for, the owner prints them, submits them on the police portal, uploads the acknowledgement and
later says the police have verified the tenant; ops read all of it.

The details are sealed (app/core/sealing.py) for their row before they're stored, and opened only
for the student who gave them, the PG's owner, and ops, who reads them is audited. No identity
document's full number is ever taken: its type and last four characters only, and any text that
holds what looks like an Aadhaar number is refused before it gets here.
"""

import json
from typing import TYPE_CHECKING, Final

from app.core import audit
from app.core.calendar import india_date
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.ids import new_public_id
from app.modules.agreements.domain import verification as police
from app.modules.agreements.domain.agreements import Signer
from app.modules.agreements.domain.verification import (
    PoliceVerificationStatus,
    VerificationEvent,
    VerificationRefusedError,
    advance,
    allowed,
)
from app.modules.agreements.errors import AcknowledgementInvalidError, PoliceDetailsInvalidError
from app.modules.agreements.models import TenantVerification
from app.modules.agreements.repository import AgreementRepository
from app.modules.agreements.schemas import (
    AcknowledgementFile,
    AddressDetails,
    OpsPoliceVerification,
    OwnerPoliceVerification,
    ReferenceDetails,
    StudentPoliceVerification,
    TenancySummary,
    TenantDetails,
)
from app.modules.agreements.service.agreements import RentAgreements
from app.modules.media.domain.assets import AssetStatus, Purpose
from app.modules.media.service import MediaLookup

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.sealing import FieldCipher
    from app.modules.agreements.domain.terms import Tenancy
    from app.modules.agreements.models import RentalAgreement
    from app.modules.agreements.templates import Templates
    from app.modules.booking.service import BookingRecord
    from app.modules.media.ports import ObjectStorage
    from app.modules.media.service import Buckets

ENTITY: Final = "tenant_verification"


def sealing_context(verification: TenantVerification) -> str:
    """What a verification's details are sealed for: its own row, so they open nowhere else."""
    return f"tenant_verification:{verification.public_id}"


def details_view(details: police.TenantDetails) -> TenantDetails:
    address = details.permanent_address
    return TenantDetails(
        full_name=details.full_name,
        parent_name=details.parent_name,
        date_of_birth=details.date_of_birth,
        gender=details.gender,
        phone=details.phone_e164,
        permanent_address=AddressDetails(
            line=address.line,
            city=address.city,
            district=address.district,
            state=address.state,
            pin_code=address.pin_code,
            police_station=address.police_station,
        ),
        occupation=details.occupation,
        institution=details.institution,
        id_type=details.id_type,
        id_last4=details.id_last4,
        references=[
            ReferenceDetails(name=item.name, phone=item.phone_e164, relation=item.relation)
            for item in details.references
        ],
    )


def from_body(body: TenantDetails) -> police.TenantDetails:
    """The domain's details from a validated body."""
    address = body.permanent_address
    return police.TenantDetails(
        full_name=body.full_name,
        parent_name=body.parent_name,
        date_of_birth=body.date_of_birth,
        gender=body.gender,
        phone_e164=body.phone,
        permanent_address=police.Address(
            line=address.line,
            city=address.city,
            district=address.district,
            state=address.state,
            pin_code=address.pin_code,
            police_station=address.police_station,
        ),
        occupation=body.occupation,
        institution=body.institution,
        id_type=body.id_type,
        id_last4=body.id_last4,
        references=tuple(
            police.Reference(name=item.name, phone_e164=item.phone, relation=item.relation)
            for item in body.references
        ),
    )


def tenancy_summary(tenancy: Tenancy) -> TenancySummary:
    return TenancySummary(
        booking=tenancy.booking_code,
        licensor=tenancy.licensor,
        pg_name=tenancy.pg_name,
        pg_address=tenancy.pg_address,
        room=f"Bed {tenancy.bed}, room {tenancy.room} ({tenancy.room_type})",
        move_in=tenancy.move_in,
        planned_move_out=tenancy.planned_move_out,
    )


class PoliceVerifications:
    def __init__(
        self,
        db: AsyncSession,
        clock: Clock,
        *,
        templates: Templates,
        cipher: FieldCipher,
        buckets: Buckets,
        storage: ObjectStorage | None,
    ) -> None:
        self._db = db
        self._clock = clock
        self._cipher = cipher
        self._agreements = RentAgreements(db, clock, templates=templates)
        self._rows = AgreementRepository(db)
        self._media = MediaLookup(db, buckets, storage=storage)

    # The student.

    async def for_student(self, actor: Actor, code: str) -> StudentPoliceVerification:
        async with self._db.begin():
            booking = await self._agreements.booking_of(actor, code, side=Signer.STUDENT)
            agreement, verification = await self._found(booking)
            return self._student_view(booking, agreement, verification)

    async def give_details(
        self, actor: Actor, code: str, body: TenantDetails
    ) -> StudentPoliceVerification:
        """The student's details, given or corrected until the owner submits them. 422
        POLICE_DETAILS_INVALID for what the police form couldn't take."""
        details = from_body(body)
        found = police.problems(details, today=india_date(self._clock.now()))
        if found:
            raise PoliceDetailsInvalidError(found)
        now = self._clock.now()
        async with self._db.begin():
            booking = await self._agreements.booking_of(actor, code, side=Signer.STUDENT)
            current = await self._agreements.ensure(booking)
            if current is None:
                raise NotFoundError
            agreement = current.row
            verification = await self._rows.verification_of(agreement.id, lock=True)
            status = (
                PoliceVerificationStatus.NOT_STARTED
                if verification is None
                else PoliceVerificationStatus(verification.status)
            )
            to = _advance(status, VerificationEvent.GIVE_DETAILS, booking=booking)
            plain = json.dumps(police.to_json(details), ensure_ascii=False, sort_keys=True)
            if verification is None:
                verification = TenantVerification(
                    public_id=new_public_id(),
                    agreement_id=agreement.id,
                    status=to,
                    details_submitted_at=now,
                )
                verification.details_sealed = self._cipher.seal(
                    plain, context=sealing_context(verification)
                )
                await self._rows.add_verification(verification)
            else:
                verification.status = to
                verification.details_sealed = self._cipher.seal(
                    plain, context=sealing_context(verification)
                )
                verification.details_submitted_at = now
                await self._db.flush()
            # What changed, never the details themselves.
            await self._record(
                audit.Actor("user", actor.user_id),
                verification,
                booking,
                "police_verification.details_given",
            )
            return self._student_view(booking, agreement, verification)

    # The owner.

    async def for_owner(self, actor: Actor, code: str) -> OwnerPoliceVerification:
        """The details to copy onto the police portal, with the tenancy; every look is audited."""
        async with self._db.begin():
            booking = await self._agreements.booking_of(actor, code, side=Signer.OWNER)
            agreement, verification = await self._found(booking)
            if verification is not None and verification.details_sealed is not None:
                await self._record(
                    audit.Actor("owner", actor.user_id),
                    verification,
                    booking,
                    "police_verification.details_viewed",
                )
            return await self._owner_view(booking, agreement, verification)

    async def mark_submitted(
        self, actor: Actor, code: str, *, acknowledgement: uuid.UUID, reference: str | None
    ) -> OwnerPoliceVerification:
        """The owner submitted the details on the police portal: the acknowledgement they
        uploaded (their own document), and its number. 422 ACKNOWLEDGEMENT_INVALID for a file
        that isn't theirs, isn't a document, or was refused."""
        now = self._clock.now()
        async with self._db.begin():
            booking = await self._agreements.booking_of(actor, code, side=Signer.OWNER)
            agreement, verification = await self._found(booking, lock=True)
            status = (
                PoliceVerificationStatus.NOT_STARTED
                if verification is None
                else PoliceVerificationStatus(verification.status)
            )
            to = _advance(status, VerificationEvent.SUBMIT_TO_POLICE, booking=booking)
            if verification is None:  # pragma: no cover - refused above
                raise NotFoundError
            ref = (await self._media.by_public_id({acknowledgement})).get(acknowledgement)
            if ref is None or ref.uploaded_by != actor.user_id:
                raise AcknowledgementInvalidError(f"No such file: {acknowledgement}.")
            if ref.purpose is not Purpose.DOCUMENT:
                raise AcknowledgementInvalidError("Upload the acknowledgement as a document.")
            if ref.status is AssetStatus.REJECTED:
                raise AcknowledgementInvalidError("That file was refused; upload it again.")
            verification.status = to
            verification.acknowledgement_media_id = ref.id
            verification.police_reference = None if reference is None else reference.strip()
            verification.submitted_to_police_at = now
            verification.submitted_by = actor.user_id
            await self._db.flush()
            await self._record(
                audit.Actor("owner", actor.user_id),
                verification,
                booking,
                "police_verification.submitted",
                {"reference": verification.police_reference or ""},
            )
            return await self._owner_view(booking, agreement, verification)

    async def mark_verified(self, actor: Actor, code: str) -> OwnerPoliceVerification:
        """The police verified the tenant, as the owner says."""
        now = self._clock.now()
        async with self._db.begin():
            booking = await self._agreements.booking_of(actor, code, side=Signer.OWNER)
            agreement, verification = await self._found(booking, lock=True)
            status = (
                PoliceVerificationStatus.NOT_STARTED
                if verification is None
                else PoliceVerificationStatus(verification.status)
            )
            to = _advance(status, VerificationEvent.MARK_VERIFIED, booking=booking)
            if verification is None:  # pragma: no cover - refused above
                raise NotFoundError
            verification.status = to
            verification.verified_at = now
            verification.verified_by = actor.user_id
            await self._db.flush()
            await self._record(
                audit.Actor("owner", actor.user_id),
                verification,
                booking,
                "police_verification.verified",
            )
            return await self._owner_view(booking, agreement, verification)

    # Ops.

    async def for_ops(self, actor: Actor, code: str) -> OpsPoliceVerification:
        """Everything, read-only; a look at the details is audited."""
        async with self._db.begin():
            booking = await self._agreements.booking_of_anyone(code)
            agreement, verification = await self._found(booking)
            if verification is not None and verification.details_sealed is not None:
                await self._record(
                    audit.Actor("staff", actor.user_id),
                    verification,
                    booking,
                    "police_verification.details_viewed",
                )
            owner = await self._owner_view(booking, agreement, verification)
            return OpsPoliceVerification(
                booking=owner.booking,
                status=owner.status,
                details=owner.details,
                tenancy=owner.tenancy,
                details_submitted_at=owner.details_submitted_at,
                submitted_to_police_at=owner.submitted_to_police_at,
                police_reference=owner.police_reference,
                acknowledgement=owner.acknowledgement,
                verified_at=owner.verified_at,
                erased=owner.erased,
            )

    # Shared.

    async def _found(
        self, booking: BookingRecord, *, lock: bool = False
    ) -> tuple[RentalAgreement | None, TenantVerification | None]:
        """The booking's agreement and verification. A booking without an agreement (never
        confirmed) has no verification either: 404. A confirmed booking whose agreement nobody
        has acted on yet has one that hasn't started."""
        agreement = await self._rows.of_booking(booking.id)
        if agreement is None:
            if not booking.was_confirmed:
                raise NotFoundError
            return None, None
        return agreement, await self._rows.verification_of(agreement.id, lock=lock)

    def _details(self, verification: TenantVerification | None) -> TenantDetails | None:
        if verification is None or verification.details_sealed is None:
            return None
        plain = self._cipher.open(
            verification.details_sealed, context=sealing_context(verification)
        )
        return details_view(police.from_json(json.loads(plain)))

    def _student_view(
        self,
        booking: BookingRecord,
        agreement: RentalAgreement | None,
        verification: TenantVerification | None,
    ) -> StudentPoliceVerification:
        status = _status(verification)
        return StudentPoliceVerification(
            booking=booking.code,
            status=status,
            details=self._details(verification),
            details_submitted_at=None
            if verification is None
            else verification.details_submitted_at,
            submitted_to_police_at=None
            if verification is None
            else verification.submitted_to_police_at,
            police_reference=None if verification is None else verification.police_reference,
            verified_at=None if verification is None else verification.verified_at,
            can_edit=allowed(status, VerificationEvent.GIVE_DETAILS, booking_ended=booking.ended),
            erased=verification is not None and verification.erased_at is not None,
        )

    async def _owner_view(
        self,
        booking: BookingRecord,
        agreement: RentalAgreement | None,
        verification: TenantVerification | None,
    ) -> OwnerPoliceVerification:
        status = _status(verification)
        files: list[AcknowledgementFile] = []
        if verification is not None and verification.acknowledgement_media_id is not None:
            media_id = verification.acknowledgement_media_id
            ref = (await self._media.by_id({media_id})).get(media_id)
            if ref is not None:
                files = [
                    AcknowledgementFile(content_type=view.content_type, url=view.url)
                    for view in ref.renditions
                ]
        return OwnerPoliceVerification(
            booking=booking.code,
            status=status,
            details=self._details(verification),
            tenancy=tenancy_summary(await self._agreements.tenancy(booking)),
            details_submitted_at=None
            if verification is None
            else verification.details_submitted_at,
            submitted_to_police_at=None
            if verification is None
            else verification.submitted_to_police_at,
            police_reference=None if verification is None else verification.police_reference,
            acknowledgement=files,
            verified_at=None if verification is None else verification.verified_at,
            can_mark_submitted=allowed(
                status, VerificationEvent.SUBMIT_TO_POLICE, booking_ended=booking.ended
            ),
            can_mark_verified=allowed(
                status, VerificationEvent.MARK_VERIFIED, booking_ended=booking.ended
            ),
            erased=verification is not None and verification.erased_at is not None,
        )

    async def _record(
        self,
        actor: audit.Actor,
        verification: TenantVerification,
        booking: BookingRecord,
        action: str,
        details: dict[str, object] | None = None,
    ) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=actor,
            action=action,
            entity_type=ENTITY,
            entity_id=str(verification.public_id),
            details={"booking": booking.code, "status": verification.status} | (details or {}),
        )


def _status(verification: TenantVerification | None) -> PoliceVerificationStatus:
    return (
        PoliceVerificationStatus.NOT_STARTED
        if verification is None
        else PoliceVerificationStatus(verification.status)
    )


def _advance(
    status: PoliceVerificationStatus, event: VerificationEvent, *, booking: BookingRecord
) -> PoliceVerificationStatus:
    try:
        return advance(status, event, booking_ended=booking.ended)
    except VerificationRefusedError as refusal:
        raise InvalidTransitionError(refusal.reason) from refusal
