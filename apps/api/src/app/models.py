"""Every SQLAlchemy model, imported in one place so Alembic sees the whole schema (a composition
root, read by migrations/env.py). Add each module's models here as the module arrives."""

from app.core.audit import AuditLog
from app.core.db import Base
from app.core.flags import FeatureFlag
from app.core.idempotency import IdempotencyRecord
from app.core.outbox import OutboxJob
from app.modules.identity.models import OtpChallenge, User, UserRole, UserSession

__all__ = [
    "AuditLog",
    "Base",
    "FeatureFlag",
    "IdempotencyRecord",
    "OtpChallenge",
    "OutboxJob",
    "User",
    "UserRole",
    "UserSession",
]
