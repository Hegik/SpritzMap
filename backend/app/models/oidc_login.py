from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class OidcLogin(Base):
    """Laufender OIDC-Login: state/PKCE/nonce bis zum Callback, danach ein einmaliger Code für das Frontend."""

    __tablename__ = "oidc_logins"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    code_verifier: Mapped[str] = mapped_column(String(128))
    nonce: Mapped[str] = mapped_column(String(64))
    next_path: Mapped[str] = mapped_column(String(500), default="/")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # nach erfolgreichem Callback gesetzt
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    login_code: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    login_code_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exchanged: Mapped[bool] = mapped_column(default=False, server_default="false")
