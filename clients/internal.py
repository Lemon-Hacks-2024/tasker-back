import logging

import httpx

from app.settings import settings
from clients.response_models import BookingOrderResponseModel


class InternalClient:
    __headers = {
        "x-key": settings.BACK_X_KEY
    }
    __logger = logging.getLogger("internalclient")

    @classmethod
    async def save_new_order(cls, body: BookingOrderResponseModel):
        url = "https://api.t-app.ru/ax-train/booked-tickets/"
        async with httpx.AsyncClient(headers=cls.__headers) as client:
            response = await client.post(
                url=url,
                json=body.model_dump(),
            )
            if response.status_code != 201:
                cls.__logger.error(
                    f"Ошибка передачи заказа: {body.order_id}. "
                    f"[{response.status_code}] - {response.text}"
                )
                return None
            else:
                cls.__logger.info(
                    "Заказ успешно передан"
                )
                return None