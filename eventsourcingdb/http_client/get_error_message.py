import aiohttp

from .response import Response

async def get_error_message(response: Response) -> str:
    """Extrahiert Fehlermeldung aus der Response."""
    error_message = f'Request failed with status code \'{response.status_code}\''

    try:
        encoded_error_reason = await response.body.read()
    except (aiohttp.ClientError, IOError):  # Use specific exception types instead of Exception
        pass
    else:
        try:
            error_reason = encoded_error_reason.decode('utf-8')
        except UnicodeDecodeError:  # Use specific exception type instead of Exception
            pass
        else:
            error_message += f" {error_reason}"

    error_message += '.'
    return error_message
