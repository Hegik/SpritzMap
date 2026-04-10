from pydantic import BaseModel


class DrinkOut(BaseModel):
    id: int
    name: str
    color_hex: str
    is_active: bool

    model_config = {"from_attributes": True}


class DrinkCreate(BaseModel):
    name: str
    color_hex: str
