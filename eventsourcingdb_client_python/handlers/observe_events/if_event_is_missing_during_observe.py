from enum import Enum


class IfEventIsMissingDuringObserve(str, Enum):
    WAIT_FOR_EVENT = 'wait-for-event'
    READ_EVERYTHING = 'read-everything'
