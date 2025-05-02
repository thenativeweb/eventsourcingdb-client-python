def get_post_headers(api_token: str) -> dict[str, str]:
    return {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }
