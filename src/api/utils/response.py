"""Both directions of an HTTP response, in one place.

Every response the API sends has the same outer shape:

    {"success": true,  "data": {...}}
    {"success": false, "error": {"code": "...", "message": "..."}}

A client checks one field to know which it got, and reads `error.code` to
branch. Enveloping only errors -- which is where this started -- means a
client has to know per endpoint whether the body is the payload or a wrapper.

Nothing else builds a `JSONResponse`, so this is the one place to audit for
what reaches a client.
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from api.utils.errors import Failure


def success(data: Any = None, status: int = 200) -> JSONResponse:
    """A successful response carrying `data`.

    Takes an already-serialisable value: routers pass a pydantic model's
    `model_dump()`, so the model still defines and validates the shape.
    """
    return JSONResponse(status_code=status, content={"success": True, "data": data})


def respond(failure: Failure) -> JSONResponse:
    """The failure's own status code, with its code and message."""
    return JSONResponse(
        status_code=failure.status,
        content={
            "success": False,
            "error": {"code": failure.code, "message": failure.message},
        },
    )
