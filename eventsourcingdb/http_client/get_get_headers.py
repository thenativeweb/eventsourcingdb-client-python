def get_get_headers(api_token: str, with_authorization: bool) -> dict[str, str]:
    headers = {}
    if with_authorization:
        headers['Authorization'] = f'Bearer {api_token}'
    return headers
