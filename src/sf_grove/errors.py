"""Error type and JSON envelope helpers shared by the CLI and the MCP server."""

from __future__ import annotations

from typing import Any

ERROR_CODES = ("not_found", "invalid", "io", "internal")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class GroveError(Exception):
    """An expected failure that maps onto the error envelope."""

    def __init__(self, code: str, message: str) -> None:
        if code not in ERROR_CODES:
            code = "internal"
        super().__init__(message)
        self.code = code
        self.message = message


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def fail(code: str, message: str) -> dict[str, Any]:
    if code not in ERROR_CODES:
        code = "internal"
    return {"ok": False, "error": {"code": code, "message": message}}


def page_args(limit: Any = None, offset: Any = None) -> tuple[int, int]:
    """Validate paging arguments. Limit defaults to 50 and is clamped to 200."""
    if limit is None:
        limit = DEFAULT_LIMIT
    if offset is None:
        offset = 0
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise GroveError("invalid", "limit must be an integer of at least 1")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise GroveError("invalid", "offset must be an integer of at least 0")
    return min(limit, MAX_LIMIT), offset


def page(items: list[Any], total: int, offset: int, limit: int, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"items": items, "total": total, "offset": offset, "limit": limit}
    data.update(extra)
    return data
