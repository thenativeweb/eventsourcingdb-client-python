import os

IMAGE_TAG_VARIABLE = 'EVENTSOURCINGDB_IMAGE_TAG'
DEFAULT_IMAGE_TAG = 'preview'


def get_image_tag() -> str:
    """
    Returns the tag of the EventSourcingDB image that the tests run against.
    It is the only place that decides the tag: the CI sets the environment
    variable to run the tests once per tag, a local run without it uses the
    default.
    """
    return os.environ.get(IMAGE_TAG_VARIABLE) or DEFAULT_IMAGE_TAG
