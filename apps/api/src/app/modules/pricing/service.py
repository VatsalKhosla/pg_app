"""Pricing's use cases. For now the current policies, which the public pages explain (step 3.8);
quotes and the engine arrive in Phase 4."""

from dataclasses import dataclass

from app.modules.pricing.domain.policies import (
    DEFAULT_BOOKING_POLICY,
    DEFAULT_FEE_POLICY,
    BookingPolicy,
    FeePolicy,
)


@dataclass(frozen=True, slots=True)
class Policies:
    fee: FeePolicy
    booking: BookingPolicy


class PolicyService:
    async def current(self) -> Policies:
        """The policies in force. Step 4.1 reads them from the policy tables."""
        return Policies(fee=DEFAULT_FEE_POLICY, booking=DEFAULT_BOOKING_POLICY)
