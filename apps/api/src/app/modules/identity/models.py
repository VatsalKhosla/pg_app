"""Identity tables (ARCHITECTURE §6): users, their roles and their sessions."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.actor import Role
from app.core.db import Model
from app.core.ids import new_public_id
from app.modules.identity.domain.otp import OtpPurpose
from app.modules.identity.domain.sessions import EndReason, SessionKind


def _one_of(column: str, values: type[Role | SessionKind | EndReason | OtpPurpose]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


class User(Model):
    __tablename__ = "users"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    # E.164 (+919876543210): the account's login identity.
    phone_e164: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    # A suspended user can't sign in, and their sessions stop working.
    status: Mapped[str] = mapped_column(Text, server_default="active")

    __table_args__ = (
        CheckConstraint(r"phone_e164 ~ '^\+[1-9][0-9]{6,14}$'", name="phone_e164"),
        CheckConstraint("status IN ('active', 'suspended')", name="status"),
    )


class UserRole(Model):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("user_id", "role"),
        CheckConstraint(_one_of("role", Role), name="role"),
    )


class UserSession(Model):
    """A signed-in browser. Only the token's SHA-256 is stored: a leaked table holds no token."""

    __tablename__ = "sessions"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    kind: Mapped[str] = mapped_column(Text)
    # Times from the injectable clock, so tests can move them.
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(Text)
    # For the user's session list and for investigating abuse; deleted with the session.
    ip_address: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_one_of("kind", SessionKind), name="kind"),
        CheckConstraint(_one_of("end_reason", EndReason), name="end_reason"),
        CheckConstraint("(ended_at IS NULL) = (end_reason IS NULL)", name="ended"),
    )


class OtpChallenge(Model):
    """One sign-in code sent to a phone. The code is kept only as an HMAC under SECRET_KEY, bound to
    the challenge, so a leaked table reveals no code."""

    __tablename__ = "otp_challenges"

    # The browser's handle on the challenge; the code alone identifies nothing.
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    phone_e164: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    code_hash: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A newer code for the same phone replaced this one.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_one_of("purpose", OtpPurpose), name="purpose"),
        CheckConstraint("attempts >= 0", name="attempts"),
        Index("ix_otp_challenges_phone_e164_requested_at", "phone_e164", "requested_at"),
    )
