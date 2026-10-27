"""Every HTTP response uses the same envelope."""

from fastapi.responses import JSONResponse


def ok(data, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content={"data": data, "error": None})


def fail(status: int, code: str, message: str, fields: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"data": None, "error": {"code": code, "message": message, "fields": fields or {}}},
    )
