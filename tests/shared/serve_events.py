from aiohttp import web

from eventsourcingdb import Event, EventCandidate, ReadEventsOptions

from .stream_server import Api, StreamServer

END_LINE = '{"type":"end","data":{}}'


async def read_events_from(lines: list[str], api: Api = 'v1') -> list[Event]:
    """
    Reads events from a local server that answers with the given lines, and
    with the end item that the v2 API sends after them.
    """

    async def write_stream(response: web.StreamResponse) -> None:
        for line in lines + ([END_LINE] if api == 'v2' else []):
            await response.write(line.encode('utf-8') + b'\n')

    async with StreamServer(write_stream, api=api) as server:
        return [
            event
            async for event in server.get_client().read_events(
                '/books/42', ReadEventsOptions(recursive=False)
            )
        ]


async def write_events_to(response_text: str, api: Api = 'v1') -> list[Event]:
    """Writes an event to a local server that answers with the given text."""

    async def write_stream(response: web.StreamResponse) -> None:
        await response.write(response_text.encode('utf-8'))

    async with StreamServer(write_stream, api=api) as server:
        return await server.get_client().write_events(
            [
                EventCandidate(
                    source='https://www.eventsourcingdb.io',
                    subject='/books/42',
                    type='io.eventsourcingdb.library.book-acquired',
                    data={},
                )
            ]
        )
