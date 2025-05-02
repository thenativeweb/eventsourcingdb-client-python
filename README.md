# eventsourcingdb

The official Python client SDK for [EventSourcingDB](https://www.eventsourcingdb.io) – a purpose-built database for event sourcing.

EventSourcingDB enables you to build and operate event-driven applications with native support for writing, reading, and observing events. This client SDK provides convenient access to its capabilities in Python.

For more information on EventSourcingDB, see its [official documentation](https://docs.eventsourcingdb.io/).

This client SDK includes support for [Testcontainers](https://testcontainers.com/) to spin up EventSourcingDB instances in integration tests. For details, see [Using Testcontainers](#using-testcontainers).

## Getting Started

Install the client SDK:

```shell
pip install eventsourcingdb
```

Import the `Client` class and create an instance by providing the URL of your EventSourcingDB instance and the API token to use:

```python
from eventsourcingdb import Client

url = 'http://localhost:3000'
api_token = 'secret'

client = Client(
  base_url = url,
  api_token = api_token,
)
```

Then call the `ping` function to check whether the instance is reachable. If it is not, the function will raise an error:

```python
await client.ping()
```

*Note that `ping` does not require authentication, so the call may succeed even if the API token is invalid.*

If you want to verify the API token, call `verify_api_token`. If the token is invalid, the function will raise an error:

```python
await client.verify_api_token()
```

### Writing Events

Call the `write_events` function and hand over a list with one or more events. You do not have to provide all event fields – some are automatically added by the server.

Specify `source`, `subject`, `type`, and `data` according to the [CloudEvents](https://docs.eventsourcingdb.io/fundamentals/cloud-events/) format.

The function returns the written events, including the fields added by the server:

```python
written_events = await client.write_events(
  events = [
    {
      'source': 'https://library.eventsourcingdb.io',
      'subject': '/books/42',
      'type': 'io.eventsourcingdb.library.book-acquired',
      'data': {
        'title': '2001 – A Space Odyssey',
        'author': 'Arthur C. Clarke',
        'isbn': '978-0756906788',
      },
    }
  ]
)
```

#### Using the `isSubjectPristine` precondition

If you only want to write events in case a subject (such as `/books/42`) does not yet have any events, import the `IsSubjectPristine` class and pass it as the second argument as a list of preconditions:

```python
from eventsourcingdb import IsSubjectPristine

written_events = await client.write_events(
  events = [
    # events
  ],
  preconditions = [
    IsSubjectPristine('/books/42')
  ],
)
```

#### Using the `isSubjectOnEventId` precondition

If you only want to write events in case the last event of a subject (such as `/books/42`) has a specific ID (e.g., `0`), import the `IsSubjectOnEventId` class and pass it as a list of preconditions in the second argument:

```python
from eventsourcingdb import IsSubjectOnEventId

written_events = await client.write_events(
  events = [
    # events
  ],
  preconditions = [
    IsSubjectOnEventId('/books/42', '0')
  ],
)
```

*Note that according to the CloudEvents standard, event IDs must be of type string.*

### Reading Events

To read all events of a subject, call the `read_events` function with the subject as the first argument and an options object as the second argument. Set the `recursive` option to `False`. This ensures that only events of the given subject are returned, not events of nested subjects.

The function returns an asynchronous generator, which you can use e.g. inside an `async for` loop:

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

#### Reading From Subjects Recursively

If you want to read not only all the events of a subject, but also the events of all nested subjects, set the `recursive` option to `True`:

```python
from eventsourcingdb import ReadEventsOptions

async for event in client.read_events(
  subject = '/books/42',
  options = ReadEventsOptions(
    recursive = True
  ),
):
  pass
```

This also allows you to read *all* events ever written. To do so, provide `/` as the subject and set `recursive` to `True`, since all subjects are nested under the root subject.

#### Reading in Anti-Chronological Order

By default, events are read in chronological order. To read in anti-chronological order, provide the `order` option and set it to `Order.ANTICHRONOLOGICAL`:

```python
from eventsourcingdb import (
  Order,
  ReadEventsOptions,
)

async for event in client.read_events(
  subject = '/books/42',
  options = ReadEventsOptions(
    recursive = False,
    order = Order.ANTICHRONOLOGICAL,
  ),
):
  pass
```

*Note that you can also specify `Order.CHRONOLOGICAL` to explicitly enforce the default order.*

#### Specifying Bounds

Sometimes you do not want to read all events, but only a range of events. For that, you can specify the `lower_bound` and `upper_bound` options – either one of them or even both at the same time.

Specify the ID and whether to include or exclude it, for both the lower and upper bound:

```python
from eventsourcingdb import (
  Bound,
  BoundType,
  ReadEventsOptions,
)

async for event in client.read_events(
  subject = '/books/42',
  options = ReadEventsOptions(
    recursive = False,
    lower_bound = Bound(id = '100', type = BoundType.INCLUSIVE),
    upper_bound = Bound(id = '200', type = BoundType.EXCLUSIVE),
  ),
):
  pass
```

#### Starting From the Latest Event of a Given Type

To read starting from the latest event of a given type, provide the `from_latest_event` option and specify the subject, the type, and how to proceed if no such event exists.

Possible options are `IfEventIsMissingDuringRead.READ_NOTHING`, which skips reading entirely, or `IfEventIsMissingDuringRead.READ_EVERYTHING`, which effectively behaves as if `from_latest_event` was not specified:

```python
from eventsourcingdb import (
  IfEventIsMissingDuringRead,
  ReadEventsOptions,
  ReadFromLatestEvent,
)

async for event in client.read_events(
  subject = '/books/42',
  options = ReadEventsOptions(
    recursive = False,
    from_latest_event = ReadFromLatestEvent(
      subject = '/books/42',
      type = 'io.eventsourcingdb.library.book-borrowed',
      if_event_is_missing = IfEventIsMissingDuringRead.READ_EVERYTHING,
    ),
  ),
):
  pass
```

*Note that `from_latest_event` and `lower_bound` can not be provided at the same time.*

#### Aborting Reading

If you need to abort reading use `break` or `return` within the `async for` loop. However, this only works if there is currently an iteration going on.

To abort reading independently of that, store the generator in a variable, and close it explicitly:

```python
from eventsourcingdb import ReadEventsOptions

events = client.read_events(
  subject = '/books/42',
  options = ReadEventsOptions(
    recursive = False,
  ),
)

async for event in events:
  pass

# Somewhere else, abort the generator, which will cause
# reading to end.
await events.aclose()
```

### Running EventQL Queries

To run an EventQL query, call the `run_eventql_query` function and provide the query as argument. The function returns an asynchronous generator, which you can use e.g. inside an `async for` loop:

```python
async for row in client.run_eventql_query(
  query = '''
    FROM e IN events
    PROJECT INTO e
  ''',
):
  pass
```

*Note that each row returned by the generator matches the projection specified in your query.*

#### Aborting a Query

If you need to abort a query use `break` or `return` within the `async for` loop. However, this only works if there is currently an iteration going on.

To abort the query independently of that, store the generator in a variable, and close it explicitly:

```python
rows = client.run_eventql_query(
  query = '''
    FROM e IN events
    PROJECT INTO e
  ''',
)

async for row in rows:
  pass

# Somewhere else, abort the generator, which will cause
# the query to end.
await rows.aclose()
```

### Observing Events

To observe all events of a subject, call the `observe_events` function with the subject as the first argument and an options object as the second argument. Set the `recursive` option to `False`. This ensures that only events of the given subject are returned, not events of nested subjects.

The function returns an asynchronous generator, which you can use e.g. inside an `async for` loop:

```python
from eventsourcingdb import ObserveEventsOptions

async for event in client.observe_events(
  subject = '/books/42',
  options = ObserveEventsOptions(
    recursive = False
  ),
):
  pass
```

#### Observing From Subjects Recursively

If you want to observe not only all the events of a subject, but also the events of all nested subjects, set the `recursive` option to `True`:

```python
from eventsourcingdb import ObserveEventsOptions

async for event in client.observe_events(
  subject = '/books/42',
  options = ObserveEventsOptions(
    recursive = True
  ),
):
  pass
```

This also allows you to observe *all* events ever written. To do so, provide `/` as the subject and set `recursive` to `True`, since all subjects are nested under the root subject.

#### Specifying Bounds

Sometimes you do not want to observe all events, but only a range of events. For that, you can specify the `lower_bound` option.

Specify the ID and whether to include or exclude it:

```python
from eventsourcingdb import (
  Bound,
  BoundType,
  ObserveEventsOptions,
)

async for event in client.observe_events(
  subject = '/books/42',
  options = ObserveEventsOptions(
    recursive = False,
    lower_bound = Bound(id = '100', type = BoundType.INCLUSIVE),
  ),
):
  pass
```

#### Starting From the Latest Event of a Given Type

To observe starting from the latest event of a given type, provide the `from_latest_event` option and specify the subject, the type, and how to proceed if no such event exists.

Possible options are `IfEventIsMissingDuringObserve.WAIT_FOR_EVENT`, which waits for an event of the given type to happen, or `IfEventIsMissingDuringObserve.READ_EVERYTHING`, which effectively behaves as if `from_latest_event` was not specified:

```python
from eventsourcingdb import (
  IfEventIsMissingDuringObserve,
  ObserveEventsOptions,
  ObserveFromLatestEvent,
)

async for event in client.observe_events(
  subject = '/books/42',
  options = ObserveEventsOptions(
    recursive = False,
    from_latest_event = ObserveFromLatestEvent(
      subject = '/books/42',
      type = 'io.eventsourcingdb.library.book-borrowed',
      if_event_is_missing = IfEventIsMissingDuringObserve.READ_EVERYTHING,
    ),
  ),
):
  pass
```

*Note that `from_latest_event` and `lower_bound` can not be provided at the same time.*

#### Aborting Observing

If you need to abort observing use `break` or `return` within the `async for` loop. However, this only works if there is currently an iteration going on.

To abort observing independently of that, store the generator in a variable, and close it explicitly:

```python
from eventsourcingdb import ObserveEventsOptions

events = client.observe_events(
  subject = '/books/42',
  options = ObserveEventsOptions(
    recursive = False
  ),
)

async for event in events:
  pass

# Somewhere else, abort the generator, which will cause
# observing to end.
await events.aclose()
```

### Registering an Event Schema

To register an event schema, call the `register_event_schema` function and hand over an event type and the desired schema:

```python
await client.register_event_schema(
  event_type = 'io.eventsourcingdb.library.book-acquired',
  json_schema = {
    'type': 'object',
    'properties': {
      'title': { 'type': 'string' },
      'author': { 'type': 'string' },
      'isbn': { 'type': 'string' },
    },
    'required': [
      'title',
      'author',
      'isbn'
    ],
    'additionalProperties': False,
  },
)
```

### Listing Subjects

To list all subjects, call the `read_subjects` function with `/` as the base subject. The function returns an asynchronous generator, which you can use e.g. inside an `async for` loop:

```python
async for subject in client.read_subjects(
  base_subject = '/'
):
  pass
```

If you only want to list subjects within a specific branch, provide the desired base subject instead:

```python
async for subject in client.read_subjects(
  base_subject = '/books'
):
  pass
```

#### Aborting Listing

If you need to abort listing use `break` or `return` within the `async for` loop. However, this only works if there is currently an iteration going on.

To abort listing independently of that, store the generator in a variable, and close it explicitly:

```python
subjects = client.read_subjects(
  base_subject = '/'
)

async for subject in subjects:
  pass

# Somewhere else, abort the generator, which will cause
# reading to end.
await subjects.aclose()
```

### Listing Event Types

To list all event types, call the `read_event_types` function. The function returns an asynchronous generator, which you can use e.g. inside an `async for` loop:

```python
async for event_type in client.read_event_types():
  pass
```

#### Aborting Listing

If you need to abort listing use `break` or `return` within the `async for` loop. However, this only works if there is currently an iteration going on.

To abort listing independently of that, store the generator in a variable, and close it explicitly:

```python
event_types = client.read_event_types()

async for event_type in event_types:
  pass

# Somewhere else, abort the generator, which will cause
# reading to end.
await event_types.aclose()
```

### Using Testcontainers

Import the `Container` class, create an instance, call the `start` function to run a test container, get a client, run your test code, and finally call the `stop` function to stop the test container:

```python
from eventsourcingdb import Container

container = Container()
container.start()

client = container.get_client()

# ...

container.stop()
```

To check if the test container is running, call the `is_running` function:

```python
is_running = container.is_running()
```

#### Configuring the Container Instance

By default, `Container` uses the `latest` tag of the official EventSourcingDB Docker image. To change that, call the `with_image_tag` function:

```python
container = (
  Container()
    .with_image_tag('1.0.0')
)
```

Similarly, you can configure the port to use and the API token. Call the `with_port` or the `with_api_token` function respectively:

```python
container = (
  Container()
    .with_port(4000)
    .with_api_token('secret')
)
```

#### Configuring the Client Manually

In case you need to set up the client yourself, use the following functions to get details on the container:

- `get_host()` returns the host name
- `get_mapped_port()` returns the port
- `get_base_url()` returns the full URL of the container
- `get_api_token()` returns the API token
