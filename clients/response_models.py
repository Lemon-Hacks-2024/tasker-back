from pydantic import BaseModel, Field, model_validator


class BookingOrderRequestModel(BaseModel):
    train_id: int
    wagon_id: int
    seat_ids: int


class BookingOrderRequestModelV2(BookingOrderRequestModel):
    seat_ids: list[int]

    @model_validator(mode="before")
    def validate_seat_ids(self, v):
        if isinstance(self.get("seat_ids"), int):
            self["seat_ids"] = [self.get("seat_ids")]
        return self



class BookingOrderResponseModel(BookingOrderRequestModelV2):
    user_id: int
    booking_date: str
    order_id: int


class GetTrainsRequestModel(BaseModel):
    booking_available: bool
    start_point: str
    end_point: str
    stop_points: str


class GetTrainsResponseModel(BaseModel):
    train_id: int
    startpoint_departure: str
    wagons_info: list
    available_seats_count: int


class GetWagonsInfoResponseModel(BaseModel):
    type: str
    seats: dict


class GetSeatsResponseModel(BaseModel):
    seat_id: int
    seat_num: str = Field(..., alias='seatNum')
    block: str
    price: int
    booking_status: str = Field(..., alias='bookingStatus')



