"""Unit tests for functions/connect.py."""

from __future__ import annotations

import pytest

from functions import connect
from tests.conftest import FakeContext, FakeTable, websocket_event


def test_connect_stores_connection_with_authorized_email(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable()
    monkeypatch.setattr(connect, "connections_table", lambda: table)

    result = connect.handler(
        websocket_event(route_key="$connect", authorizer={"email": "user@example.com"}),
        FakeContext(),
    )

    assert result["statusCode"] == 200
    assert table.put_items == [{"connectionId": "sender-1", "email": "user@example.com"}]
