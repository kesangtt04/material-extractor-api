# -*- coding: utf-8 -*-
"""
API Validation Layer
====================

Validate các input từ client trước khi đưa vào pipeline xử lý.

⚠️ Mục đích: Bảo vệ server khỏi:
- DoS attacks (gửi query 100K+ ký tự → CPU treo)
- Invalid types (None, int, list)
- Empty/whitespace-only queries
- Excessively long inputs gây OOM

Validation rules (v1):
- Query phải là string
- Query không rỗng sau khi strip
- Query length ≤ MAX_QUERY_LENGTH (1000 chars)
- Token count ≤ MAX_TOKEN_COUNT (200 tokens)

Author: Material Extractor Project
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


# ==============================================================================
# Constants
# ==============================================================================

#: Maximum query length in characters (DoS protection)
MAX_QUERY_LENGTH = 1000

#: Maximum token count (sanity check after tokenization)
MAX_TOKEN_COUNT = 200

#: Minimum query length (reject trivial inputs)
MIN_QUERY_LENGTH = 1


# ==============================================================================
# Validation Result
# ==============================================================================

@dataclass
class ValidationResult:
    """
    Kết quả validation.

    Attributes:
        valid: True nếu input hợp lệ
        query: Query đã được normalized (stripped) nếu valid
        error_code: Mã lỗi nếu invalid
        error_message: Mô tả lỗi chi tiết
    """
    valid: bool
    query: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dict for JSON response."""
        result = {"valid": self.valid}
        if self.query is not None:
            result["query"] = self.query
        if self.error_code:
            result["error_code"] = self.error_code
        if self.error_message:
            result["error_message"] = self.error_message
        return result


# ==============================================================================
# Main Validator
# ==============================================================================

class QueryValidator:
    """
    Validator cho input query từ API clients.

    Usage:
        validator = QueryValidator()
        result = validator.validate({"query": "20 cái búa"})
        if result.valid:
            process(result.query)
        else:
            return error(result.error_code, result.error_message)
    """

    def __init__(
        self,
        max_query_length: int = MAX_QUERY_LENGTH,
        max_token_count: int = MAX_TOKEN_COUNT,
        min_query_length: int = MIN_QUERY_LENGTH,
    ):
        self.max_query_length = max_query_length
        self.max_token_count = max_token_count
        self.min_query_length = min_query_length

    def validate(self, data: Any) -> ValidationResult:
        """
        Validate request body và trích xuất query string.

        Validation pipeline:
        1. Check data is dict → INVALID_JSON
        2. Extract 'query' field → MISSING_QUERY
        3. Check query is string → INVALID_TYPE
        4. Strip whitespace
        5. Check length >= min → EMPTY_QUERY
        6. Check length <= max → QUERY_TOO_LONG
        7. Check token count → TOO_MANY_TOKENS

        Args:
            data: Request body (dict từ request.get_json())

        Returns:
            ValidationResult with extracted query or error info
        """
        # Step 1: Check data is dict
        if not isinstance(data, dict):
            return ValidationResult(
                valid=False,
                error_code="INVALID_JSON",
                error_message="Request body phải là JSON object"
            )

        # Step 2: Extract 'query' field
        if 'query' not in data:
            return ValidationResult(
                valid=False,
                error_code="MISSING_QUERY",
                error_message="Thiếu trường 'query' trong request"
            )

        raw_query = data['query']

        # Step 3: Check query type
        if not isinstance(raw_query, str):
            return ValidationResult(
                valid=False,
                error_code="INVALID_TYPE",
                error_message=f"'query' phải là string, nhận {type(raw_query).__name__}"
            )

        # Step 4: Strip whitespace
        query = raw_query.strip()

        # Step 5: Check minimum length
        if len(query) < self.min_query_length:
            return ValidationResult(
                valid=False,
                error_code="EMPTY_QUERY",
                error_message="Query rỗng hoặc chỉ chứa whitespace"
            )

        # Step 6: Check maximum length (DoS protection)
        if len(query) > self.max_query_length:
            return ValidationResult(
                valid=False,
                error_code="QUERY_TOO_LONG",
                error_message=(
                    f"Query quá dài: {len(query)} ký tự "
                    f"(tối đa {self.max_query_length}). "
                    f"Vui lòng rút gọn truy vấn."
                )
            )

        # Step 7: Sanity check token count (post-strip)
        token_count = len(query.split())
        if token_count > self.max_token_count:
            return ValidationResult(
                valid=False,
                error_code="TOO_MANY_TOKENS",
                error_message=(
                    f"Query có quá nhiều tokens: {token_count} "
                    f"(tối đa {self.max_token_count})"
                )
            )

        # All checks passed
        return ValidationResult(valid=True, query=query)


# ==============================================================================
# Convenience Function
# ==============================================================================

def validate_query(data: Any, max_length: int = MAX_QUERY_LENGTH) -> ValidationResult:
    """
    Standalone validation function (backward compatible).

    Args:
        data: Request body
        max_length: Override max length

    Returns:
        ValidationResult
    """
    validator = QueryValidator(max_query_length=max_length)
    return validator.validate(data)
