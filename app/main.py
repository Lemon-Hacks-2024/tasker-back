import asyncio
import logging
import sys

from faststream import FastStream
from faststream.rabbit import RabbitBroker
from faststream.exceptions import AckMessage, NackMessage

from app.models import Income
from app.service import BookingService
from app.settings import settings
from clients.axenix import AxenixClient
from clients.internal import InternalClient

settings.setup_architecture()
settings.setup_logging()

broker = RabbitBroker(url=settings.amqp_url)
app = FastStream(broker)
service = BookingService(AxenixClient())
logger = logging.getLogger(__name__)


@broker.subscriber(
    queue=settings.RMQ_QUEUE
)
async def collect_new_bookings_tickets(
        body: Income
):
    result = await service.processing_auto(body)
    if not result:
        if isinstance(result, bool):
            logger.warning("Время брони вышло")
            raise AckMessage()
        logger.error("Ошибка брони")
        raise NackMessage()
    else:
        logger.info("Заказ успешно создан")
        coroutines = [
            InternalClient.save_new_order(res)
            for res in result
        ]
        await asyncio.gather(*coroutines)
        raise AckMessage()


if __name__ == '__main__':
    try:
        asyncio.run(app.run())
    except Exception as e:
        logger.exception(e)


