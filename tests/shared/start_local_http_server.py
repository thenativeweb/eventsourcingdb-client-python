import asyncio
from collections.abc import Callable
from multiprocessing import get_context

import aiohttp
from flask import Flask, Response, make_response

from eventsourcingdb.client import Client
from eventsourcingdb.client_options import ClientOptions
from eventsourcingdb.util.retry.retry_with_backoff import retry_with_backoff
from eventsourcingdb.util.retry.retry_result import Retry, Return, RetryResult

from .util.get_random_available_port import get_random_available_port

Handler = Callable[[Response], Response]
AttachHandler = Callable[[str, str, Handler], None]
AttachHandlers = Callable[[AttachHandler], None]
StopServer = Callable[[], None]


class LocalHttpServer():
    def __init__(self, attach_handlers: AttachHandlers):
        self.port = get_random_available_port()
        self.app = Flask('local')

        def attach_handler(route: str, method: str, handler: Handler):
            @self.app.route(route, methods=[method])
            def attached_handler():
                response = make_response()
                return handler(response)

        attach_handlers(attach_handler)

        @self.app.get('/__python_test__/api/v1/ping')
        def ping():
            return "OK"

    @staticmethod
    def start(this: 'LocalHttpServer'):
        this.app.run(host='localhost', port=this.port)


async def start_local_http_server(attach_handlers: AttachHandlers) -> tuple[Client, StopServer]:
    local_http_server = LocalHttpServer(attach_handlers)

    async def ping_app() -> RetryResult[None]:
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5.0)  # Increase timeout to 5 seconds
        )

        async with session:
            try:
                response = await session.get(
                    f'http://localhost:{local_http_server.port}/__python_test__/api/v1/ping',
                    timeout=aiohttp.ClientTimeout(total=5.0)  # Explicit timeout here too
                )
            except aiohttp.ClientError as error:
                return Retry(cause=error)
            except asyncio.TimeoutError as error:
                return Retry(cause=error)  # Handle timeout explicitly
            if not response.ok:
                return Retry(cause=ValueError("Response is not OK."))

        return Return(None)

    multiprocessing = get_context('fork')
    server = multiprocessing.Process(target=LocalHttpServer.start, args=(local_http_server, ))
    server.start()

    # Increase number of retries for server to become available
    await retry_with_backoff(15, ping_app)  # Increased from 10 to 15 retries

    def stop_server():
        server.terminate()
        server.join()

    client = Client(
        f'http://localhost:{local_http_server.port}',
        'access-token',
        ClientOptions(max_tries=3)  # Increase max_tries from 2 to 3
    )
    await client.initialize()

    return client, stop_server
