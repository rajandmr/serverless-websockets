"""Deliver a message to every open connection belonging to a recipient email."""

import json
from collections.abc import Iterable
from typing import Any

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import (
    APIGatewayWebSocketEvent,
    event_source,
)
from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from utils.helper import connections_table, fetch_all_items, management_client, response

logger = Logger()

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    recipient_email: str = Field(alias="recipientEmail", pattern=EMAIL_PATTERN)
    message: str = Field(min_length=1)

    @field_validator("message")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


def _deliver_to_connections(
    client: Any, table: Any, connections: Iterable[dict[str, Any]], payload: bytes
) -> int:
    """Send payload to each connection, pruning stale ones and skipping failures."""
    delivered = 0
    for item in connections:
        connection_id = item["connectionId"]
        try:
            client.post_to_connection(ConnectionId=connection_id, Data=payload)
            delivered += 1
        except client.exceptions.GoneException:
            table.delete_item(Key={"connectionId": connection_id})
            logger.info("Removed stale WebSocket connection")
        except ClientError:
            logger.exception("Failed to deliver WebSocket message")
    return delivered


@logger.inject_lambda_context(log_event=True)
@event_source(data_class=APIGatewayWebSocketEvent)
def handler(event: APIGatewayWebSocketEvent, _context: LambdaContext) -> dict[str, Any]:
    try:
        send_request = SendMessageRequest.model_validate_json(event.body or "{}")
    except ValidationError:
        return response(
            400, {"message": "body must include recipientEmail and a non-empty message"}
        )

    sender_connection_id = event.request_context.connection_id
    payload = json.dumps(
        {"message": send_request.message, "senderConnectionId": sender_connection_id}
    ).encode()

    table = connections_table()
    client = management_client(event)
    connections = fetch_all_items(
        table,
        IndexName="EmailIndex",
        KeyConditionExpression=Key("email").eq(send_request.recipient_email),
    )
    delivered = _deliver_to_connections(client, table, connections, payload)
    logger.info("Delivered WebSocket message", extra={"delivered": delivered})

    return response(200, {"message": "sent"})
