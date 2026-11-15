"""The agreements module's personal data over time (DPDP; ADRs 0018 and 0070): its part of a
person's data export, and its rules in the retention schedule.

- **Export:** the agreements a person is the student on, the signatures they made on either side,
  and the police-verification details they gave, opened for them.
- **Retention:** signing codes (with the IP address and user agent that asked) go after 7 days,
  as sign-in codes do. The police-verification details are erased 30 days after the police
  verified the tenant or the booking ended, whichever comes first; the record that it happened,
  the acknowledgement and the dates stay. [The founders confirm the 30 days.] Signatures are
  evidence of the agreement and stay with it; the table refuses deletes.
"""

import json
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from app.core.sealing import SealError
from app.modules.agreements.domain import verification as police
from app.modules.agreements.repository import AgreementRepository
from app.modules.agreements.service.signing import SIGNING_CODE_RETENTION
from app.modules.agreements.service.verification import sealing_context
from app.modules.booking.service import BookingLookup

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.core.sealing import FieldCipher
    from app.modules.agreements.models import TenantVerification

# Police-verification details are erased this long after the police verified the tenant, or the
# booking ended.
POLICE_DETAILS_RETENTION: Final = timedelta(days=30)


def _moment(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def agreements_part(
    cipher: FieldCipher,
) -> Callable[[AsyncSession, int], Awaitable[dict[str, object]]]:
    """The export part, with the cipher that opens the person's own police-verification
    details."""

    async def part(db: AsyncSession, user_id: int) -> dict[str, object]:
        rows = AgreementRepository(db)
        mine = await rows.of_student(user_id)
        signed = await rows.signatures_by(user_id)
        if not mine and not signed:
            return {}
        agreements = await rows.by_ids({signature.agreement_id for signature in signed})
        agreements |= {agreement.id: agreement for agreement in mine}
        bookings = await BookingLookup(db).by_ids(
            {agreement.booking_id for agreement in agreements.values()}
        )
        verifications = await rows.verifications_of({agreement.id for agreement in mine})
        return {
            "rentAgreements": [
                {
                    "booking": bookings[agreement.booking_id].code,
                    "status": agreement.status,
                    "templateVersion": agreement.template_version,
                    "textSha256": agreement.text_sha256,
                    "text": agreement.text,
                    "signedAt": _moment(agreement.signed_at),
                    "voidedAt": _moment(agreement.voided_at),
                    "policeVerification": _verification(cipher, verifications.get(agreement.id)),
                }
                for agreement in mine
            ],
            "agreementSignatures": [
                {
                    "booking": bookings[agreements[signature.agreement_id].booking_id].code,
                    "side": signature.signer,
                    "typedName": signature.typed_name,
                    "signedAt": signature.signed_at.isoformat(),
                    "ipAddress": signature.ip_address,
                    "userAgent": signature.user_agent,
                    "textSha256": signature.text_sha256,
                }
                for signature in signed
            ],
        }

    return part


def _verification(
    cipher: FieldCipher, verification: TenantVerification | None
) -> dict[str, object] | None:
    if verification is None:
        return None
    details: dict[str, object] | None = None
    if verification.details_sealed is not None:
        try:
            plain = cipher.open(verification.details_sealed, context=sealing_context(verification))
        except SealError:
            # A key no longer listed: say so rather than fail the whole export.
            details = {"unreadable": True}
        else:
            details = police.to_json(police.from_json(json.loads(plain)))
    return {
        "status": verification.status,
        "details": details,
        "detailsSubmittedAt": _moment(verification.details_submitted_at),
        "submittedToPoliceAt": _moment(verification.submitted_to_police_at),
        "policeReference": verification.police_reference,
        "verifiedAt": _moment(verification.verified_at),
        "erasedAt": _moment(verification.erased_at),
    }


async def delete_old_signing_codes(db: AsyncSession, clock: Clock) -> int:
    """Retention: signing codes older than SIGNING_CODE_RETENTION."""
    return await AgreementRepository(db).delete_codes_requested_before(
        clock.now() - SIGNING_CODE_RETENTION
    )


async def erase_police_details(db: AsyncSession, clock: Clock) -> int:
    """Retention: police-verification details POLICE_DETAILS_RETENTION after the police verified
    the tenant or the booking ended."""
    now = clock.now()
    cutoff = now - POLICE_DETAILS_RETENTION
    return await AgreementRepository(db).erase_details(
        verified_before=cutoff, ended_before=cutoff, now=now
    )
