"""Rent agreement and police verification routes (ADR 0070).

- The student who booked reads the agreement, asks for a signing code and signs; and gives the
  details for their police verification.
- The PG's owner reads and signs the same agreement, prints the police-verification details,
  submits them on the Delhi Police portal, uploads the acknowledgement and marks it verified.
- Ops read all of it, and change none of it.

Another student's or owner's booking, like one that doesn't exist, is a 404. A booking that was
never confirmed has no agreement: 404 too.
"""

from datetime import timedelta
from typing import Final

from fastapi import APIRouter, Request, status

from app.core.actor import Actor
from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.ratelimit import RateLimit, client_ip, enforce
from app.modules.agreements.domain.agreements import Signer
from app.modules.agreements.policies import (
    can_read_everything,
    can_sign_as_owner,
    can_sign_as_student,
)
from app.modules.agreements.schemas import (
    OpsPoliceVerification,
    OpsRentAgreement,
    OwnerPoliceVerification,
    PoliceSubmission,
    RentAgreement,
    SignatureRequest,
    SigningCodeSent,
    StudentPoliceVerification,
    TenantDetailsInput,
)
from app.modules.agreements.service import (
    AgreementSigning,
    PoliceVerifications,
    RentAgreements,
    Signing,
)

router = APIRouter(prefix="/v1", tags=["agreements"])

# Signing is a few tries at most; this leaves room for typos without leaving room for guessing.
SIGNING_ATTEMPTS_PER_USER: Final = RateLimit(
    "signing-attempts-per-user", limit=20, window=timedelta(minutes=15)
)
# The police form is filled in once and corrected now and then.
POLICE_DETAILS_PER_USER: Final = RateLimit(
    "police-details-per-user", limit=20, window=timedelta(hours=1)
)


def _agreements(request: Request, db: DbSession, clock: ClockDep) -> RentAgreements:
    return RentAgreements(db, clock, templates=request.app.state.rent_templates)


def _signing(request: Request, db: DbSession, clock: ClockDep) -> AgreementSigning:
    state = request.app.state
    return AgreementSigning(
        db,
        clock,
        templates=state.rent_templates,
        secret=state.secret_key,
        sender=state.signing_code_sender,
        limiter=state.rate_limiter,
        shows_code=state.signing_codes_shown,
    )


def _verifications(request: Request, db: DbSession, clock: ClockDep) -> PoliceVerifications:
    state = request.app.state
    return PoliceVerifications(
        db,
        clock,
        templates=state.rent_templates,
        cipher=state.field_cipher,
        buckets=state.media_buckets,
        storage=state.storage,
    )


def _as(actor: Actor, side: Signer) -> Signer:
    allowed = can_sign_as_student(actor) if side is Signer.STUDENT else can_sign_as_owner(actor)
    if not allowed:
        raise ForbiddenError
    return side


