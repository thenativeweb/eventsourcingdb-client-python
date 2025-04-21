
# TODO: Can be MAYBE removed. Have to be checked
def is_non_negative_integer(value: str) -> bool:
    value_as_int: int
    try:
        value_as_int = int(value)
    except ValueError:
        return False

    return value_as_int >= 0
