from enum import StrEnum


class ErrorCode(StrEnum):
    """
    The codes of the errors that EventSourcingDB reports, as the code of a
    DbApiError holds them. A code is the URL of the page in the documentation
    that explains the error, and each constant is named after the last part
    of it. Since a member is a string, it compares equal to the code as the
    server sends it.
    """

    SUBJECT_MISSING = "https://docs.eventsourcingdb.io/errors/subject-missing"
    SUBJECT_MALFORMED = "https://docs.eventsourcingdb.io/errors/subject-malformed"
    ORDER_UNKNOWN = "https://docs.eventsourcingdb.io/errors/order-unknown"
    EVENT_ID_MISSING = "https://docs.eventsourcingdb.io/errors/event-id-missing"
    EVENT_ID_MALFORMED = "https://docs.eventsourcingdb.io/errors/event-id-malformed"
    BOUND_TYPE_MISSING = "https://docs.eventsourcingdb.io/errors/bound-type-missing"
    BOUND_TYPE_UNKNOWN = "https://docs.eventsourcingdb.io/errors/bound-type-unknown"
    RANGE_UNSATISFIABLE = "https://docs.eventsourcingdb.io/errors/range-unsatisfiable"
    FROM_LATEST_EVENT_INCOMPLETE = (
        "https://docs.eventsourcingdb.io/errors/from-latest-event-incomplete"
    )
    IF_EVENT_IS_MISSING_UNKNOWN = (
        "https://docs.eventsourcingdb.io/errors/if-event-is-missing-unknown"
    )
    SELECTION_CONFLICTING = "https://docs.eventsourcingdb.io/errors/selection-conflicting"
    EVENT_TYPE_MISSING = "https://docs.eventsourcingdb.io/errors/event-type-missing"
    EVENT_TYPE_MALFORMED = "https://docs.eventsourcingdb.io/errors/event-type-malformed"
    EVENT_TYPE_UNKNOWN = "https://docs.eventsourcingdb.io/errors/event-type-unknown"
    SOURCE_MISSING = "https://docs.eventsourcingdb.io/errors/source-missing"
    SOURCE_MALFORMED = "https://docs.eventsourcingdb.io/errors/source-malformed"
    DATA_MISSING = "https://docs.eventsourcingdb.io/errors/data-missing"
    TRACEPARENT_MALFORMED = "https://docs.eventsourcingdb.io/errors/traceparent-malformed"
    TRACESTATE_MALFORMED = "https://docs.eventsourcingdb.io/errors/tracestate-malformed"
    TRACESTATE_WITHOUT_TRACEPARENT = (
        "https://docs.eventsourcingdb.io/errors/tracestate-without-traceparent"
    )
    EVENTS_MISSING = "https://docs.eventsourcingdb.io/errors/events-missing"
    PRECONDITION_TYPE_MISSING = "https://docs.eventsourcingdb.io/errors/precondition-type-missing"
    PRECONDITION_UNKNOWN = "https://docs.eventsourcingdb.io/errors/precondition-unknown"
    PAYLOAD_MISSING = "https://docs.eventsourcingdb.io/errors/payload-missing"
    LICENSE_INVALID = "https://docs.eventsourcingdb.io/errors/license-invalid"
    CAPACITY_EXCEEDED = "https://docs.eventsourcingdb.io/errors/capacity-exceeded"
    EVENT_SCHEMA_VIOLATED = "https://docs.eventsourcingdb.io/errors/event-schema-violated"
    EVENT_SCHEMA_UNREGISTERED = "https://docs.eventsourcingdb.io/errors/event-schema-unregistered"
    EVENT_SCHEMA_MISSING = "https://docs.eventsourcingdb.io/errors/event-schema-missing"
    EVENT_SCHEMA_MALFORMED = "https://docs.eventsourcingdb.io/errors/event-schema-malformed"
    EVENT_SCHEMA_NOT_OBJECT = "https://docs.eventsourcingdb.io/errors/event-schema-not-object"
    EVENT_SCHEMA_ALREADY_REGISTERED = (
        "https://docs.eventsourcingdb.io/errors/event-schema-already-registered"
    )
    LAST_AUDITED_EVENT_MISSING = (
        "https://docs.eventsourcingdb.io/errors/last-audited-event-missing"
    )
    LAST_AUDITED_EVENT_MISMATCHED = (
        "https://docs.eventsourcingdb.io/errors/last-audited-event-mismatched"
    )
    LAST_AUDITED_EVENT_UNKNOWN = (
        "https://docs.eventsourcingdb.io/errors/last-audited-event-unknown"
    )
    EVENT_HASH_MISSING = "https://docs.eventsourcingdb.io/errors/event-hash-missing"
    EVENT_HASH_MALFORMED = "https://docs.eventsourcingdb.io/errors/event-hash-malformed"
    EVENT_CHAIN_BROKEN = "https://docs.eventsourcingdb.io/errors/event-chain-broken"
    LAST_BACKED_UP_EVENT_MISSING = (
        "https://docs.eventsourcingdb.io/errors/last-backed-up-event-missing"
    )
    LAST_BACKED_UP_EVENT_MISMATCHED = (
        "https://docs.eventsourcingdb.io/errors/last-backed-up-event-mismatched"
    )
    LAST_BACKED_UP_EVENT_UNKNOWN = (
        "https://docs.eventsourcingdb.io/errors/last-backed-up-event-unknown"
    )
    STORE_NOT_EMPTY = "https://docs.eventsourcingdb.io/errors/store-not-empty"
    EVENT_HASH_VERSION_UNKNOWN = (
        "https://docs.eventsourcingdb.io/errors/event-hash-version-unknown"
    )
    BACKUP_MALFORMED = "https://docs.eventsourcingdb.io/errors/backup-malformed"
    BACKUP_INCOMPLETE = "https://docs.eventsourcingdb.io/errors/backup-incomplete"
    BACKUP_FORMAT_UNKNOWN = "https://docs.eventsourcingdb.io/errors/backup-format-unknown"
    FULL_BACKUP_MISSING = "https://docs.eventsourcingdb.io/errors/full-backup-missing"
    BACKUP_INCREMENT_DISCONNECTED = (
        "https://docs.eventsourcingdb.io/errors/backup-increment-disconnected"
    )
    BACKUP_FAILED = "https://docs.eventsourcingdb.io/errors/backup-failed"
    BACKUP_UNREADABLE = "https://docs.eventsourcingdb.io/errors/backup-unreadable"
    EVENT_TOO_LARGE = "https://docs.eventsourcingdb.io/errors/event-too-large"
    DATA_MALFORMED = "https://docs.eventsourcingdb.io/errors/data-malformed"
    QUERY_MISSING = "https://docs.eventsourcingdb.io/errors/query-missing"
    QUERY_MALFORMED = "https://docs.eventsourcingdb.io/errors/query-malformed"
    QUERY_UNEVALUABLE = "https://docs.eventsourcingdb.io/errors/query-unevaluable"
    QUERY_NOT_BOOLEAN = "https://docs.eventsourcingdb.io/errors/query-not-boolean"
    PRECONDITION_VIOLATED = "https://docs.eventsourcingdb.io/errors/precondition-violated"
    STORE_READ_ONLY = "https://docs.eventsourcingdb.io/errors/store-read-only"
    READ_ONLY_MODE_ALREADY_ENABLED = (
        "https://docs.eventsourcingdb.io/errors/read-only-mode-already-enabled"
    )
    DISK_FULL = "https://docs.eventsourcingdb.io/errors/disk-full"
    RESTORE_IN_PROGRESS = "https://docs.eventsourcingdb.io/errors/restore-in-progress"
    STORE_FAILED = "https://docs.eventsourcingdb.io/errors/store-failed"
    INDEXES_REBUILDING = "https://docs.eventsourcingdb.io/errors/indexes-rebuilding"
    SERVER_SHUTTING_DOWN = "https://docs.eventsourcingdb.io/errors/server-shutting-down"
