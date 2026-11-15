"""A booking's rent agreement (ADR 0070): made once the owner confirms the booking, from the
booking's own facts, and read by the student, the owner and ops.

- **Made from the booking.** The parties, the PG and its exact address (a confirmed booking may see
  it, rule 11), the bed, the stay and every amount come from the booking, catalog, identity and
  pricing modules' services, written into the template in force. Money is copied as the booking
  has it, never worked out again.
- **Kept current until somebody signs.** Until the first signature, the text follows the facts (a
  student who adds their name, ops correcting an address) and the template in force. From the
  first signature it is fixed, so both sides sign the same words; the database enforces that too.
- **Following the booking.** The booking module announces a confirmation and an end through the
  outbox; ``sync`` makes the agreement, or voids one not yet signed by both when the booking ends
  early. Every request does the same first, so nothing depends on when the job runs.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from sqlalchemy.dialects.postgresql import insert

from app.config import BRAND_NAME
from app.core import audit
from app.core.errors import NotFoundError
from app.modules.agreements.domain.agreements import (
    AgreementEvent,
    AgreementStatus,
    Signer,
    awaits,
    text_settled,
    transition,
)
from app.modules.agreements.domain.terms import (
    ChargeCadence,
    ChargeTerm,
    Tenancy,
    missing,
    render,
    text_sha256,
)
from app.modules.agreements.models import RentalAgreement
from app.modules.agreements.repository import AgreementRepository
from app.modules.agreements.schemas import (
    AgreementSignatureView,
    OpsRentAgreement,
    RentAgreement,
    SignatureEvidence,
)
from app.modules.agreements.templates import is_draft
from app.modules.booking.service import BookingLookup
from app.modules.catalog.service import CatalogLookup
from app.modules.identity.service import Accounts
from app.modules.pricing.service import QuoteLookup

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.modules.agreements.models import AgreementSignature
    from app.modules.agreements.templates import Templates
    from app.modules.booking.service import BookingRecord

# What the audit log calls an agreement.
ENTITY: Final = "rental_agreement"
_VOIDABLE: Final = frozenset(
    {
        AgreementStatus.AWAITING_SIGNATURES,
        AgreementStatus.SIGNED_BY_STUDENT,
        AgreementStatus.SIGNED_BY_OWNER,
    }
)


@dataclass(frozen=True, slots=True)
class Current:
    """An agreement as it stands now: its row, its text, and what the text still lacks."""

    row: RentalAgreement
    tenancy: Tenancy
    missing: list[str]


@dataclass(frozen=True, slots=True)
class Reading:
    """What a reader is shown: the saved agreement, or the one a confirmed booking has before
    anyone has acted on it (``row`` None)."""

    row: RentalAgreement | None
    status: AgreementStatus
    template_version: str
    text: str
    text_sha256: str
    missing: list[str]
    tenancy: Tenancy
    signatures: list[AgreementSignature]


class RentAgreements:
    def __init__(self, db: AsyncSession, clock: Clock, *, templates: Templates) -> None:
        self._db = db
        self._clock = clock
        self._templates = templates
        self._agreements = AgreementRepository(db)
        self._bookings = BookingLookup(db)
        self._catalog = CatalogLookup(db)
        self._accounts = Accounts(db)
        self._quotes = QuoteLookup(db, clock)

    # Whose booking it is.

    async def booking_of(self, actor: Actor, code: str, *, side: Signer | None) -> BookingRecord:
        """The booking ``code`` names, if ``actor`` is the side ``side`` names on it (the student
        who booked, or its PG's owner). Anything else is a 404, as if it didn't exist."""
        booking = await self._bookings.by_code(code)
        if booking is None:
            raise NotFoundError
        if side is Signer.STUDENT and booking.student_id != actor.user_id:
            raise NotFoundError
        if side is Signer.OWNER and (
            await self._catalog.owner_id_of_user(actor.user_id) != booking.owner_id
        ):
            raise NotFoundError
        return booking

    # The text.

    async def tenancy(self, booking: BookingRecord) -> Tenancy:
        """What the booking's agreement states, from the modules that know each fact."""
        party = await self._catalog.invoice_party(booking.owner_id, booking.property_id)
        bed = await self._catalog.bed_ref(booking.bed_id)
        student = (await self._accounts.many([booking.student_id])).get(booking.student_id)
        charges = await self._quotes.charges(booking.quote_id)
        return Tenancy(
            booking_code=booking.code,
            licensor=party.legal_name,
            licensor_business=party.business_name,
            licensee=None if student is None else student.name,
            pg_name=party.pg_name,
            pg_address=party.pg_address,
            room_type=bed.category_label,
            room=bed.room_label,
            bed=bed.label,
            move_in=booking.move_in,
            stay_months=booking.stay_months,
            planned_move_out=booking.planned_move_out,
            monthly_rent_paise=booking.monthly_rent_paise,
            deposit_paise=booking.deposit_paise,
            token_paise=booking.token_paise,
            due_at_move_in_paise=booking.due_at_move_in_paise,
            monthly_charges_paise=booking.monthly_charges_paise,
            one_time_charges_paise=booking.one_time_charges_paise,
            charges=tuple(
                ChargeTerm(
                    label=charge.label,
                    cadence=ChargeCadence(charge.cadence),
                    amount_paise=charge.amount_paise,
                    rate_paise=charge.rate_paise,
                    unit=charge.unit,
                )
                for charge in charges
            ),
        )

    def text_of(self, tenancy: Tenancy) -> str:
        return render(self._templates.current, tenancy, brand=BRAND_NAME)

    # Keeping the agreement in step with its booking.

    async def ensure(self, booking: BookingRecord) -> Current | None:
        """The booking's agreement, locked until the transaction ends: made once the booking has
        been confirmed, voided if the booking ended early before both sides signed, and with its
        text brought up to date while nobody has signed. None for a booking never confirmed. Runs
        inside the caller's transaction, and comes to the same whenever it runs."""
        row = await self._agreements.of_booking(booking.id, lock=True)
        if row is None and not booking.was_confirmed:
            return None
        tenancy = await self.tenancy(booking)
        if row is None:
            row = await self._create(booking, tenancy)
        now = self._clock.now()
        if booking.ended and row.booking_ended_at is None:
            row.booking_ended_at = booking.ended_at or now
        status = AgreementStatus(row.status)
        if booking.ended_early and status in _VOIDABLE:
            row.status = transition(status, AgreementEvent.BOOKING_ENDED_EARLY)
            row.voided_at = booking.ended_at or now
            await self._record(row, booking, "agreement.void", {"booking_status": booking.status})
        elif not text_settled(status):
            text = self.text_of(tenancy)
            if text != row.text:
                row.text = text
                row.text_sha256 = text_sha256(text)
                row.template_version = self._templates.version
        await self._db.flush()
        settled = text_settled(AgreementStatus(row.status))
        return Current(row=row, tenancy=tenancy, missing=[] if settled else missing(tenancy))

    async def sync(self, booking_id: uuid.UUID) -> None:
        """A booking was confirmed or ended (its outbox event): its agreement follows. Changes
        nothing when run again. Runs inside the job's transaction."""
        booking = await self._bookings.by_public_id(booking_id)
        if booking is not None:
            await self.ensure(booking)

    async def _create(self, booking: BookingRecord, tenancy: Tenancy) -> RentalAgreement:
        text = self.text_of(tenancy)
        made = await self._db.scalar(
            insert(RentalAgreement)
            .values(
                booking_id=booking.id,
                student_id=booking.student_id,
                owner_id=booking.owner_id,
                status=AgreementStatus.AWAITING_SIGNATURES,
                template_version=self._templates.version,
                text=text,
                text_sha256=text_sha256(text),
            )
            .on_conflict_do_nothing(index_elements=[RentalAgreement.booking_id])
            .returning(RentalAgreement.id)
        )
        # Made now, or a moment ago by a request racing this one: either way, the one there is.
        row = await self._agreements.of_booking(booking.id, lock=True)
        if row is None:  # pragma: no cover - inserted or found just above
            raise NotFoundError
        if made is not None:
            await self._record(
                row,
                booking,
                "agreement.created",
                {"template_version": row.template_version, "text_sha256": row.text_sha256},
            )
        return row

    async def _record(
        self,
        row: RentalAgreement,
        booking: BookingRecord,
        action: str,
        details: dict[str, object],
    ) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.SYSTEM,
            action=action,
            entity_type=ENTITY,
            entity_id=str(row.public_id),
            details={"booking": booking.code} | details,
        )

    # Reading.

    async def reading(self, booking: BookingRecord) -> Reading:
        """What the agreement says now, without changing anything: the saved text once somebody
        has signed, otherwise the text the facts make now. 404 when the booking has none."""
        row = await self._agreements.of_booking(booking.id)
        if row is None and not booking.was_confirmed:
            raise NotFoundError
        tenancy = await self.tenancy(booking)
        status = AgreementStatus.AWAITING_SIGNATURES if row is None else AgreementStatus(row.status)
        if booking.ended_early and status in _VOIDABLE:
            # The booking's end is on its way through the outbox; it is void already.
            status = AgreementStatus.VOID
        if row is not None and text_settled(status):
            text, version, lacking = row.text, row.template_version, []
        else:
            text, version, lacking = (
                self.text_of(tenancy),
                self._templates.version,
                missing(tenancy),
            )
        return Reading(
            row=row,
            status=status,
            template_version=version,
            text=text,
            text_sha256=text_sha256(text),
            missing=lacking,
            tenancy=tenancy,
            signatures=[] if row is None else await self._agreements.signatures_of(row.id),
        )

    async def for_party(self, actor: Actor, code: str, *, side: Signer) -> RentAgreement:
        """The student's or the owner's view of their own booking's agreement."""
        async with self._db.begin():
            booking = await self.booking_of(actor, code, side=side)
            return party_view(booking, await self.reading(booking), side=side)

    async def for_ops(self, code: str) -> OpsRentAgreement:
        async with self._db.begin():
            booking = await self.booking_of_anyone(code)
            reading = await self.reading(booking)
            signers = await self._accounts.many({row.user_id for row in reading.signatures})
            return OpsRentAgreement(
                booking=booking.code,
                status=reading.status,
                template_version=reading.template_version,
                draft=is_draft(reading.template_version),
                text=reading.text,
                text_sha256=reading.text_sha256,
                ready=not reading.missing,
                missing=reading.missing,
                signatures=[
                    SignatureEvidence(
                        signer=Signer(row.signer),
                        user=signers[row.user_id].public_id,
                        name=row.typed_name,
                        signed_at=row.signed_at,
                        ip_address=row.ip_address,
                        user_agent=row.user_agent,
                        text_sha256=row.text_sha256,
                        template_version=row.template_version,
                    )
                    for row in reading.signatures
                ],
                created_at=None if reading.row is None else reading.row.created_at,
                signed_at=None if reading.row is None else reading.row.signed_at,
                voided_at=None if reading.row is None else reading.row.voided_at,
                booking_ended_at=None if reading.row is None else reading.row.booking_ended_at,
            )

    async def booking_of_anyone(self, code: str) -> BookingRecord:
        booking = await self._bookings.by_code(code)
        if booking is None:
            raise NotFoundError
        return booking


def party_view(booking: BookingRecord, reading: Reading, *, side: Signer) -> RentAgreement:
    signed = {Signer(row.signer) for row in reading.signatures}
    row = reading.row
    return RentAgreement(
        booking=booking.code,
        status=reading.status,
        you=side,
        template_version=reading.template_version,
        draft=is_draft(reading.template_version),
        text=reading.text,
        text_sha256=reading.text_sha256,
        ready=not reading.missing,
        missing=reading.missing,
        can_sign=awaits(reading.status, side) and side not in signed and not reading.missing,
        signatures=[
            AgreementSignatureView(
                signer=Signer(signature.signer),
                name=signature.typed_name,
                signed_at=signature.signed_at,
            )
            for signature in reading.signatures
        ],
        signed_at=None if row is None else row.signed_at,
        voided_at=None if row is None else row.voided_at,
    )
