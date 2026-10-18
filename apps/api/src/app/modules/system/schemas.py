from typing import Literal

from app.core.schemas import ApiModel
from app.modules.system.domain.readiness import CheckState


class Health(ApiModel):
    """Liveness: the process is up and serving requests."""

    status: Literal["ok"]


class Readiness(ApiModel):
    """Readiness: whether this instance can serve traffic, with the state of each dependency."""

    status: CheckState
    checks: dict[str, CheckState]
