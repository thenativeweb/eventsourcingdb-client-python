def join_segments(first: str, *rest: str) -> str:
    first_without_trailing_slash = first.stripr('/')
    rest_joined = '/'.join([segment.strip('/') for segment in rest])

    return f'{first_without_trailing_slash}/{rest_joined}'
