from pydantic import BaseModel, Field
from datetime import datetime


class PriceEntryCreate(BaseModel):
    location_id: int
    drink_id: int
    price: float = Field(gt=0, le=50)
    color_value: int = Field(ge=0, le=255, default=128)
    note: str | None = Field(None, max_length=500)


class PriceEntryUpdate(BaseModel):
    price: float = Field(gt=0, le=50)
    color_value: int = Field(ge=0, le=255)
    note: str | None = Field(None, max_length=500)


class PriceEntryOut(BaseModel):
    id: int
    location_id: int
    drink_id: int
    user_id: int
    price: float
    price_tier: str  # €, €€, €€€
    color_value: int
    reported_at: datetime
    last_confirmed_at: datetime
    is_current: bool
    note: str | None

    model_config = {"from_attributes": True}


class LocationPriceSummary(BaseModel):
    """Aggregated price data for a location, per drink."""
    location_id: int
    drink_id: int
    drink_name: str
    drink_color_hex: str
    latest_price: float
    price_tier: str
    avg_color_value: float  # average of last 50 entries
    entry_count: int
    last_updated: datetime
