from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Drink(Base):
    __tablename__ = "drinks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    # CSS hex color for map marker (e.g. "#FF6B35" for Aperol)
    color_hex: Mapped[str] = mapped_column(String(7))
    is_active: Mapped[bool] = mapped_column(default=True)

    price_entries: Mapped[list["PriceEntry"]] = relationship(back_populates="drink")
