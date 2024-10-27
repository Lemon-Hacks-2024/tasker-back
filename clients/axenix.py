import asyncio
import datetime
import random
from typing import OrderedDict

from httpx import Response

from clients.api_client import BaseApiClientAbstract
from clients.response_models import BookingOrderResponseModel, BookingOrderRequestModel, GetTrainsResponseModel, \
    GetWagonsInfoResponseModel, GetSeatsResponseModel, BookingOrderRequestModelV2

from app.settings import settings


class AxenixClient(BaseApiClientAbstract):
    request_per_seconds = 2
    seconds = 1
    request_times = OrderedDict.fromkeys(
        range(request_per_seconds), None
    )

    __base_url = "http://84.252.135.231/"
    # __base_url = "http://localhost:8000/"
    # __base_url = "https://api.t-app.ru/ax-train/mocks/"
    __booking_url = __base_url + "api/order"
    __get_trains_url = __base_url + "api/info/trains"
    __get_train_url = __base_url + "api/info/train"
    __get_wagon_url = __base_url + "api/info/seats"
    __auth_url = __base_url + "api/auth/login"
    __auth_token = None

    class NoneTokenException(Exception):
        ...

    class AuthError(Exception):
        ...

    def check_token(self):
        if self.__auth_token is None:
            self.log_with_task_id(
                "warning",
                "Токен отсутствует"
            )
            raise self.NoneTokenException()

    async def __booking(self, user_id: int, body: BookingOrderRequestModelV2):
        self.log_with_task_id(
            "info",
            f"Бронирование заказ для пользователя: {user_id} "
            f"-> Места: {body.seat_ids}"
        )
        response = await self.get_page(
            self.__booking_url,
            headers={
                "Authorization": f"Bearer {self.__auth_token}"
            },
            json_format=True,
            json_data=body.model_dump(),
            limit_request=True,
            method="post"
        )
        if isinstance(response, dict):
            order_id = response.get("order_id")
            assert order_id is not None
            self.log_with_task_id(
                "info",
                f"Для пользователя {user_id} успешно "
                f"забронирован заказ [{order_id}]"
            )
            return BookingOrderResponseModel(
                **body.model_dump(),
                user_id=user_id,
                order_id=order_id,
                booking_date=datetime.datetime.now().strftime(
                    "%d.%m.%Y %H:%M:%S"
                )
            )
        elif isinstance(response, Response):
            self.log_with_task_id(
                "error",
                f"Ошибка бронирования заказа для {user_id}. "
                f"[{response.status_code}] - {response.text}"
            )
            if response.status_code == 403:
                async with self.lock:
                    self.__auth_token = None
            return None

    async def __auth(self):
        self.log_with_task_id(
            "debug",
            "Попытка авторизоваться в системе Axenix"
        )
        response = await self.get_page(
            self.__auth_url,
            method="post",
            json_data=settings.axenix_auth_data,
            json_format=True,
            limit_request=True,
        )
        if isinstance(response, dict):
            self.log_with_task_id(
                "info",
                "Успешная авторизация"
            )
            async with self.lock:
                self.__auth_token = response["token"]
        elif isinstance(response, Response):
            self.log_with_task_id(
                "error",
                f"Ошибка авторизации - "
                f"[{response.status_code}] - {response.text}"
            )
            raise self.AuthError()
        else:
            self.log_with_task_id(
                "error",
                "Неизвестная ошибка авторизации"
            )
            raise self.AuthError()


    async def booking(
            self,
            orders_to_booking: list[dict[str, BookingOrderRequestModelV2 | int]]
    ) -> list[BookingOrderResponseModel | None]:
        try:
            self.check_token()
        except self.NoneTokenException:
            try:
                await self.__auth()
            except self.AuthError:
                return []
        coroutines = []
        for order in orders_to_booking:
            coroutines.append(self.__booking(
                order["user_id"], order["params"]
            ))
        self.log_with_task_id(
            "info",
            f"Бронирование {len(coroutines)} заказов"
        )
        result = await asyncio.gather(*coroutines)
        return result

    async def get_trains(self, from_: str, to_: str):
        try:
            self.check_token()
        except self.NoneTokenException:
            try:
                await self.__auth()
            except self.AuthError:
                return []
        response = await self.get_page(
            self.__get_trains_url, headers={
                "Authorization": f"Bearer {self.__auth_token}"
            },
            json_format=True,
            limit_request=True,
            method="get",
            params={
                "booking_available": True,
                "start_point": from_,
                "end_point": to_
            }
        )
        if isinstance(response, list):
            self.log_with_task_id(
                "info",
                f"Маршруты для {from_} -> {to_} успешно получены"
            )
            result = list(map(
                lambda x: GetTrainsResponseModel.model_validate(x),
                response
            ))
            return result
        elif isinstance(response, Response):
            self.log_with_task_id(
                "error",
                f"Ошибка в получения маршрутов для {from_} -> {to_}. "
                f"[{response.status_code}] - {response.text}"
            )
            return []

    async def get_train_by_id(self, train_id: int):
        try:
            self.check_token()
        except self.NoneTokenException:
            try:
                await self.__auth()
            except self.AuthError:
                return []
        response = await self.get_page(
            self.__get_train_url + f"/{train_id}", headers={
                "Authorization": f"Bearer {self.__auth_token}"
            },
            json_format=True,
            limit_request=True,
            method="get"
        )
        if isinstance(response, dict):
            self.log_with_task_id(
                "info",
                f"Маршрут для {train_id} успешно получен"
            )
            return GetTrainsResponseModel.model_validate(response)
        elif isinstance(response, Response):
            self.log_with_task_id(
                "error",
                f"Ошибка в получения маршрута для {train_id} "
                f"[{response.status_code}] - {response.text}"
            )
            return []

    async def get_wagon_info(self, train_id: int, wagon_id: int):
        try:
            self.check_token()
        except self.NoneTokenException:
            try:
                await self.__auth()
            except self.AuthError:
                return []
        response = await self.get_page(
            self.__get_wagon_url,
            headers={
                "Authorization": f"Bearer {self.__auth_token}"
            },
            params={
                "wagonId": wagon_id
            },
            json_format=True,
            limit_request=True,
            method="get"
        )
        if isinstance(response, list):
            self.log_with_task_id(
                "info",
                f"Данные по вагону {wagon_id} успешно получены"
            )
            result = list(map(lambda x: GetSeatsResponseModel(**x), response))
            return {
                "train_id": train_id,
                "wagon_id": wagon_id,
                "seats": result
            }
        elif isinstance(response, Response):
            self.log_with_task_id(
                "error",
                f"Ошибка получения данных по вагону: {wagon_id}"
            )
            return []

    async def auth(self):
        await self.__auth()





