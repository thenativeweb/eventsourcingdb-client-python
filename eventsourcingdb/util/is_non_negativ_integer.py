def is_non_negative_integer(value: str) -> bool:
    value_as_int: int
    try:
        value_as_int = int(value)
    except ValueError:
        return False

    return value_as_int >= 0
