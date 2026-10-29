"""The pricing module's errors (ARCHITECTURE §15)."""

from typing import TYPE_CHECKING

from app.core.errors import AppError

if TYPE_CHECKING:
    from collections.abc import Sequence


class PolicyInvalidError(AppError):
    """A policy version the founders' rules don't allow: the detail names every problem."""

    status = 422
    code = "POLICY_INVALID"
    title = "That policy doesn't work"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


class PricingConfigError(AppError):
    """No policy is in force, which the seeded defaults rule out: ops must look, and nothing is
    priced meanwhile."""

    status = 503
    code = "PRICING_CONFIG_ERROR"
    title = "Pricing isn't set up"


class RuleSetInvalidError(AppError):
    """A rule, or a set, that can't go into force: the detail names every problem."""

    status = 422
    code = "RULE_SET_INVALID"
    title = "Those pricing rules don't work"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


class QuoteInvalidError(AppError):
    """A move-in or stay that can't be quoted: the detail names every problem."""

    status = 422
    code = "QUOTE_INVALID"
    title = "That can't be quoted"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


class QuoteExpiredError(AppError):
    """A quote past its 30 minutes: what it says may no longer hold, so a new one is needed."""

    status = 409
    code = "QUOTE_EXPIRED"
    title = "That quote has expired"
