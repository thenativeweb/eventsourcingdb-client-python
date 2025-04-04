from enum import Enum


class IfEventIsMissingDuringRead(str, Enum):
    READ_NOTHING = 'read-nothing'
    READ_EVERYTHING = 'read-everything'
