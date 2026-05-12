from __future__ import annotations

from product_agent.schemas import ApiError, ApiResponse


def ok(data=None, *, trace_id: str | None = None) -> ApiResponse:
    return ApiResponse(success=True, data=data, trace_id=trace_id)


def fail(code: str, message: str, *, trace_id: str | None = None) -> ApiResponse:
    return ApiResponse(success=False, data=None, error=ApiError(code=code, message=message), trace_id=trace_id)

