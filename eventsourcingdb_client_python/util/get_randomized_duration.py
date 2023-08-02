import random


def get_randomized_duration(
    duration_milliseconds: int,
    deviation_milliseconds: int
) -> int:
    return duration_milliseconds \
        - deviation_milliseconds \
        + round(random.random() * deviation_milliseconds * 2)
