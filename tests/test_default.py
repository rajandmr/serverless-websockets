"""Unit tests for functions/default.py."""

from __future__ import annotations

from functions import default
from tests.conftest import FakeContext, response_body, websocket_event


def test_default_handler_rejects_unknown_action() -> None:
    result = default.handler(websocket_event(body='{"action":"unknown"}'), FakeContext())

    assert result["statusCode"] == 400
    assert response_body(result) == {"message": "unsupported action"}
