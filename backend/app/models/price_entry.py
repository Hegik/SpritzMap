from sqlalchemy import Float, Integer, ForeignKey, DateTime, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.core.database import Base


class PriceEntry(Base):
    __tablename__ = "price_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    drink_id: Mapped[int] = mapped_column(ForeignKey("drinks.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    price: Mapped[float] = mapped_column(Float)
    # 0–255 color intensity slider
    color_value: Mapped[int] = mapped_column(Integer, default=128)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Nutzer können bestätigen, dass der Preis noch aktuell ist
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String(500))

    location: Mapped["Location"] = relationship(back_populates="price_entries")
    drink: Mapped["Drink"] = relationship(back_populates="price_entries")
    user: Mapped["User"] = relationship(back_populates="price_entries")
    moderation_logs: Mapped[list["ModerationLog"]] = relationship(back_populates="price_entry")
