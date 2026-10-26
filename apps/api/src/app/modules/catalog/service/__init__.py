"""Use cases of the catalog module; each method is one transaction (ADR 0021, 0023, 0024)."""

from app.modules.catalog.service.inventory import CategoryChanges, CategoryDraft, InventoryService
from app.modules.catalog.service.listings import ListingService, PropertyChanges, PropertyDraft
from app.modules.catalog.service.owners import OwnerRecord, OwnerService
from app.modules.catalog.service.reads import (
    CatalogReader,
    CategoryView,
    ListingDetail,
    ListingSummary,
    RoomView,
)
from app.modules.catalog.service.verification import (
    Report,
    VerificationService,
    VisitReader,
    VisitView,
)

__all__ = [
    "CatalogReader",
    "CategoryChanges",
    "CategoryDraft",
    "CategoryView",
    "InventoryService",
    "ListingDetail",
    "ListingService",
    "ListingSummary",
    "OwnerRecord",
    "OwnerService",
    "PropertyChanges",
    "PropertyDraft",
    "Report",
    "RoomView",
    "VerificationService",
    "VisitReader",
    "VisitView",
]
