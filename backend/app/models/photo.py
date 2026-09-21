from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.core.database import Base


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    price_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("price_entries.id", ondelete="SET NULL"), index=True, nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # Dateinamen relativ zu MEDIA_ROOT, z. B. "123/<uuid>.webp"
    filename: Mapped[str] = mapped_column(String(255))
    thumb_filename: Mapped[str] = mapped_column(String(255))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    location: Mapped["Location"] = relationship()
    price_entry: Mapped["PriceEntry | None"] = relationship()
    user: Mapped["User | None"] = relationship()
