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

### Talking to Servers With and Without the v2 API

The client SDK works with servers that offer the v2 API of EventSourcingDB, which it has since version 1.3, as well as with servers that only offer the v1 API. Creating a client does not send any request. Instead, on its first request, the client asks the server whether it offers the v2 API, and remembers the answer for as long as it exists. If the server answers a path of the v2 API with 404 or 405, for example after it was rolled back to a version without it, the client asks again on the next request. If the server cannot be asked, for example because it is not reachable, the first request fails with that error, and the next request asks again.

With the v2 API, every function that reads, such as `read_events`, `observe_events`, `run_eventql_query`, `read_subjects`, `read_event_type`, and `read_event_types`, uses the HTTP method `QUERY` ([RFC 10008](https://www.rfc-editor.org/rfc/rfc10008)). If there is a proxy, a load balancer, or a firewall in front of EventSourcingDB, it has to let requests with this method through. The client does not fall back to `POST`.

### Configuring the Stall Timeout

A request fails once nothing at all has arrived from the server for 30 seconds, measured from sending the request until its end, including connecting and waiting for the response. Everything that arrives, such as a part of a response, an event, a row, or a heartbeat, restarts the clock, so a long-running request that keeps receiving data is never cut off. The time your code spends between two items of a stream does not count. To change the limit, pass the `stall_timeout` keyword argument in seconds when creating the client:

```python
client = Client(
  base_url = url,
  api_token = api_token,
  stall_timeout = 10,
)
```

The stall timeout cannot be turned off: it must be a finite number of seconds greater than zero, otherwise creating the client raises a `ValueError`.

Once the server stalls, every request raises a `ConnectionStalledError`, which is a subclass of `ServerError`, whether it stalls while connecting, while sending the request, while waiting for the response, or in the middle of a stream. Its `stall_timeout` attribute holds the stall timeout in seconds. If writing events or registering an event schema stalls once the request has a connection, the server may have stored the write, so the `ConnectionStalledError` is the cause of an `OutcomeUnknownError` instead, see [Knowing Whether a Write Was Stored](#knowing-whether-a-write-was-stored). For details on streams, see [Detecting a Stalled Connection](#detecting-a-stalled-connection).

The stall timeout also covers the time a request waits for a free connection: a client keeps at most 100 connections open at the same time, so with as many streams open, a further request waits until one of them ends. If it waits for longer than the stall timeout, it raises a `ConnectionStalledError` as well.

In any case, the client closes the connection. Your own timeouts and cancellations, such as `asyncio.timeout`, still apply and can end a request earlier. For a write that you end this way once it has a connection, `is_outcome_unknown` tells that it may have been stored, see [Knowing Whether a Write Was Stored](#knowing-whether-a-write-was-stored).

### Handling Errors

Every error that the server reports raises a `DbApiError`, which is a subclass of `ServerError`, or, for a write that the server may have stored nonetheless, becomes the cause of an `OutcomeUnknownError`, see [Knowing Whether a Write Was Stored](#knowing-whether-a-write-was-stored). A `DbApiError` has the following attributes:

- `code` is the URL of the page in the documentation that explains the error, exactly as the server sends it, such as `https://docs.eventsourcingdb.io/errors/precondition-violated`, or `None` if the error has no code.
- `description` describes the error.
- `details` is a dict that locates the error, such as the index of the precondition that does not hold, and is empty if there is nothing to locate.
- `status` is the HTTP status of the answer, which is `200` for an error that the server reports within an answer that it began successfully.
- `retry_after` is the number of seconds to wait before trying again, which the server only tells when it refuses a request because it received too many (with status `429`). Otherwise, it is `None`. The client never retries a request on its own.

To tell errors apart, compare the `code` with the constants of `ErrorCode`, which has one for every code the server knows. Since the constants are strings, they compare equal to the code as the server sends it:

```python
from eventsourcingdb import DbApiError, ErrorCode, IsSubjectPristine

try:
  written_events = await client.write_events(
    event_candidates = [
      # event candidates
    ],
    preconditions = [
      IsSubjectPristine('/books/42')
    ],
  )
except DbApiError as error:
  if error.code != ErrorCode.PRECONDITION_VIOLATED:
    raise
  # The subject already has events.
```

Servers without the v2 API report errors without a code. For them, the client assigns the code of the v2 API to the errors that clearly match one: a precondition that does not hold, an exceeded capacity of the store, an event that does not match the schema of its type, a schema that is already registered, a schema that existing events do not match, a range of events that cannot be read because `from_latest_event` lies above the `upper_bound`, an unknown event type, a store in read-only mode, and an invalid license. Every other error of such a server has no code.

#### Knowing Whether a Write Was Stored

EventSourcingDB never stores a write halfway: the events of a call to `write_events`, or the schema of a call to `register_event_schema`, are either stored completely or not at all. If one of these functions fails in a way that leaves open whether the server stored the write, it raises an `OutcomeUnknownError`, whose `cause` attribute holds the error that the write failed with. This happens, for example, if the server stalls or the connection breaks once the request has a connection, if the server answers with a status such as `500`, `502`, or `504`, if the answer does not come from EventSourcingDB, or if the server ends its answer before it is complete. Before you repeat such a write, find out whether it was stored, for example by reading the events of the subject, or repeat it with a precondition such as `IsSubjectOnEventId` that only holds if it was not stored.

The function raises the error itself, which tells that the write was certainly not stored, only if the request could not get a connection at all, such as when the name of the server cannot be resolved, connecting or TLS fails, or the request waits for a free connection for longer than the stall timeout, or if the server refused the write: with an error that it reports within its answer, other than `ErrorCode.STORE_FAILED`, with one of the statuses `400`, `401`, `408`, `413`, `429`, and `503`, or, for servers without the v2 API, with any status `4xx`, `503`, or `507`.

Cancelling a write once it has a connection, for example with `asyncio.timeout` or by cancelling its task, leaves its outcome open as well. It is cancelled as usual nonetheless, so that `asyncio.timeout`, `asyncio.wait_for`, and task groups work as always: the `asyncio.CancelledError` is not wrapped, but marked, and carries a note that says so. To tell whether the outcome of a write is unknown, call `is_outcome_unknown` with the error. It returns `True` for an `OutcomeUnknownError`, for a marked `CancelledError`, and for an error caused by one of them, such as the `TimeoutError` of `asyncio.timeout`:

```python
import asyncio

from eventsourcingdb import is_outcome_unknown

try:
  async with asyncio.timeout(5):
    written_events = await client.write_events(
      event_candidates = [
        # event candidates
      ],
    )
except TimeoutError as error:
  if is_outcome_unknown(error):
    # The events may have been stored.
    pass
```

A write that you cancel before it has a connection is not marked, and `is_outcome_unknown` returns `False` for it.

There are two cases that `is_outcome_unknown` cannot see: a timeout around a task group of writes that have a connection re-raises the cancellation of the task that awaits the group, which is not marked, and an `ExceptionGroup` that holds an `OutcomeUnknownError` needs `except*` or a check of its members.

```python
from eventsourcingdb import OutcomeUnknownError

try:
  written_events = await client.write_events(
    event_candidates = [
      # event candidates
    ],
  )
except OutcomeUnknownError as error:
  # The events may have been stored. error.cause tells why the outcome is unknown.
  pass
```

`OutcomeUnknownError` is a subclass of `CustomError`, the base class of every error of the client SDK, but not of `ServerError`.

### Writing Events

Call the `write_events` function and hand over a list with one or more event candidates. You do not have to provide all event fields – some are automatically added by the server.

Specify `source`, `subject`, `type`, and `data` according to the [CloudEvents](https://docs.eventsourcingdb.io/fundamentals/cloud-events/) format. Optionally, specify `trace_parent` and `trace_state`.

The function returns the written events, including the fields added by the server:

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

#### Using the `isSubjectPristine` precondition

If you only want to write events in case a subject (such as `/books/42`) does not yet have any events, import the `IsSubjectPristine` class and pass it as the second argument as a list of preconditions:

```python
from eventsourcingdb import IsSubjectPristine

written_events = await client.write_events(
  event_candidates = [
    # event candidates
  ],
  preconditions = [
    IsSubjectPristine('/books/42')
  ],
)
```

#### Using the `isSubjectPopulated` precondition

If you only want to write events in case a subject (such as `/books/42`) already has at least one event, import the `IsSubjectPopulated` class and pass it as the second argument as a list of preconditions:

```python
from eventsourcingdb import IsSubjectPopulated

written_events = await client.write_events(
  event_candidates = [
    # event candidates
  ],
  preconditions = [
    IsSubjectPopulated('/books/42')
  ],
)
```

#### Using the `isSubjectOnEventId` precondition

If you only want to write events in case the last event of a subject (such as `/books/42`) has a specific ID (e.g., `0`), import the `IsSubjectOnEventId` class and pass it as a list of preconditions in the second argument:

```python
from eventsourcingdb import IsSubjectOnEventId

written_events = await client.write_events(
  event_candidates = [
    # event candidates
  ],
  preconditions = [
    IsSubjectOnEventId('/books/42', '0')
  ],
)
```

*Note that according to the CloudEvents standard, event IDs must be of type string.*

#### Using the `isEventQlQueryTrue` precondition

If you want to write events depending on an EventQL query, import the `IsEventQlQueryTrue` class and pass it as a list of preconditions in the second argument:

```python
from eventsourcingdb import IsEventQlQueryTrue

written_events = await client.write_events(
  event_candidates = [
    # event candidates
  ],
  preconditions = [
    IsEventQlQueryTrue('FROM e IN events WHERE e.type == "io.eventsourcingdb.library.book-borrowed" PROJECT INTO COUNT() < 10')
  ],
)
```

*Note that the query must return a single row with a single value, which is interpreted as a boolean.*

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

While the query runs, the server sends a heartbeat every second whenever there is no row to send. If neither a row nor a heartbeat arrives for the [stall timeout](#configuring-the-stall-timeout), 30 seconds by default, the generator closes the connection and raises a `ConnectionStalledError`, which is a subclass of `ServerError`. For details, see [Detecting a Stalled Connection](#detecting-a-stalled-connection).

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

### Converting Events to pandas DataFrame

For data analysis and exploration, you can convert event streams to pandas DataFrames. To use this feature, install the client SDK with pandas support:

```shell
pip install eventsourcingdb[pandas]
```

Import the `events_to_dataframe` function from the `eventsourcingdb.pandas` module and pass an event stream to it:

```python
from eventsourcingdb import Client, ReadEventsOptions
from eventsourcingdb.pandas import events_to_dataframe

events = client.read_events(
  subject = '/books',
  options = ReadEventsOptions(
    recursive = True
  ),
)

df = await events_to_dataframe(events)
```

The resulting DataFrame includes all event fields as columns: `event_id`, `time`, `source`, `subject`, `type`, `data`, `spec_version`, `data_content_type`, `predecessor_hash`, `hash`, `trace_parent`, `trace_state`, and `signature`.

The `data` field remains as a dict column, which you can access directly:

```python
# Access the data field
for index, row in df.iterrows():
  print(row['data'])
```

#### Flattening the Data Field

For analysis of specific event types, you may want to flatten the `data` field into separate columns. Use pandas' `json_normalize` function:

```python
import pandas as pd

# Filter for a specific event type first
book_acquired_df = df[df['type'] == 'io.eventsourcingdb.library.book-acquired']

# Flatten the data field
flattened_df = book_acquired_df.join(
  pd.json_normalize(book_acquired_df['data'])
)

# Now you can access data fields as columns
print(flattened_df['title'])
print(flattened_df['author'])
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

#### Detecting a Stalled Connection

While observing, the server sends a heartbeat every second whenever there is no new event. If neither an event nor a heartbeat arrives for the [stall timeout](#configuring-the-stall-timeout), 30 seconds by default, for example because a proxy keeps the connection open but no longer passes anything on, the generator closes the connection and raises a `ConnectionStalledError`. Since `ConnectionStalledError` is a subclass of `ServerError`, you can handle it specifically or together with other server errors:

```python
from eventsourcingdb import ConnectionStalledError, ObserveEventsOptions

try:
  async for event in client.observe_events(
    subject = '/books/42',
    options = ObserveEventsOptions(
      recursive = False
    ),
  ):
    pass
except ConnectionStalledError:
  # Neither an event nor a heartbeat arrived for the stall timeout.
  pass
```

#### Aborting Observing

Observing has no time limit of its own and runs until you abort it. Since it never ends on its own, the generator raises a `ServerError` if the server closes the stream without reporting an error, which it only does after an unexpected failure. A server that shuts down gracefully reports that as a `DbApiError` first.

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

To list subjects, call the `read_subjects` function with a subject as the first argument and an options object as the second argument. The `recursive` option is required: set it to `True` to list the subject together with all its nested subjects, or to `False` to list the subject alone, if it exists. If the options or the `recursive` option are missing, the function raises an error right away.

To list all subjects, provide `/` as the subject and set `recursive` to `True`. The function returns an asynchronous generator, which you can use e.g. inside an `async for` loop:

```python
from eventsourcingdb import ReadSubjectsOptions

async for subject in client.read_subjects(
  subject = '/',
  options = ReadSubjectsOptions(
    recursive = True
  ),
):
  pass
```

If you only want to list subjects within a specific branch, provide the desired subject instead:

```python
from eventsourcingdb import ReadSubjectsOptions

async for subject in client.read_subjects(
  subject = '/books',
  options = ReadSubjectsOptions(
    recursive = True
  ),
):
  pass
```

#### Aborting Listing

If you need to abort listing use `break` or `return` within the `async for` loop. However, this only works if there is currently an iteration going on.

To abort listing independently of that, store the generator in a variable, and close it explicitly:

```python
from eventsourcingdb import ReadSubjectsOptions

subjects = client.read_subjects(
  subject = '/',
  options = ReadSubjectsOptions(
    recursive = True
  ),
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

Each event type is an `EventType` with the name of the type in `type`, whether events of this type exist in `has_events`, and the registered schema in `schema`, which is `None` if no schema is registered. An event type that has a schema but no events yet has `has_events` set to `False`.

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

### Listing a Specific Event Type

To list a specific event type, call the `read_event_type` function with the event type as an argument. The function returns the detailed event type as an `EventType`, with the same fields as above:

```python
event_type = await client.read_event_type("io.eventsourcingdb.library.book-acquired")
```

### Verifying an Event's Hash

To verify the integrity of an event, call the `verify_hash` function on the event instance. This recomputes the event's hash locally and compares it to the hash stored in the event. If the hashes differ, the function raises a `HashVerificationFailedError`:

```python
event.verify_hash()
```

The hash of an event has a version. EventSourcingDB writes hashes of version 2, which start with `esdb:hash:v2:`, since version 1.3, while events written before keep their hashes of version 1, which have no prefix. The `verify_hash` function supports both versions and computes the hash over the event's data exactly as the server sent it. If the hash is of a version the client SDK does not support, the function raises an `UnsupportedHashVersionError`, whose `version` attribute names the version.

*Note that this only verifies the hash. If you also want to verify the signature, you can skip this step and call `verify_signature` directly, which performs a hash verification internally.*

### Verifying an Event's Signature

To verify the authenticity of an event, call the `verify_signature` function on the event instance. This requires the public key that matches the private key used for signing on the server.

The function first verifies the event's hash, and then checks the signature. If any verification step fails, it raises an error:

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# ...

verification_key = # public key as Ed25519PublicKey

event.verify_signature(verification_key)
```

If the hash verification fails, the function raises the same errors as `verify_hash`. If the signature does not match the verification key, or if it is malformed, the function raises a `SignatureVerificationFailedError`. If the event has no signature at all, for example because the server was started without a signing key, the function raises a `ValidationError`.

`HashVerificationFailedError`, `UnsupportedHashVersionError`, and `SignatureVerificationFailedError` are subclasses of `ValidationError`, so you can handle them specifically or together with other validation errors.

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

If you want to sign events, call the `with_signing_key` function. This generates a new signing and verification key pair inside the container:

```python
container = (
  Container()
    .with_signing_key()
)
```

You can retrieve the private key (for signing) and the public key (for verifying signatures) once the container has been started:

```python
signing_key = container.get_signing_key()
verification_key = container.get_verification_key()
```

The `signing_key` is the private key EventSourcingDB signs events with. The `verification_key` can be passed to `verify_signature` when verifying events read from the database.

By default, `start` waits up to 30 seconds for the database to become reachable, measured from creating the container, not counting the time it takes to pull the image. To change that, call the `with_startup_timeout` function with a number of seconds:

```python
container = (
  Container()
    .with_startup_timeout(60)
)
```

If a container is running but does not become reachable in time, `start` replaces it with a new one, and raises a `TimeoutError` once three containers have failed. If the container exits before it becomes reachable, or if Docker fails, for example because the image cannot be pulled, `start` raises a `RuntimeError` at once. Either way, `start` removes every container whose start failed.

#### Configuring the Client Manually

In case you need to set up the client yourself, use the following functions to get details on the container:

- `get_host()` returns the host name
- `get_mapped_port()` returns the port
- `get_base_url()` returns the full URL of the container
- `get_api_token()` returns the API token

## Upgrading From Version 1

Version 2 of the client SDK speaks the v2 API of EventSourcingDB, and keeps speaking the v1 API to servers without it, see [Talking to Servers With and Without the v2 API](#talking-to-servers-with-and-without-the-v2-api). If there is a proxy in front of EventSourcingDB, make sure it lets requests with the HTTP method `QUERY` through. Besides, it changes the following:

- **Event types:** an `EventType` names its type `type` instead of `event_type`, and tells whether events of the type exist with `has_events`, the opposite of the former `is_phantom`.
  - Before: `event_type.event_type`, `event_type.is_phantom`, `EventType(event_type = '…', is_phantom = True)`
  - After: `event_type.type`, `not event_type.has_events`, `EventType(type = '…', has_events = False)`
  - Positional arguments keep their places but change their meaning without an error: `EventType('…', True)` used to create an event type without events, and now creates one with events. Pass them by name, or negate the second one.
- **Reading subjects:** `read_subjects` takes a subject and `ReadSubjectsOptions` with a `recursive` option that is required. To keep the previous behavior, set it to `True`.
  - Before: `client.read_subjects(base_subject = '/books')`
  - After: `client.read_subjects(subject = '/books', options = ReadSubjectsOptions(recursive = True))`
- **Errors that the server reports:** they raise a `DbApiError`, which is a subclass of `ServerError`, so `except ServerError` still catches them. Its message is the text of the server rather than one of the client SDK, such as `Failed to verify API token`, so tell errors apart by their code, see [Handling Errors](#handling-errors).
  - Before: `except ServerError as error:` and `if 'state conflict' in str(error):`
  - After: `except DbApiError as error:` and `if error.code == ErrorCode.PRECONDITION_VIOLATED:`
- **Stalled connections:** every request that stalls raises a `ConnectionStalledError`. `HeartbeatTimeoutError` no longer exists, and a stall no longer raises aiohttp's `ConnectionTimeoutError` while connecting, which `read_event_types` wrapped in an `InternalError`, or a `TimeoutError` for requests that are not streams.
  - Before: `except HeartbeatTimeoutError:`, `except aiohttp.ConnectionTimeoutError:`, `except TimeoutError:`
  - After: `except ConnectionStalledError:`
- **Writes whose outcome is unknown:** `write_events` and `register_event_schema` raise an `OutcomeUnknownError` whose `cause` is the error they failed with, whenever the server may have stored the write, see [Knowing Whether a Write Was Stored](#knowing-whether-a-write-was-stored). A write that you cancel, or that `asyncio.timeout` ends, is cancelled as before, and `is_outcome_unknown` tells whether it may have been stored.
  - Before: `except ServerError:` for a status such as `500`, `except aiohttp.ClientError:` for a broken connection
  - After: `except OutcomeUnknownError as error:`, with the former error in `error.cause`
- **Observing events:** if the server closes the stream without reporting an error, `observe_events` raises a `ServerError` instead of ending quietly.
  - Before: `async for event in client.observe_events(…):` ends
  - After: it raises a `ServerError`
- **Internals:** the helpers `eventsourcingdb.is_event`, `eventsourcingdb.is_heartbeat`, `eventsourcingdb.is_stream_error`, `eventsourcingdb.read_event_types.is_event_type`, and `eventsourcingdb.read_subjects.is_subject` moved into the transport of the v1 API. `HttpClient.post` no longer takes `is_stream`, and `Response.read_lines` no longer takes the error to raise on a stall.
