"""Unit tests for functions/send_message.py."""

from __future__ import annotations

import json

import pytest

from functions import send_message
from tests.conftest import (
    FakeContext,
    FakeManagementClient,
    FakeTable,
    response_body,
    websocket_event,
)


def test_send_message_delivers_to_recipients_connections_and_removes_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = FakeTable(
        [
            {
                "Items": [
                    {"connectionId": "sender-1", "email": "recipient@example.com"},
                    {"connectionId": "stale-2", "email": "recipient@example.com"},
                ],
                "LastEvaluatedKey": {"connectionId": "stale-2"},
            },
            {"Items": [{"connectionId": "listener-3", "email": "recipient@example.com"}]},
        ]
    )
    client = FakeManagementClient(gone_connection_id="stale-2")
    monkeypatch.setattr(send_message, "connections_table", lambda: table)
    monkeypatch.setattr(send_message, "management_client", lambda _event: client)

    result = send_message.handler(
        websocket_event(
            body='{"action":"sendmessage","recipientEmail":"recipient@example.com","message":"hello"}'
        ),
        FakeContext(),
    )

    assert result["statusCode"] == 200
    assert response_body(result) == {"message": "sent"}
    assert [connection_id for connection_id, _payload in client.sent] == ["sender-1", "listener-3"]
    assert json.loads(client.sent[0][1]) == {
        "message": "hello",
        "senderConnectionId": "sender-1",
    }
    assert table.deleted_keys == [{"connectionId": "stale-2"}]
    assert len(table.query_calls) == 2
    assert table.query_calls[0]["IndexName"] == "EmailIndex"
    assert table.query_calls[1]["ExclusiveStartKey"] == {"connectionId": "stale-2"}


def test_send_message_only_delivers_to_target_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Query against EmailIndex must only ever be seeded with the recipient's connections."""
    table = FakeTable([{"Items": [{"connectionId": "recipient-conn"}]}])
    client = FakeManagementClient()
    monkeypatch.setattr(send_message, "connections_table", lambda: table)
    monkeypatch.setattr(send_message, "management_client", lambda _event: client)

    result = send_message.handler(
        websocket_event(
            body='{"action":"sendmessage","recipientEmail":"target@example.com","message":"hi"}'
        ),
        FakeContext(),
    )

    assert result["statusCode"] == 200
    assert [connection_id for connection_id, _payload in client.sent] == ["recipient-conn"]
    condition = table.query_calls[0]["KeyConditionExpression"]
    assert condition._values[1] == "target@example.com"


def test_send_message_continues_after_delivery_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ClientError delivering to one connection must not abort delivery to the rest."""
    table = FakeTable(
        [{"Items": [{"connectionId": "broken-1"}, {"connectionId": "listener-2"}]}]
    )
    client = FakeManagementClient(error_connection_id="broken-1")
    monkeypatch.setattr(send_message, "connections_table", lambda: table)
    monkeypatch.setattr(send_message, "management_client", lambda _event: client)

    result = send_message.handler(
        websocket_event(
            body='{"action":"sendmessage","recipientEmail":"recipient@example.com","message":"hello"}'
        ),
        FakeContext(),
    )

    assert result["statusCode"] == 200
    assert [connection_id for connection_id, _payload in client.sent] == ["listener-2"]
    assert table.deleted_keys == []


@pytest.mark.parametrize(
    "body",
    [
        None,
        "not-json",
        "{}",
        '{"recipientEmail":"recipient@example.com","message":" "}',
        '{"recipientEmail":"recipient@example.com","message":2}',
        '{"recipientEmail":"not-an-email","message":"hello"}',
        '{"message":"hello"}',
    ],
)
def test_send_message_rejects_invalid_payload(
    monkeypatch: pytest.MonkeyPatch, body: str | None
) -> None:
    monkeypatch.setattr(
        send_message, "connections_table", lambda: pytest.fail("table should not be used")
    )

    result = send_message.handler(websocket_event(body=body), FakeContext())

    assert result["statusCode"] == 400
