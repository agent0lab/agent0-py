"""
Tests for A2A client (agent0_sdk.core.a2a_client).
"""

import pytest
from unittest.mock import Mock, patch

from agent0_sdk.core.a2a import Part, MessageA2AOptions, AgentCardAuth
from agent0_sdk.core.a2a_client import (
    normalize_interfaces,
    pick_interface,
    normalize_binding,
    apply_credential,
    parts_for_send,
    _part_from_dict,
)


class TestNormalizeBinding:
    def test_http_json(self):
        assert normalize_binding("HTTP+JSON") == "HTTP+JSON"
        assert normalize_binding("http+json") == "HTTP+JSON"

    def test_auto_fallback(self):
        assert normalize_binding("") == "AUTO"
        assert normalize_binding(None) == "AUTO"
        assert normalize_binding("unknown") == "AUTO"


class TestNormalizeInterfaces:
    def test_empty_card_returns_empty(self):
        assert normalize_interfaces(None) == []
        assert normalize_interfaces({}) == []

    def test_supported_interfaces_v1(self):
        card = {
            "supportedInterfaces": [
                {"url": "https://agent.example.com/a2a", "protocolBinding": "HTTP+JSON", "protocolVersion": "0.3"},
            ],
        }
        out = normalize_interfaces(card)
        assert len(out) == 1
        assert out[0]["url"] == "https://agent.example.com/a2a"
        assert out[0]["binding"] == "HTTP+JSON"
        assert out[0]["version"] == "0.3"

    def test_primary_url_fallback(self):
        card = {"url": "https://agent.example.com", "preferredTransport": "HTTP+JSON"}
        out = normalize_interfaces(card)
        assert len(out) == 1
        assert out[0]["url"] == "https://agent.example.com"


class TestPickInterface:
    def test_prefers_http_json(self):
        interfaces = [
            {"url": "https://a", "binding": "AUTO", "version": None},
            {"url": "https://b", "binding": "HTTP+JSON", "version": "0.3"},
        ]
        chosen = pick_interface(interfaces, ["HTTP+JSON", "JSONRPC"])
        assert chosen is not None
        assert chosen["binding"] == "HTTP+JSON"
        assert chosen["url"] == "https://b"


class TestApplyCredential:
    def test_api_key_header(self):
        auth = AgentCardAuth(
            securitySchemes={"apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}},
            security=[{"apiKey": []}],
        )
        out = apply_credential("secret-key", auth)
        assert out["headers"].get("X-API-Key") == "secret-key"

    def test_string_normalizes_to_api_key(self):
        auth = AgentCardAuth(
            securitySchemes={"apiKey": {"type": "apiKey", "in": "header", "name": "Authorization"}},
            security=[{"apiKey": []}],
        )
        out = apply_credential("my-token", auth)
        assert out["headers"].get("Authorization") == "my-token"


class TestPartsForSend:
    def test_v03_kind_text(self):
        parts = [Part(text="hello")]
        out = parts_for_send(parts, "0.3")
        assert len(out) == 1
        assert out[0]["kind"] == "text"
        assert out[0]["text"] == "hello"

    def test_v1_flat_shape(self):
        parts = [Part(text="hi", url=None)]
        out = parts_for_send(parts, "1.0")
        assert len(out) == 1
        assert "text" in out[0]
        assert out[0]["text"] == "hi"


class TestPartFromDict:
    def test_kind_text(self):
        p = _part_from_dict({"kind": "text", "text": "hello"})
        assert p.text == "hello"
        assert p.url is None

    def test_kind_file_uri(self):
        p = _part_from_dict({"kind": "file", "file": {"uri": "https://example.com/f"}})
        assert p.url == "https://example.com/f"

    def test_flat_dict(self):
        p = _part_from_dict({"text": "flat", "url": "https://u"})
        assert p.text == "flat"
        assert p.url == "https://u"
