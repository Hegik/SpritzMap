from sqlalchemy import String, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.core.database import Base


class ModerationLog(Base):
    __tablename__ = "moderation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    price_entry_id: Mapped[int] = mapped_column(ForeignKey("price_entries.id"), index=True)
    moderator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    action: Mapped[str] = mapped_column(String(50))  # created, updated, confirmed, flagged, deleted
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    price_entry: Mapped["PriceEntry"] = relationship(back_populates="moderation_logs")
    moderator: Mapped["User | None"] = relationship(back_populates="moderation_logs")
