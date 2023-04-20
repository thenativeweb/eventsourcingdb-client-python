from enum import Enum


class IfEventIsMissing(str, Enum):
    READ_NOTHING = 'read-nothing'
    READ_EVERYTHING = 'read-everything'
