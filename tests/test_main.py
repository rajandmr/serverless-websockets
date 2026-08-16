"""Unit tests for the WebSocket handlers."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app import main


def websocket_event(
    *,
    connection_id: str = "sender-1",
    body: str | None = None,
    route_key: str = "sendmessage",
) -> dict[str, Any]:
    return {
        "body": body,
        "isBase64Encoded": False,
        "requestContext": {
            "connectionId": connection_id,
            "domainName": "example.execute-api.us-east-1.amazonaws.com",
            "stage": "dev",
            "routeKey": route_key,
        },
    }


class FakeTable:
    def __init__(self, pages: list[dict[str, Any]] | None = None) -> None:
        self.pages = pages or [{"Items": []}]
        self.put_items: list[dict[str, str]] = []
        self.deleted_keys: list[dict[str, str]] = []
        self.scan_calls: list[dict[str, Any]] = []

    def put_item(self, *, Item: dict[str, str]) -> None:
        self.put_items.append(Item)

    def delete_item(self, *, Key: dict[str, str]) -> None:
        self.deleted_keys.append(Key)

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        self.scan_calls.append(kwargs)
        return self.pages[len(self.scan_calls) - 1]


class GoneException(Exception):
    pass


class FakeManagementClient:
    class exceptions:
        GoneException = GoneException

    def __init__(self, gone_connection_id: str | None = None) -> None:
        self.gone_connection_id = gone_connection_id
        self.sent: list[tuple[str, bytes]] = []

    def post_to_connection(self, *, ConnectionId: str, Data: bytes) -> None:
        if ConnectionId == self.gone_connection_id:
            raise GoneException()
        self.sent.append((ConnectionId, Data))


def response_body(response: dict[str, Any]) -> dict[str, str]:
    return json.loads(response["body"])


def test_connect_stores_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable()
    monkeypatch.setattr(main, "_connections_table", lambda: table)

    response = main.connect_handler(websocket_event(route_key="$connect"), None)

    assert response["statusCode"] == 200
    assert table.put_items == [{"connectionId": "sender-1"}]


def test_disconnect_removes_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable()
    monkeypatch.setattr(main, "_connections_table", lambda: table)

    response = main.disconnect_handler(websocket_event(route_key="$disconnect"), None)

    assert response["statusCode"] == 200
    assert table.deleted_keys == [{"connectionId": "sender-1"}]


def test_send_message_broadcasts_and_removes_stale_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = FakeTable(
        [
            {
                "Items": [{"connectionId": "sender-1"}, {"connectionId": "stale-2"}],
                "LastEvaluatedKey": {"connectionId": "stale-2"},
            },
            {"Items": [{"connectionId": "listener-3"}]},
        ]
    )
    client = FakeManagementClient(gone_connection_id="stale-2")
    monkeypatch.setattr(main, "_connections_table", lambda: table)
    monkeypatch.setattr(main, "_management_client", lambda _event: client)

    response = main.send_message_handler(
        websocket_event(body='{"action":"sendmessage","message":"hello"}'), None
    )

    assert response["statusCode"] == 200
    assert response_body(response) == {"message": "broadcast"}
    assert [connection_id for connection_id, _payload in client.sent] == ["sender-1", "listener-3"]
    assert json.loads(client.sent[0][1]) == {
        "message": "hello",
        "senderConnectionId": "sender-1",
    }
    assert table.deleted_keys == [{"connectionId": "stale-2"}]
    assert table.scan_calls == [{}, {"ExclusiveStartKey": {"connectionId": "stale-2"}}]


@pytest.mark.parametrize("body", [None, "not-json", "{}", '{"message":" "}', '{"message":2}'])
def test_send_message_rejects_invalid_payload(
    monkeypatch: pytest.MonkeyPatch, body: str | None
) -> None:
    monkeypatch.setattr(main, "_connections_table", lambda: pytest.fail("table should not be used"))

    response = main.send_message_handler(websocket_event(body=body), None)

    assert response["statusCode"] == 400


def test_default_handler_rejects_unknown_action() -> None:
    response = main.default_handler(websocket_event(body='{"action":"unknown"}'), None)

    assert response["statusCode"] == 400
    assert response_body(response) == {"message": "unsupported action"}
