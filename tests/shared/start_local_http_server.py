from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.client_options import ClientOptions
from flask import Flask, Response, make_response
from multiprocessing import Process
from typing import Callable
from .util.get_random_available_port import get_random_available_port

Handler = Callable[[Response], Response]
AttachHandler = Callable[[str, str, Handler], None]
AttachHandlers = Callable[[AttachHandler], None]
StopServer = Callable[[], None]


def start_local_http_server(attach_handlers: AttachHandlers) -> (Client, StopServer):
    app = Flask('local')

    def attach_handler(route: str, method: str, handler: Handler):
        @app.route(route, methods=[method])
        def attached_handler():
            response = make_response()
            return handler(response)

    attach_handlers(attach_handler)

    port = get_random_available_port()

    def start():
        app.run(host='localhost', port=port)

    server = Process(target=start)
    server.start()

    def stop_server():
        server.terminate()
        server.join()

    client = Client(f'http://localhost:{port}', ClientOptions(max_tries=2))

    return client, stop_server
