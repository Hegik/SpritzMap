from sqlalchemy import String, Boolean, Enum as SAEnum, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
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
    hashed_password: Mapped[str] = mapped_column(String(255))
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
