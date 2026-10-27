"""Every SQLAlchemy model, imported in one place so Alembic sees the whole schema (a composition
root, read by migrations/env.py). Add each module's models here as the module arrives."""

from app.core.audit import AuditLog
from app.core.db import Base
from app.core.flags import FeatureFlag
from app.core.idempotency import IdempotencyRecord
from app.core.outbox import OutboxJob
from app.modules.catalog.models import (
    Amenity,
    Bed,
    Owner,
    OwnerAgreement,
    Property,
    PropertyAmenity,
    PropertyMedia,
    Room,
    RoomCategory,
    VerificationPhoto,
    VerificationVisit,
)
from app.modules.compliance.models import DataExport, DataRequest
from app.modules.geo.models import (
    Campus,
    City,
    Locality,
    MetroLine,
    MetroStation,
    MetroStationLine,
)
from app.modules.identity.models import (
    Consent,
    OtpChallenge,
    TotpCredential,
    User,
    UserIdentity,
    UserRole,
    UserSession,
)
from app.modules.media.models import MediaAsset
from app.modules.search.models import PropertyPriceSummary

__all__ = [
    "Amenity",
    "AuditLog",
    "Base",
    "Bed",
    "Campus",
    "City",
    "Consent",
    "DataExport",
    "DataRequest",
    "FeatureFlag",
    "IdempotencyRecord",
    "Locality",
    "MediaAsset",
    "MetroLine",
    "MetroStation",
    "MetroStationLine",
    "OtpChallenge",
    "OutboxJob",
    "Owner",
    "OwnerAgreement",
    "Property",
    "PropertyAmenity",
    "PropertyMedia",
    "PropertyPriceSummary",
    "Room",
    "RoomCategory",
    "TotpCredential",
    "User",
    "UserIdentity",
    "UserRole",
    "UserSession",
    "VerificationPhoto",
    "VerificationVisit",
]
