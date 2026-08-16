"""Remove a disconnected WebSocket client."""

from typing import Any

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import (
    APIGatewayWebSocketEvent,
    event_source,
)
from aws_lambda_powertools.utilities.typing import LambdaContext

from utils.helper import connections_table, response

logger = Logger()


@logger.inject_lambda_context(log_event=True)
@event_source(data_class=APIGatewayWebSocketEvent)
def handler(event: APIGatewayWebSocketEvent, _context: LambdaContext) -> dict[str, Any]:
    connection_id = event.request_context.connection_id
    connections_table().delete_item(Key={"connectionId": connection_id})
    logger.info("WebSocket client disconnected", extra={"connection_id": connection_id})
    return response(200, {"message": "disconnected"})
