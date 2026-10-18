from aiohttp import web

from eventsourcingdb import Event, EventCandidate, ReadEventsOptions

from .stream_server import StreamServer


async def read_events_from(lines: list[str]) -> list[Event]:
    """Reads events from a local server that answers with the given lines."""

    async def write_stream(response: web.StreamResponse) -> None:
        for line in lines:
            await response.write(line.encode('utf-8') + b'\n')

    async with StreamServer(write_stream) as server:
        return [
            event
            async for event in server.get_client().read_events(
                '/books/42', ReadEventsOptions(recursive=False)
            )
        ]


async def write_events_to(response_text: str) -> list[Event]:
    """Writes an event to a local server that answers with the given text."""

    async def write_stream(response: web.StreamResponse) -> None:
        await response.write(response_text.encode('utf-8'))

    async with StreamServer(write_stream) as server:
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
