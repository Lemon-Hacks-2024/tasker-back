import asyncio
import datetime
import logging

from watchfiles import awatch

from app.models import Income, WagonType, PlacePosition
from clients.axenix import AxenixClient
from clients.response_models import GetTrainsResponseModel, BookingOrderRequestModel, GetSeatsResponseModel, \
    BookingOrderRequestModelV2


class BookingService:
    def __init__(self, api_client: AxenixClient):
        self.client = api_client
        self.logger = logging.getLogger(self.__class__.__name__)

    async def wagons_processing(self, user_id: int, train_id: int, wagon_id: int, order_data: Income):
        seats = await self.client.get_wagon_info(train_id=train_id, wagon_id=wagon_id)
        _booking_params = []
        for seat in seats["seats"]:
            seat_id = self.seat_processing(seat, order_data)
            if seat_id is not None:
                _booking_params.extend([{
                    "user_id": user_id,
                    "params": BookingOrderRequestModel(
                        train_id=train_id,
                        wagon_id=wagon_id,
                        seat_ids=seat_id,
                    )
                }])
                if order_data.seats_qty is not None and order_data.seats_qty > 0:
                    if len(_booking_params) >= order_data.seats_qty:
                        break
                    else:
                        continue
                else:
                    break

        if order_data.need_nearby:
            seats_ids_list = [
                param["params"].seat_ids
                for param in _booking_params
            ]

            seats_nums = {
                seat.seat_num: seat.block
                for seat in seats["seats"]
                    if seat.seat_id in seats_ids_list
            }

            _nums = list(seats_nums.keys())
            _nums.sort(key=lambda x: x)
            _block = seats_nums.values()

            set_block = set(_block)
            if len(set_block) > 1:
                return None

            for i in range(1, len(_nums)):
                if abs(int(_nums[i- 1]) - int(_nums[i])) != 1:
                    return None

        return _booking_params

    async def train_processing(self, user_id: int, train_id: int, order_data: Income):
        train = await self.client.get_train_by_id(train_id=train_id)
        if train.available_seats_count == 0:
            return []

        train_wagons = train.wagons_info
        coroutines = []
        for wagon in train_wagons:
            wagon_type = wagon["type"]
            if order_data.wagon_type is not None:
                if wagon_type != order_data.wagon_type.value:
                    continue

            coroutines.append(
                self.wagons_processing(user_id, train_id, wagon["wagon_id"], order_data)
            )

        result = await asyncio.gather(*coroutines)
        to_handle = []
        for res in result:
            if res is not None:
                # yield res
                to_handle.append(res)
        return to_handle
        # return []

    async def need_booking_data_exist(
            self, order_data: Income
    ):
        train_id = order_data.train_id
        user_id = order_data.user_id
        wagon_id = order_data.wagon_id
        seat_id = order_data.seat_id

        booking_params = None
        if train_id is not None and wagon_id is not None and seat_id is not None:
            booking_params = [{
                "user_id": user_id,
                "params": BookingOrderRequestModel(
                    train_id=train_id,
                    wagon_id=wagon_id,
                    seat_id=seat_id,
                ),
            }]

        if train_id is not None and wagon_id is not None and seat_id is None:
            booking_params = await self.wagons_processing(user_id, train_id, wagon_id, order_data)

        if train_id is not None and wagon_id is None and seat_id is None:
            booking_params = await self.train_processing(user_id, train_id, order_data)


        if booking_params is None or len(booking_params) == 0:
            return None

        to_final_params = self.merge_dicts([
            params["params"]
            for params in booking_params
        ])

        booking_params = [{
            "user_id": user_id,
            "params": BookingOrderRequestModelV2.model_validate(to_final_params),
        }]
        booking_params = self.split_seats(booking_params)
        result = await self.client.booking(booking_params)
        return result

    async def processing_auto(self, order_data: Income):

        booking_result = await self.need_booking_data_exist(
            order_data
        )
        if booking_result is not None:
            return booking_result

        start_point, *_, end_point = order_data.route.split(" -> ")
        orders_for_route = await self.client.get_trains(
            start_point, end_point
        )
        self.logger.info(
            f"Всего найдено {len(orders_for_route)} "
            f"поездов по маршруту: {start_point} -> {end_point}"
        )

        suitable_date_range_trains = []
        for train in orders_for_route:
            date_from = datetime.datetime.strptime(
                order_data.date_from, "%d.%m.%Y %H:%M:%S"
            )
            date_to = datetime.datetime.strptime(
                order_data.date_to, "%d.%m.%Y %H:%M:%S"
            )
            # if date_to <= datetime.datetime.now():
            #     return False
            if date_from <= datetime.datetime.strptime(
                    train.startpoint_departure,
                    "%d.%m.%Y %H:%M:%S"
            ) <= date_to:
                suitable_date_range_trains.append(train)
        self.logger.info(
            f"Всего найдено: {len(suitable_date_range_trains)} "
            f"поездов подходящих по датам"
        )

        suitable_available_seats_count_trains = []
        for train in suitable_date_range_trains:
            if train.available_seats_count != 0:
                suitable_available_seats_count_trains.append(train)

        self.logger.info(
            f"Всего найдено: {len(suitable_available_seats_count_trains)} "
            f"со свободными местами"
        )

        final_booking_params = []
        for train in suitable_available_seats_count_trains:
            # booking_params = await self.train_processing(
            #     order_data.user_id, train.train_id, order_data
            # )
            # if booking_params is None or len(booking_params) == 0:
            #     return None
            # to_final_params = self.merge_dicts([
            #     params["params"]
            #     for params in booking_params
            # ])
            # final_booking_params.append({
            #     "user_id": order_data.user_id,
            #     "params": BookingOrderRequestModelV2.model_validate(to_final_params),
            # })
             for booking_params in await self.train_processing(order_data.user_id, train.train_id, order_data):
                if booking_params is None or len(booking_params) == 0:
                    return None
                to_final_params = self.merge_dicts([
                    params["params"]
                    for params in booking_params
                ])
                final_booking_params.append({
                    "user_id": order_data.user_id,
                    "params": BookingOrderRequestModelV2.model_validate(to_final_params),
                })

        final_booking_params = self.merge_seats_by_train_and_wagon(final_booking_params)
        final_booking_params = self.group_common_train(final_booking_params)
        final_booking_params = self.split_and_merge_seats(final_booking_params)
        result = await self.client.booking(final_booking_params)
        return result

    @staticmethod
    def get_seat_position(seat_num: str):
        if int(seat_num) % 2 == 0:
            return PlacePosition.UP.value
        else:
            return PlacePosition.DOWN.value

    def seat_processing(self, seat: GetSeatsResponseModel, order_data: Income):
        seat_id = None

        if seat.booking_status == "FREE":
            seat_id = seat.seat_id
        else:
            return None

        if order_data.place_position is not None:
            seat_position = self.get_seat_position(seat.seat_num)
            if seat_position in order_data.place_position:
                seat_id = seat.seat_id
            else:
                return None

        if order_data.price is not None:
            if seat.price <= order_data.price:
                seat_id = seat.seat_id
            else:
                return None
        return seat_id

    @staticmethod
    def get_wagons_ids(
            suitable_available_seats_count_trains: list[GetTrainsResponseModel],
            wagon_type: WagonType = None
    ):
        result = []
        for train in suitable_available_seats_count_trains:
            wagons = train.wagons_info
            for wagon in wagons:
                if wagon_type is not None:
                    if wagon["wagonType"] == wagon_type.value:
                        result.append({
                            "train_id": train.train_id,
                            "wagon_id": wagon["wagon_id"]
                        })
                else:
                    result.append({
                        "train_id": train.train_id,
                        "wagon_id": wagon["wagon_id"]
                    })
        return result

    @staticmethod
    def merge_dicts(dicts):
        merged_dict = {}
        for d in dicts:
            for key, value in d.model_dump().items():
                if key in merged_dict and not isinstance(merged_dict[key], list) and merged_dict[key] != value:
                    merged_dict[key] = [merged_dict[key], value]
                elif key in merged_dict and isinstance(merged_dict[key], list):
                    if value not in merged_dict[key]:
                        merged_dict[key].append(value)
                else:
                    merged_dict[key] = value
        return merged_dict

    @staticmethod
    def split_seats(final_booking_params: list):
        result = []
        max_seats = 10

        for order in final_booking_params:
            user_id = order['user_id']
            params = order['params']

            seat_ids = params.seat_ids

            for i in range(0, len(seat_ids), max_seats):
                chunk = seat_ids[i:i + max_seats]
                new_params = BookingOrderRequestModelV2(train_id=params.train_id, wagon_id=params.wagon_id,
                                                        seat_ids=chunk)
                result.append({'user_id': user_id, 'params': new_params})

        return result

    @staticmethod
    def split_and_merge_seats(orders):
        result = []
        max_seats = 10
        merged_orders = {}

        for order in orders:
            user_id = order['user_id']
            params = order['params']
            seat_ids = params.seat_ids

            # Проверка на необходимость объединения
            if params.train_id in merged_orders and len(seat_ids) <= 2:
                existing_order = merged_orders[params.train_id]
                if len(existing_order['params'].seat_ids) <= 2:
                    # Объединяем места из обоих заказов
                    combined_seat_ids = existing_order['params'].seat_ids + seat_ids
                    if len(combined_seat_ids) <= max_seats:
                        existing_order['params'].seat_ids = combined_seat_ids
                        continue

            # Если объединение не произошло, разбиваем на чанки по max_seats
            for i in range(0, len(seat_ids), max_seats):
                chunk = seat_ids[i:i + max_seats]
                new_params = BookingOrderRequestModelV2(train_id=params.train_id, wagon_id=params.wagon_id,
                                                        seat_ids=chunk)
                new_order = {'user_id': user_id, 'params': new_params}

                # Добавляем новый заказ в результаты и словарь для объединения
                result.append(new_order)
                merged_orders[params.train_id] = new_order

        return result

    @staticmethod
    def merge_seats_with_same_train_id(orders):
        result = []
        seat_limit = 10
        merged_orders = {}

        # Обрабатываем каждый заказ
        for order in orders:
            user_id = order['user_id']
            params = order['params']
            train_id = params.train_id
            seat_ids = params.seat_ids

            if train_id in merged_orders and len(seat_ids) <= seat_limit:
                existing_order = merged_orders[train_id]
                if len(existing_order['params'].seat_ids) <= seat_limit:
                    combined_seat_ids = existing_order['params'].seat_ids + seat_ids
                    if len(combined_seat_ids) <= 10:
                        existing_order['params'].seat_ids = combined_seat_ids
                    else:
                        continue
            else:
                if len(seat_ids) <= seat_limit:
                    merged_orders[train_id] = {
                        'user_id': user_id,
                        'params': BookingOrderRequestModelV2(train_id=params.train_id, wagon_id=params.wagon_id,
                                                             seat_ids=seat_ids)
                    }

        result = list(merged_orders.values())

        return result

    @staticmethod
    def merge_seats_by_train_and_wagon(orders):
        merged_orders = {}

        for order in orders:
            user_id = order['user_id']
            params = order['params']
            train_id = params.train_id
            wagon_id = params.wagon_id
            seat_ids = params.seat_ids

            # Создаем уникальный ключ для комбинации train_id и wagon_id
            key = (train_id, wagon_id)

            # Если ключ уже существует, объединяем seat_ids
            if key in merged_orders:
                merged_orders[key]['params'].seat_ids.extend(seat_ids)
            else:
                # Добавляем новый заказ в словарь для будущего объединения
                merged_orders[key] = {
                    'user_id': user_id,
                    'params': BookingOrderRequestModelV2(train_id=train_id, wagon_id=wagon_id, seat_ids=seat_ids)
                }

        # Возвращаем список объединённых заказов
        return list(merged_orders.values())

    @staticmethod
    def group_common_train(orders):
        result = []
        train_id = None

        for order in orders:
            if train_id is None:
                train_id = order["params"].train_id
            if order["params"].train_id == train_id:
                result.append(order)
            else:
                continue

        return result
