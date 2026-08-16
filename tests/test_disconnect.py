"""Unit tests for functions/disconnect.py."""

from __future__ import annotations

import pytest

from functions import disconnect
from tests.conftest import FakeContext, FakeTable, websocket_event


def test_disconnect_removes_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable()
    monkeypatch.setattr(disconnect, "connections_table", lambda: table)

    result = disconnect.handler(websocket_event(route_key="$disconnect"), FakeContext())

    assert result["statusCode"] == 200
    assert table.deleted_keys == [{"connectionId": "sender-1"}]
