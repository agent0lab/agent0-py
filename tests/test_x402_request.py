"""
Tests for x402 request flow (agent0_sdk.core.x402_request).
"""

import json
import pytest
from unittest.mock import Mock

from agent0_sdk.core.x402_types import X402Accept, RequestSnapshot, X402RequiredResponse
from agent0_sdk.core.x402_request import request_with_x402, X402RequestDeps


class TestRequestWithX402:
    def test_2xx_returns_parsed_response(self):
        resp = Mock(status_code=200, json=Mock(return_value={"data": "ok"}))
        def fetch(url, method, headers, body, **kwargs):
            return resp
        deps = X402RequestDeps(
            fetch=fetch,
            build_payment=lambda a, s: "dummy-payment",
        )
        result = request_with_x402(
            {"url": "https://example.com/r", "method": "GET", "headers": {}},
            deps,
        )
        assert result == {"data": "ok"}

    def test_402_returns_x402_required_response(self):
        import base64
        payload = {"accepts": [{"price": "1000", "token": "0xabc"}]}
        header_val = base64.b64encode(json.dumps(payload).encode()).decode()
        resp = Mock(
            status_code=402,
            headers={"Payment-Required": header_val},
            text="",
        )
        def fetch(url, method, headers, body, **kwargs):
            return resp
        deps = X402RequestDeps(
            fetch=fetch,
            build_payment=lambda a, s: "signed-payload",
        )
        result = request_with_x402(
            {"url": "https://example.com/r", "method": "GET", "headers": {}},
            deps,
        )
        assert isinstance(result, X402RequiredResponse)
        assert result.x402Required is True
        assert result.x402Payment is not None
        assert callable(result.x402Payment.pay)
