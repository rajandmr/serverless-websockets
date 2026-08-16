"""API Gateway WebSocket handlers for the broadcast-chat prototype."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Serverless packages production dependencies into this adjacent directory.
DEPENDENCY_DIRECTORY = Path(__file__).parent.parent / ".requirements"
if str(DEPENDENCY_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(DEPENDENCY_DIRECTORY))

import boto3  # noqa: E402
from aws_lambda_powertools import Logger  # noqa: E402
from aws_lambda_powertools.utilities.data_classes import (  # noqa: E402
    APIGatewayWebSocketEvent,
    event_source,
)
from botocore.exceptions import ClientError  # noqa: E402

logger = Logger()


def _connections_table() -> Any:
    return boto3.resource("dynamodb").Table(os.environ["CONNECTIONS_TABLE"])


def _management_client(event: APIGatewayWebSocketEvent) -> Any:
    endpoint_url = f"https://{event.request_context.domain_name}/{event.request_context.stage}"
    return boto3.client("apigatewaymanagementapi", endpoint_url=endpoint_url)


def _response(status_code: int, body: dict[str, str]) -> dict[str, Any]:
    return {"statusCode": status_code, "body": json.dumps(body)}


@event_source(data_class=APIGatewayWebSocketEvent)  # type: ignore[misc]
def connect_handler(event: APIGatewayWebSocketEvent, _context: Any) -> dict[str, Any]:
    """Register a newly connected WebSocket client."""
    connection_id = event.request_context.connection_id
    _connections_table().put_item(Item={"connectionId": connection_id})
    logger.info("WebSocket client connected", extra={"connection_id": connection_id})
    return _response(200, {"message": "connected"})


@event_source(data_class=APIGatewayWebSocketEvent)  # type: ignore[misc]
def disconnect_handler(event: APIGatewayWebSocketEvent, _context: Any) -> dict[str, Any]:
    """Remove a disconnected WebSocket client."""
    connection_id = event.request_context.connection_id
    _connections_table().delete_item(Key={"connectionId": connection_id})
    logger.info("WebSocket client disconnected", extra={"connection_id": connection_id})
    return _response(200, {"message": "disconnected"})


def _message_from_event(event: APIGatewayWebSocketEvent) -> str | None:
    try:
        payload = json.loads(event.body or "")
    except json.JSONDecodeError:
        return None

    message = payload.get("message") if isinstance(payload, dict) else None
    return message if isinstance(message, str) and message.strip() else None


@event_source(data_class=APIGatewayWebSocketEvent)  # type: ignore[misc]
def send_message_handler(event: APIGatewayWebSocketEvent, _context: Any) -> dict[str, Any]:
    """Broadcast a valid client message and prune stale connections."""
    message = _message_from_event(event)
    if message is None:
        return _response(400, {"message": "body must include a non-empty string message"})

    sender_connection_id = event.request_context.connection_id
    payload = json.dumps({"message": message, "senderConnectionId": sender_connection_id}).encode()
    table = _connections_table()
    client = _management_client(event)
    delivered = 0

    scan_kwargs: dict[str, Any] = {}
    while True:
        page = table.scan(**scan_kwargs)
        for item in page.get("Items", []):
            connection_id = item["connectionId"]
            try:
                client.post_to_connection(ConnectionId=connection_id, Data=payload)
                delivered += 1
            except client.exceptions.GoneException:
                table.delete_item(Key={"connectionId": connection_id})
                logger.info(
                    "Removed stale WebSocket connection", extra={"connection_id": connection_id}
                )
            except ClientError:
                logger.exception(
                    "Failed to deliver WebSocket message", extra={"connection_id": connection_id}
                )
                raise

        last_evaluated_key = page.get("LastEvaluatedKey")
        if last_evaluated_key is None:
            break
        scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

    logger.info(
        "Broadcast WebSocket message",
        extra={"sender_connection_id": sender_connection_id, "delivered": delivered},
    )
    return _response(200, {"message": "broadcast"})


@event_source(data_class=APIGatewayWebSocketEvent)  # type: ignore[misc]
def default_handler(_event: APIGatewayWebSocketEvent, _context: Any) -> dict[str, Any]:
    """Reject unsupported WebSocket actions without closing the connection."""
    return _response(400, {"message": "unsupported action"})
