from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from amora.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserStatus(StrEnum):
    ONBOARDING = "onboarding"
    PENDING = "pending"      # submitted, waiting for admin review
    ACTIVE = "active"        # approved, visible in browse
    REJECTED = "rejected"    # admin asked for changes
    PAUSED = "paused"        # hidden by the user
    BANNED = "banned"
    UNDERAGE = "underage"    # permanently blocked


class Role(StrEnum):
    USER = "user"
    MOD = "mod"
    ADMIN = "admin"
    OWNER = "owner"  # only ever granted via OWNER_* env vars, never stored


class Platform(StrEnum):
    TELEGRAM = "telegram"
    DISCORD = "discord"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"sqlite_autoincrement": True}  # never reuse IDs of deleted users (audit log integrity)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    status: Mapped[str] = mapped_column(String(16), default=UserStatus.ONBOARDING, index=True)
    role: Mapped[str] = mapped_column(String(16), default=Role.USER)
    rejection_reason: Mapped[str | None] = mapped_column(String(200))

    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    biometric_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dob: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(16))
    show_me: Mapped[list[str]] = mapped_column(JSON, default=list)
    looking_for: Mapped[str | None] = mapped_column(String(16))
    display_name: Mapped[str | None] = mapped_column(String(40))
    bio: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    lang: Mapped[str] = mapped_column(String(8), default="en")
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)

    is_verified: Mapped[bool] = mapped_column(default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Pointer to the JSON snapshot of this profile in the Telegram vault channel
    vault_snapshot_msg_id: Mapped[int | None] = mapped_column(BigInteger)

    accounts: Mapped[list["PlatformAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    photos: Mapped[list["Photo"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin", order_by="Photo.position"
    )

    def age(self, today: date | None = None) -> int | None:
        if self.dob is None:
            return None
        from amora.core.validation import age_on

        return age_on(self.dob, today or date.today())

    def account(self, platform: str) -> "PlatformAccount | None":
        return next((a for a in self.accounts if a.platform == platform), None)


class PlatformAccount(Base):
    __tablename__ = "platform_accounts"
    __table_args__ = (UniqueConstraint("platform", "platform_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    platform_user_id: Mapped[str] = mapped_column(String(32))
    username: Mapped[str | None] = mapped_column(String(64))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="accounts")


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)  # 0 = main photo

    tg_file_id: Mapped[str | None] = mapped_column(String(255))
    vault_msg_id: Mapped[int | None] = mapped_column(BigInteger)
    local_path: Mapped[str | None] = mapped_column(String(500))

    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    phash: Mapped[str] = mapped_column(String(16), index=True)
    face_score: Mapped[float] = mapped_column(Float)
    match_score: Mapped[float | None] = mapped_column(Float)  # similarity to main photo (extras only)
    face_embedding: Mapped[bytes] = mapped_column(LargeBinary)  # Fernet-encrypted float32[128]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="photos")


class AdminAction(Base):
    """Audit log: every admin/moderator action is recorded here."""

    __tablename__ = "admin_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    admin_platform: Mapped[str] = mapped_column(String(16))
    admin_platform_id: Mapped[str] = mapped_column(String(32))
    admin_name: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    target_user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
