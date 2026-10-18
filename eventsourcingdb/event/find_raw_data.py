import json
import re
from collections.abc import Iterator

# The hash of an event covers its data exactly as the server sent it. Parsing
# the data and serializing it again does not reproduce these bytes, since the
# server writes some characters differently than Python does: it escapes < and
# keeps ü, for example. Hence, these functions find the data in the raw text of
# a response. They expect text that has already been parsed as JSON.

DECODER = json.JSONDecoder()
WHITESPACE = re.compile(r'[ \t\n\r]*')


def find_raw_data_of_event(text: str, index: int = 0) -> bytes | None:
    """
    Returns the data of the event whose JSON object starts at the given index,
    byte for byte as the server sent it, or None if the event has no data.
    """
    span = find_member(text, index, 'data')
    if span is None:
        return None

    start, end = span
    return text[start:end].encode('utf-8')


def find_raw_data_of_events(text: str) -> list[bytes | None]:
    """
    Returns the data of every event in a JSON array of events, as the response
    of writing events contains it.
    """
    return [find_raw_data_of_event(text, start) for start, _ in iterate_elements(text, 0)]


def find_raw_data_of_stream_item(text: str) -> bytes | None:
    """
    Returns the data of the event in the payload of a stream item, as reading
    and observing events return it.
    """
    span = find_member(text, 0, 'payload')
    if span is None:
        return None

    return find_raw_data_of_event(text, span[0])


def find_member(text: str, index: int, key: str) -> tuple[int, int] | None:
    """
    Returns the span of the value of the given member of the JSON object that
    starts at the given index. Like json.loads, it takes the last one if the
    object contains the key more than once.
    """
    span = None
    for member_key, start, end in iterate_members(text, index):
        if member_key == key:
            span = (start, end)

    return span


def iterate_members(text: str, index: int) -> Iterator[tuple[str, int, int]]:
    index = skip_whitespace(text, index)
    expect(text, index, '{')
    index = skip_whitespace(text, index + 1)
    if text[index:index + 1] == '}':
        return

    while True:
        key, index = DECODER.raw_decode(text, index)
        index = skip_whitespace(text, index)
        expect(text, index, ':')
        value_start = skip_whitespace(text, index + 1)
        _, value_end = DECODER.raw_decode(text, value_start)

        yield key, value_start, value_end

        index = skip_whitespace(text, value_end)
        if text[index:index + 1] != ',':
            break
        index = skip_whitespace(text, index + 1)

    expect(text, index, '}')


def iterate_elements(text: str, index: int) -> Iterator[tuple[int, int]]:
    index = skip_whitespace(text, index)
    expect(text, index, '[')
    index = skip_whitespace(text, index + 1)
    if text[index:index + 1] == ']':
        return

    while True:
        _, value_end = DECODER.raw_decode(text, index)

        yield index, value_end

        index = skip_whitespace(text, value_end)
        if text[index:index + 1] != ',':
            break
        index = skip_whitespace(text, index + 1)

    expect(text, index, ']')


def skip_whitespace(text: str, index: int) -> int:
    match = WHITESPACE.match(text, index)
    if match is None:
        return index

    return match.end()


def expect(text: str, index: int, character: str) -> None:
    if text[index:index + 1] != character:
        raise ValueError(f"Expected '{character}' at position {index}.")
