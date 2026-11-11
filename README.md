# eventsourcingdb

The official Python client SDK for [EventSourcingDB](https://www.eventfoundation.io/products/eventsourcingdb) – a purpose-built database for event sourcing.

The complete documentation of this client SDK, including preconditions, EventQL, observing events, handling errors, Testcontainers, and upgrading, is available at **[https://www.eventfoundation.io/docs/eventsourcingdb/sdks/python](https://www.eventfoundation.io/docs/eventsourcingdb/sdks/python)**.

## Getting Started

Install the client SDK:

```shell
pip install eventsourcingdb
```

Create a client with the URL of your EventSourcingDB instance and the API token to use, and check whether the instance is reachable:

```python
from eventsourcingdb import Client

url = 'http://localhost:3000'
api_token = 'secret'

client = Client(
  base_url = url,
  api_token = api_token,
)

await client.ping()
```

Write an event:

```python
from eventsourcingdb import EventCandidate

written_events = await client.write_events(
  event_candidates = [
    EventCandidate(
      source = 'https://library.eventsourcingdb.io',
      subject = '/books/42',
      type = 'io.eventsourcingdb.library.book-acquired',
      data = {
        'title': '2001 – A Space Odyssey',
        'author': 'Arthur C. Clarke',
        'isbn': '978-0756906788',
      },
    )
  ]
)
```

Read the events of a subject:

```python
from eventsourcingdb import ReadEventsOptions

async for event in client.read_events(
  subject = '/books/42',
  options = ReadEventsOptions(
    recursive = False
  ),
):
  pass
```

For everything else, see the **[complete documentation](https://www.eventfoundation.io/docs/eventsourcingdb/sdks/python)**.
