from pydantic import BaseModel
from app.models.location import LocationType


class LocationOut(BaseModel):
    id: int
    osm_id: int
    name: str
    location_type: LocationType
    latitude: float
    longitude: float
    address_street: str | None
    address_city: str | None
    address_postcode: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class LocationGeoJSON(BaseModel):
    """GeoJSON Feature for a location with aggregated price data."""
    type: str = "Feature"
    geometry: dict
    properties: dict
