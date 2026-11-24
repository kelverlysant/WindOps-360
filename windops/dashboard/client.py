"""Thin HTTP client for the WindOps API, with short-lived caching."""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from windops.config import API_URL


class ApiError(RuntimeError):
    pass


def _params(params: dict[str, Any] | None) -> tuple:
    return tuple(sorted((k, v) for k, v in (params or {}).items() if v is not None))


@st.cache_data(ttl=30, show_spinner=False)
def _cached_get(path: str, params: tuple) -> Any:
    response = httpx.get(f"{API_URL}{path}", params=dict(params), timeout=30)
    response.raise_for_status()
    return response.json()


def get(path: str, params: dict[str, Any] | None = None) -> Any:
    return _cached_get(path, _params(params))


def send(method: str, path: str, payload: dict) -> tuple[bool, Any]:
    """POST/PATCH; returns (ok, body). Clears the cache so screens refresh."""
    response = httpx.request(method, f"{API_URL}{path}", json=payload, timeout=30)
    _cached_get.clear()
    body = response.json() if response.content else None
    if response.is_success:
        return True, body
    detail = body.get("detail") if isinstance(body, dict) else body
    if isinstance(detail, list):  # pydantic validation errors
        detail = "; ".join(str(item.get("msg", item)) for item in detail)
    return False, detail


def is_available() -> bool:
    try:
        get("/health")
        return True
    except httpx.HTTPError:
        return False
