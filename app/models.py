import enum

from pydantic import BaseModel

class WagonType(enum.Enum):
    PLATZCART = "PLATZCART"
    COUPE = "COUPE"


class PlacePosition(enum.Enum):
    UP = "upper"
    DOWN = "lower"


class Income(BaseModel):
    user_id: int
    train_id: int | None = None
    wagon_id: int | None = None
    seat_id: int | None = None
    route: str
    date_from: str
    date_to: str
    wagon_type: WagonType | None = None
    place_position: list[str] | None = None
    price: float | None = None
    seats_qty: int | None = None
    need_nearby: bool | None = None
