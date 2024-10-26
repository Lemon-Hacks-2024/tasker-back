import asyncio
import json
import logging
import time
import uuid
from abc import ABC
from collections import OrderedDict

import httpx


class BaseApiClientAbstract(ABC):
    seconds = 1.0
    request_per_seconds = 5
    request_times = OrderedDict.fromkeys(
        range(request_per_seconds), None
    )

    max_retry_count = 5
    async_client = None

    timeout_make_requests = 0.1
    reserved_waiting_value = -1
    lock = asyncio.Lock()

    logger = logging.getLogger(__name__)

    def _create_session(self):
        """Создание асинхронного клиента"""
        self.async_client = httpx.AsyncClient()

    def log_with_task_id(self, level="debug", message=""):
        current_task = asyncio.current_task()
        task_id = current_task.get_name() if current_task else "Main"

        getattr(self.logger, level)(f"[{task_id}] - {message}"[:1000])

    async def make_request(self, key):
        """
        Аргументы:
            key (uuid): Ключ для словаря, по которому добавить значение

        Возвращает:
            tuple[bool, float]: Возможность сделать запрос и время для ожидания
        """
        async with self.lock:
            value = list(self.request_times.values())[0]
            possible = True
            remaining_time = 0
            if value == self.reserved_waiting_value:
                possible = False
                remaining_time = self.timeout_make_requests
            elif value is not None:
                wait_time = value + self.seconds - time.time()
                if wait_time > 0:
                    remaining_time = wait_time
            if possible:
                self.request_times.popitem(last=False)
                self.request_times.update({key: self.reserved_waiting_value})
            return possible, remaining_time

    async def update_times(self, key):
        async with self.lock:
            self.request_times.update({key: time.time()})

    async def get_page(
            self, url, params=None, headers=None,
            method="get", limit_request=True, timeout=60,
            json_format=False, if_error_return=False,
            json_data=None, log_fails=True, expected_status=(200, ),
    ):
        """
        Аргументы:
            client (httpx.AsyncClient): клиент для запросов
            url (str): ссылка для запроса
            params (dict | None): параметры запроса
            limit_request (bool): ограничивать ли количество запросов в секунду
            timeout (int): таймаут для запросов
            json_format (bool): форматироваль ли в json
            if_error_return (bool): возвращать ли результат сразу после ошибки
            json_data (dict | None): json параметр запроса
            log_fails (bool): при наличии ошибки выводить ли текст ответа

        Возвращает:
            (httpx.Response | dict): ответ запроса, либо декодированный в dict,
                либо чистый response
        """
        if self.async_client is None:
            self._create_session()
        retry_count = 0
        resp_json = None
        response = None
        error_req = False
        args = {
            "url": url,
            "params": params,
            "headers": headers,
            "timeout": timeout,
        }
        if json_data:
            args["json"] = json_data

        # делаем запрос self.max_retry_count раз, пока не получим ответ
        while retry_count < self.max_retry_count:
            error_req = False
            if limit_request:
                # если требуется ограничение запросов в секунду, то проверяем
                # возможность сделать запрос
                key = uuid.uuid4()
                possible = False
                while not possible:
                    possible, remaining_time = await self.make_request(key)
                    if remaining_time != self.timeout_make_requests:
                        self.log_with_task_id(
                            level="debug",
                            message=f"Ожидаем перед запросом {remaining_time}s"
                        )
                    await asyncio.sleep(remaining_time)
            try:
                self.log_with_task_id(
                    level="debug",
                    message=f"Попытка получить данные с аргументами: {args}")

                if limit_request:
                    await self.update_times(key)

                time_start = time.time()
                response = await getattr(self.async_client, method)(**args)
                time_end = round(time.time() - time_start, 1)
                resp_json = response
                response.raise_for_status()
            except httpx.ConnectTimeout:
                error_req = True
                self.log_with_task_id(
                    level="warning",
                    message=(
                        f"ConnectTimeout! Retry_count: {retry_count}, "
                        f"args: {args}"
                    )
                )
                continue
            except httpx.ReadTimeout:
                error_req = True
                self.log_with_task_id(
                    level="warning",
                    message=(
                        f"ReadTimeout! Retry_count: {retry_count}, "
                        f"args: {args}"
                    )
                )
                continue
            except httpx.HTTPStatusError as err:
                error_req = True
                if response.status_code in [500, 501, 502, 503, 504]:
                    self.log_with_task_id(
                        level="warning",
                        message=(
                            f"Status code: {response.status_code}, "
                            f"retry_count: {retry_count}, args: {args}"
                        )
                    )
                    continue
                self.log_with_task_id(
                    level="exception",
                    message=err
                )
                continue
            except httpx.RequestError as err:
                error_req = True
                self.log_with_task_id(
                    level="exception",
                    message=err
                )
                continue
            except Exception as err:
                error_req = True
                self.log_with_task_id(
                    level="exception",
                    message=err
                )
                continue
            finally:
                if error_req:
                    retry_count += 1
                    if log_fails and response:
                        self.log_with_task_id(
                            level="error",
                            message=response.text
                        )

                    if if_error_return:
                        return response
            content_len = len(response.content)
            self.log_with_task_id(
                level="debug",
                message=(
                    "Ответ сервера [время запроса {}] "
                    "[статус {}] [размер ответа {}] [url {}]".format(
                        time_end, response.status_code,
                        content_len, url
                    )
                )
            )
            resp_json = response
            if response.status_code in expected_status:
                try:
                    if json_format:
                        resp_json = response.json()
                    break
                except json.JSONDecodeError:
                    self.log_with_task_id(
                        level="error",
                        message=f"response: {response.text}"
                    )
                    retry_count += 1
                    continue
        return resp_json
