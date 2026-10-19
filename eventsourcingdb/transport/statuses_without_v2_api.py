from http import HTTPStatus

# How a server without the v2 API, such as EventSourcingDB 1.2, answers a
# request to a path of the v2 API, with or without its management UI.
STATUSES_WITHOUT_V2_API = {HTTPStatus.NOT_FOUND, HTTPStatus.METHOD_NOT_ALLOWED}
