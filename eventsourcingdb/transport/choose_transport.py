import asyncio
import json
from http import HTTPStatus

from ..errors import ServerError
from ..http_client import HttpClient
from ..is_valid_server_header import is_valid_server_header
from .error_of_answer import error_of_answer
from .statuses_without_v2_api import STATUSES_WITHOUT_V2_API
from .transport import Transport
from .v1 import V1Transport
from .v2 import V2Transport

PROBE_PATH = '/api/v2/system/ping'


class ChooseTransport:
    """
    The one place that chooses which version of the API the client speaks. On
    the first request of a client, it asks the server with a ping of the v2
    API whether it offers that API, and remembers the answer. Only a definite
    answer is remembered: if the ping fails in any other way, the request that
    needed it fails with that error, and the next request asks again. Requests
    that need the answer at the same time share a single ping. Once the server
    answers a path of the v2 API with 404 or 405, for example after it was
    rolled back to a version without it, the answer is forgotten, and the
    next request asks again. A request that needs the v2 API, such as a write
    with a recursive precondition, asks again as well if the answer is that
    the server does not offer it, since it may offer it by now, for example
    after an upgrade.
    """

    def __init__(self, http_client: HttpClient) -> None:
        self.__http_client = http_client
        self.__v1_transport = V1Transport(http_client)
        self.__transport: Transport | None = None
        self.__probe: asyncio.Task[Transport] | None = None

    async def get(self) -> Transport:
        if self.__transport is not None:
            return self.__transport

        # A ping that failed is never shared with a later request, even before
        # its callback has forgotten it.
        probe = self.__probe
        if (
            probe is None
            or probe.get_loop() is not asyncio.get_running_loop()
            or (probe.done() and not ChooseTransport.__succeeded(probe))
        ):
            probe = asyncio.create_task(self.__detect())
            probe.add_done_callback(self.__remember)
            self.__probe = probe

        # The ping goes on if one of the requests that wait for it is
        # cancelled, since the others still need it. Waiting for it, unlike
        # shielding it, does not make asyncio log the error of a ping that
        # fails after the request that waited for it was cancelled.
        await asyncio.wait({probe})
        return probe.result()

    async def get_asking_again_without_v2_api(self) -> Transport:
        # Forgetting the answer makes this request ask again, or wait for a
        # ping that asks already, as for every request that finds no answer.
        # So requests that ask again at the same time share a single ping.
        self.__forget(self.__v1_transport)
        return await self.get()

    def __remember(self, probe: asyncio.Task[Transport]) -> None:
        if self.__probe is probe:
            self.__probe = None

        if ChooseTransport.__succeeded(probe):
            self.__transport = probe.result()

    def __forget(self, transport: Transport) -> None:
        # Only the remembered transport is forgotten, and a ping that runs is
        # left alone. So a late answer to a request through a transport that
        # is forgotten already neither disturbs the ping that asks again, nor
        # discards the answer that it found.
        if self.__transport is transport:
            self.__transport = None

    @staticmethod
    def __succeeded(probe: asyncio.Task[Transport]) -> bool:
        # Asking for the exception also keeps asyncio from warning about one
        # that nobody retrieved, if no request waits for the ping anymore.
        return not probe.cancelled() and probe.exception() is None

    async def __detect(self) -> Transport:
        # The ping needs no API token, so it gets none.
        response = await self.__http_client.get(PROBE_PATH, with_authorization=False)
        async with response:
            # A proxy that only forwards the v1 API answers the ping itself,
            # so this answer does not need to come from EventSourcingDB. The
            # requests of the v1 API that follow make sure that they do.
            if response.status in STATUSES_WITHOUT_V2_API:
                return self.__v1_transport
            if not is_valid_server_header(response):
                raise ServerError('Server must be EventSourcingDB')
            if response.status != HTTPStatus.OK:
                raise await error_of_answer(response)

            response_body = await response.read()

        try:
            envelope = json.loads(response_body)
        except ValueError:
            envelope = None

        if (
            not isinstance(envelope, dict)
            or envelope.get('type') != 'event'
            or not isinstance(envelope.get('data'), dict)
            or envelope['data'].get('type') != 'io.eventsourcingdb.api.ping-received'
        ):
            raise ServerError(
                'Failed to find out whether the server offers the v2 API, it answered '
                f'with {response_body.decode("utf-8", errors="replace")}.'
            )

        # Every ping that finds the v2 API gets a transport of its own, so that
        # a request that makes the client forget the answer of one ping never
        # forgets the answer of a later one.
        return V2Transport(self.__http_client, self.__forget)
