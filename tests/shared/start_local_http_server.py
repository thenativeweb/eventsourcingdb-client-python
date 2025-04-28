import asyncio
from collections.abc import Callable
from multiprocessing import get_context

import aiohttp
from flask import Flask, Response, make_response

from eventsourcingdb.client import Client
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

    multiprocessing = get_context('fork')
    server = multiprocessing.Process(target=LocalHttpServer.start, args=(local_http_server, ))
    server.start()

    # Warte auf den Server, bis er bereit ist
    async def ping_app():
        retry_count = 0
        max_retries = 5
        retry_delay = 0.5

        async with aiohttp.ClientSession() as session:
            while retry_count < max_retries:
                try:
                    await session.get(
                        f"http://localhost:{local_http_server.port}/__python_test__/api/v1/ping",
                    )
                    # Wenn die Anfrage erfolgreich ist, brechen wir die Schleife ab
                    return True
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    retry_count += 1
                    await asyncio.sleep(retry_delay)

            # Wenn alle Versuche fehlschlagen, geben wir False zurück
            return False

    # Versuche, den Server zu erreichen
    server_ready = await ping_app()
    if not server_ready:
        server.terminate()
        server.join()
        raise RuntimeError(f"Failed to start HTTP server on port {local_http_server.port}")

    def stop_server():
        server.terminate()
        server.join()

    client = Client(
        f'http://localhost:{local_http_server.port}',
        'access-token',
    )
    await client.initialize()

    return client, stop_server
