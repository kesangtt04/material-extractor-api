"""Strict, dependency-free validation for the Flask API contract."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Optional

ITEM_FIELDS = ("Tên sản phẩm", "Mã sản phẩm", "Số lượng", "Đơn vị")
META_FIELDS = (
    "mode",
    "parser",
    "routing_confidence",
    "result_quality",
    "fallback_used",
    "fallback_reason",
    "latency_ms",
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_item(item: Any) -> None:
    if not isinstance(item, dict):
        raise ValueError("item must be an object")
    if set(item) != set(ITEM_FIELDS):
        raise ValueError("item must contain exactly the canonical fields")
    for field in ("Tên sản phẩm", "Mã sản phẩm", "Đơn vị"):
        value = item[field]
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{field} must be a string or null")
    quantity = item["Số lượng"]
    if quantity is not None and not _is_number(quantity):
        raise ValueError("Số lượng must be a finite number or null")
    if all(item[field] is None for field in ITEM_FIELDS):
        raise ValueError("item cannot be completely empty")


def _validate_range(value: Any, field: str) -> None:
    if value is not None and (not _is_number(value) or not 0 <= value <= 1):
        raise ValueError(f"{field} must be between 0 and 1 or null")


def validate_response(payload: Dict[str, Any], success: Optional[bool] = None) -> Dict[str, Any]:
    """Validate a public response and return it unchanged."""
    if not isinstance(payload, dict):
        raise ValueError("response must be an object")
    required = {"success", "query", "items", "meta", "warnings"}
    if not required.issubset(payload):
        raise ValueError("response is missing required fields")
    if not isinstance(payload["success"], bool):
        raise ValueError("success must be boolean")
    if success is not None and payload["success"] is not success:
        raise ValueError("response success flag is inconsistent")
    if not isinstance(payload["query"], str):
        raise ValueError("query must be a string")
    if not isinstance(payload["items"], list):
        raise ValueError("items must be an array")
    for item in payload["items"]:
        validate_item(item)
    if not isinstance(payload["warnings"], list) or not all(isinstance(w, str) for w in payload["warnings"]):
        raise ValueError("warnings must be an array of strings")

    meta = payload["meta"]
    if not isinstance(meta, dict) or not set(META_FIELDS).issubset(meta):
        raise ValueError("meta is missing required fields")
    if meta["mode"] is not None and not isinstance(meta["mode"], str):
        raise ValueError("meta.mode must be a string or null")
    if meta["parser"] is not None and not isinstance(meta["parser"], str):
        raise ValueError("meta.parser must be a string or null")
    _validate_range(meta["routing_confidence"], "routing_confidence")
    _validate_range(meta["result_quality"], "result_quality")
    if not isinstance(meta["fallback_used"], bool):
        raise ValueError("fallback_used must be boolean")
    if meta["fallback_reason"] is not None and not isinstance(meta["fallback_reason"], str):
        raise ValueError("fallback_reason must be a string or null")
    if not _is_number(meta["latency_ms"]) or meta["latency_ms"] < 0:
        raise ValueError("latency_ms must be a non-negative number")

    if payload["success"] is False:
        error = payload.get("error")
        if not isinstance(error, dict) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
            raise ValueError("failed response must contain error.code and error.message")
    return payload


def validate_examples(examples: Iterable[Dict[str, Any]]) -> None:
    for example in examples:
        if not isinstance(example, dict) or not isinstance(example.get("query"), str) or not isinstance(example.get("type"), str):
            raise ValueError("each example must contain query and type strings")
