"""Response normalization for all parser implementations."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .schemas import ITEM_FIELDS, validate_response


def normalize_item(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    normalized = {field: item.get(field) for field in ITEM_FIELDS}
    if all(value is None for value in normalized.values()):
        return None
    return normalized


def normalize_items(result: Any) -> List[Dict[str, Any]]:
    """Convert dict/list parser output to a clean canonical item list."""
    candidates = result if isinstance(result, list) else [result]
    items = []
    for candidate in candidates:
        item = normalize_item(candidate)
        if item is not None:
            items.append(item)
    return items


def _meta(
    mode: Optional[str],
    parser: Optional[str],
    routing_confidence: Optional[float],
    result_quality: Optional[float],
    fallback_used: bool,
    fallback_reason: Optional[str],
    latency_ms: float,
) -> Dict[str, Any]:
    return {
        "mode": mode,
        "parser": parser,
        "routing_confidence": routing_confidence,
        "result_quality": result_quality,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "latency_ms": round(max(0.0, float(latency_ms)), 3),
    }


def build_success_response(
    query: str,
    result: Any,
    *,
    mode: Optional[str] = None,
    parser: Optional[str] = None,
    routing_confidence: Optional[float] = None,
    result_quality: Optional[float] = None,
    fallback_used: bool = False,
    fallback_reason: Optional[str] = None,
    latency_ms: float = 0.0,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    # CHỈ TRẢ items array - minimal response cho speed
    return normalize_items(result)


def build_error_response(
    query: str,
    code: str,
    message: str,
    *,
    mode: Optional[str] = None,
    latency_ms: float = 0.0,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    payload = {
        "success": False,
        "query": query,
        "items": [],
        "meta": _meta(mode, None, None, None, False, None, latency_ms),
        "warnings": warnings or [],
        "error": {"code": code, "message": message},
    }
    return validate_response(payload, success=False)
