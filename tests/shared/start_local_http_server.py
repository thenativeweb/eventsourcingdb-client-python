from collections.abc import Callable
from multiprocessing import Process

import requests
from flask import Flask, Response, make_response

from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.client_options import ClientOptions
from eventsourcingdb_client_python.util.retry.retry_with_backoff import \
    Retry, \
    Return, \
    retry_with_backoff

from .util.get_random_available_port import get_random_available_port

Handler = Callable[[Response], Response]
AttachHandler = Callable[[str, str, Handler], None]
AttachHandlers = Callable[[AttachHandler], None]
StopServer = Callable[[], None]


def start_local_http_server(attach_handlers: AttachHandlers) -> (Client, StopServer):
    app = Flask('local')
    port = get_random_available_port()

    def attach_handler(route: str, method: str, handler: Handler):
        @app.route(route, methods=[method])
        def attached_handler():
            response = make_response()
            return handler(response)

    attach_handlers(attach_handler)

    @app.get('/__python_test__/ping')
    def ping():
        return "OK"

    def ping_app():
        response: requests.Response
        try:
            response = requests.get(f'http://localhost:{port}/__python_test__/ping', timeout=1)
        except requests.exceptions.RequestException as error:
            return Retry(cause=error)
        if not response.ok:
            return Retry(cause=ValueError("Response is not OK."))

        return Return(None)

    def start():
        app.run(host='localhost', port=port)

    server = Process(target=start)
    server.start()
    retry_with_backoff(10, ping_app)

    def stop_server():
        server.terminate()
        server.join()

    client = Client(f'http://localhost:{port}', ClientOptions(max_tries=2))

    return client, stop_server
