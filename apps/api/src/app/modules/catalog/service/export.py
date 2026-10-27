"""What the catalog holds about a person, for their data export (the DPDP Act's right of access):
an owner's business record and every acceptance of the owner agreement, with the IP address and
user agent it was made from (ADR 0025). Runs inside the export job's transaction (app/jobs.py)."""

from typing import TYPE_CHECKING

from app.modules.catalog.repository import CatalogRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def owner_data(db: AsyncSession, user_id: int) -> dict[str, object]:
    catalog = CatalogRepository(db)
    owner = await catalog.owner_of_user(user_id)
    if owner is None:
        return {}
    return {
        "owner": {
            "id": str(owner.public_id),
            "legalName": owner.legal_name,
            "businessName": owner.business_name,
            "gstin": owner.gstin,
            "kycStatus": owner.kyc_status,
            "status": owner.status,
            "agreementVersion": owner.agreement_version,
            "agreementAcceptances": [
                {
                    "version": acceptance.version,
                    "documentSha256": acceptance.document_sha256,
                    "acceptedAt": acceptance.accepted_at.isoformat(),
                    "ipAddress": acceptance.accepted_ip,
                    "userAgent": acceptance.accepted_user_agent,
                }
                for acceptance in await catalog.acceptances(owner.id)
            ],
        }
    }
