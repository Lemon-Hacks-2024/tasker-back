from pydantic import BaseModel, Field


class BookingOrderRequestModel(BaseModel):
    train_id: int
    wagon_id: int
    seat_id: int


class BookingOrderResponseModel(BookingOrderRequestModel):
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



