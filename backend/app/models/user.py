from sqlalchemy import String, Text, Boolean, Enum as SAEnum, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.core.database import Base


class UserRole(str, enum.Enum):
    user = "user"
    moderator = "moderator"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    # Nur noch für Legacy-Konten (Rollback-Fenster); Authentik-Konten haben kein lokales Passwort
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Authentik-User-UUID (OIDC `sub`, sub_mode=user_uuid) – einzige Verknüpfung, nie über die E-Mail
    authentik_sub: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    # Letztes ID-Token aus Authentik: nur als id_token_hint beim Abmelden (ohne Hint lehnt Authentik
    # post_logout_redirect_uri ab). Enthält nichts, was nicht ohnehin in dieser Zeile steht.
    oidc_id_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.user)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    verification_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reset_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reset_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )

    price_entries: Mapped[list["PriceEntry"]] = relationship(back_populates="user")
    # Städte, in denen ein Moderator bearbeiten darf (Admins: alle)
    moderated_cities: Mapped[list["City"]] = relationship(secondary="moderator_cities")
    moderation_logs: Mapped[list["ModerationLog"]] = relationship(back_populates="moderator")
