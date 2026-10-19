"""Every SQLAlchemy model, imported in one place so Alembic sees the whole schema (a composition
root, read by migrations/env.py). Add each module's models here as the module arrives."""

from app.core.audit import AuditLog
from app.core.db import Base
from app.core.flags import FeatureFlag
from app.core.idempotency import IdempotencyRecord
from app.core.outbox import OutboxJob
from app.modules.compliance.models import DataExport, DataRequest
from app.modules.identity.models import (
    Consent,
    OtpChallenge,
    TotpCredential,
    User,
    UserIdentity,
    UserRole,
    UserSession,
)

__all__ = [
    "AuditLog",
    "Base",
    "Consent",
    "DataExport",
    "DataRequest",
    "FeatureFlag",
    "IdempotencyRecord",
    "OtpChallenge",
    "OutboxJob",
    "TotpCredential",
    "User",
    "UserIdentity",
    "UserRole",
    "UserSession",
]