async def _code(
    signing: AgreementSigning, request: Request, actor: Actor, *, code: str, side: Signer
) -> SigningCodeSent:
    issued = await signing.request_code(
        actor,
        code,
        side=_as(actor, side),
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return SigningCodeSent(
        expires_at=issued.expires_at,
        resend_after=issued.resend_after,
        development_code=issued.development_code,
    )


async def _sign(
    signing: AgreementSigning,
    request: Request,
    actor: Actor,
    *,
    code: str,
    body: SignatureRequest,
    side: Signer,
) -> RentAgreement:
    _as(actor, side)
    await enforce(
        request.app.state.rate_limiter, SIGNING_ATTEMPTS_PER_USER, f"user:{actor.user_id}"
    )
    return await signing.sign(
        actor,
        code,
        Signing(
            side=side,
            typed_name=body.full_name,
            text_sha256=body.text_sha256,
            code=body.code,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        ),
    )


# The student.


@router.get("/bookings/{code}/agreement", summary="Your rent agreement")
async def my_agreement(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RentAgreement:
    """Once the owner has confirmed your booking: the full text (Markdown, marked DRAFT until a
    lawyer has reviewed it), who has signed and when, and whether you may sign now."""
    return await _agreements(request, db, clock).for_party(
        actor, code, side=_as(actor, Signer.STUDENT)
    )


@router.post(
    "/bookings/{code}/agreement/signing-codes",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask for a code to sign your rent agreement",
)
async def ask_for_signing_code(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> SigningCodeSent:
    """A six-digit code, sent to you, for ten minutes. A new one replaces the last, every 30
    seconds at most (429 SIGNING_CODE_TOO_SOON); five an hour. 409 INVALID_TRANSITION once you've
    signed or the agreement is void; 409 AGREEMENT_NOT_READY while it lacks your name."""
    return await _code(_signing(request, db, clock), request, actor, code=code, side=Signer.STUDENT)


@router.post(
    "/bookings/{code}/agreement/signatures",
    status_code=status.HTTP_201_CREATED,
    summary="Sign your rent agreement",
)
async def sign_my_agreement(
    code: str,
    body: SignatureRequest,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> RentAgreement:
    """With the code sent to you, your full name, and the ``textSha256`` of the text you read:
    409 AGREEMENT_TEXT_CHANGED if the text has changed since (read it again). 400
    SIGNING_CODE_INVALID, SIGNING_CODE_EXPIRED or SIGNING_CODE_LOCKED for the code."""
    return await _sign(
        _signing(request, db, clock), request, actor, code=code, body=body, side=Signer.STUDENT
    )


@router.get("/bookings/{code}/police-verification", summary="Your police verification")
async def my_police_verification(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StudentPoliceVerification:
    """Where the police verification of your stay is, with the details you gave."""
    _as(actor, Signer.STUDENT)
    return await _verifications(request, db, clock).for_student(actor, code)


@router.put("/bookings/{code}/police-verification", summary="Give your police-verification details")
async def give_police_details(
    code: str,
    body: TenantDetailsInput,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> StudentPoliceVerification:
    """What the Delhi Police tenant form asks, for your PG's owner to submit; correct it until
    they have. An identity document is its type and last four characters only: never type a full
    Aadhaar number anywhere (422). 422 POLICE_DETAILS_INVALID for an impossible date of birth;
    409 INVALID_TRANSITION once submitted or after the booking ended."""
    _as(actor, Signer.STUDENT)
    await enforce(request.app.state.rate_limiter, POLICE_DETAILS_PER_USER, f"user:{actor.user_id}")
    return await _verifications(request, db, clock).give_details(actor, code, body)


# The owner.


@router.get("/owner/bookings/{code}/agreement", summary="A booking's rent agreement")
async def owner_rent_agreement(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RentAgreement:
    """The agreement for a booking at one of your PGs, once you've confirmed it."""
    return await _agreements(request, db, clock).for_party(
        actor, code, side=_as(actor, Signer.OWNER)
    )


@router.post(
    "/owner/bookings/{code}/agreement/signing-codes",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask for a code to sign a booking's rent agreement",
)
async def owner_signing_code(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> SigningCodeSent:
    """As for students: a six-digit code, sent to you, for ten minutes."""
    return await _code(_signing(request, db, clock), request, actor, code=code, side=Signer.OWNER)


@router.post(
    "/owner/bookings/{code}/agreement/signatures",
    status_code=status.HTTP_201_CREATED,
    summary="Sign a booking's rent agreement",
)
async def owner_sign_agreement(
    code: str,
    body: SignatureRequest,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> RentAgreement:
    """As for students: the code, your full name, and the hash of the text you read."""
    return await _sign(
        _signing(request, db, clock), request, actor, code=code, body=body, side=Signer.OWNER
    )


@router.get(
    "/owner/bookings/{code}/police-verification",
    summary="A tenant's police verification, to submit",
)
async def owner_police_verification(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> OwnerPoliceVerification:
    """The tenant's details and the tenancy, to copy onto the Delhi Police portal, with the
    acknowledgement once uploaded (links signed for five minutes). Every look is audited."""
    _as(actor, Signer.OWNER)
    return await _verifications(request, db, clock).for_owner(actor, code)


@router.post(
    "/owner/bookings/{code}/police-verification/mark-submitted",
    summary="Say you've submitted the tenant's police verification",
)
async def owner_mark_submitted(
    code: str,
    body: PoliceSubmission,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> OwnerPoliceVerification:
    """With the portal's acknowledgement, uploaded as your own document, and its number if it
    gave one. 422 ACKNOWLEDGEMENT_INVALID for a file that isn't yours or isn't a document; 409
    INVALID_TRANSITION before the tenant has given their details, or after."""
    _as(actor, Signer.OWNER)
    return await _verifications(request, db, clock).mark_submitted(
        actor, code, acknowledgement=body.acknowledgement, reference=body.reference
    )


@router.post(
    "/owner/bookings/{code}/police-verification/mark-verified",
    summary="Say the police have verified the tenant",
)
async def owner_mark_verified(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> OwnerPoliceVerification:
    """Once submitted: 409 INVALID_TRANSITION before."""
    _as(actor, Signer.OWNER)
    return await _verifications(request, db, clock).mark_verified(actor, code)


# Ops: read-only.


@router.get("/ops/bookings/{code}/agreement", summary="A booking's rent agreement, with evidence")
async def ops_rent_agreement(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> OpsRentAgreement:
    """The text and every signature with its evidence: the account, the name typed, the time,
    the IP address and browser, and the hash of the text signed."""
    if not can_read_everything(actor):
        raise ForbiddenError
    return await _agreements(request, db, clock).for_ops(code)


@router.get(
    "/ops/bookings/{code}/police-verification",
    summary="A tenant's police verification, read-only",
)
async def ops_police_verification(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> OpsPoliceVerification:
    """Everything the owner sees; every look at the details is audited."""
    if not can_read_everything(actor):
        raise ForbiddenError
    return await _verifications(request, db, clock).for_ops(actor, code)
