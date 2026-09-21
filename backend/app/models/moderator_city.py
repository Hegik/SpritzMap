from sqlalchemy import ForeignKey, Table, Column
from app.core.database import Base

# Zuordnung Moderator ↔ Stadt: Moderatoren dürfen nur in diesen Städten bearbeiten (lesen überall)
moderator_cities = Table(
    "moderator_cities",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("city_id", ForeignKey("cities.id", ondelete="CASCADE"), primary_key=True),
)
