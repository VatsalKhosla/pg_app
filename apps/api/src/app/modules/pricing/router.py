"""Pricing routes (ARCHITECTURE §15): the policies in force, for anyone."""

from typing import Final

from fastapi import APIRouter, Response

from app.modules.pricing.schemas import BookingTerms, PlacementFeeTerms, PublicPolicies
from app.modules.pricing.service import PolicyService

router = APIRouter(prefix="/v1", tags=["pricing"])

# They change rarely, and the web app's pages for them are revalidated when they do.
CACHE_CONTROL: Final = "public, max-age=300"


@router.get("/policies", summary="The fee and booking terms in force")
async def policies(response: Response) -> PublicPolicies:
    """What owners pay and what students can rely on: the placement fee, the token, holds,
    cancellation and the check window. Public."""
    response.headers["Cache-Control"] = CACHE_CONTROL
    current = await PolicyService().current()
    fee, booking = current.fee, current.booking
    return PublicPolicies(
        placement_fee=PlacementFeeTerms(
            rate_bps=fee.rate_bps,
            basis=fee.basis,
            gst_rate_bps=fee.gst_rate_bps,
            gst_mode=fee.gst_mode,
        ),
        booking=BookingTerms(
            token_paise=booking.token_paise,
            hold_minutes=booking.hold_minutes,
            free_cancel_days=booking.free_cancel_days,
            check_window_hours=booking.check_window_hours,
            confirm_deadline_hours=booking.confirm_deadline_hours,
            late_cancel_policy=booking.late_cancel_policy,
        ),
    )
