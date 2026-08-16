"""Register a newly connected WebSocket client."""

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
    email = (event.request_context.get("authorizer") or {}).get("email")
    connection_id = event.request_context.connection_id
    connections_table().put_item(Item={"connectionId": connection_id, "email": email})
    logger.info(
        "WebSocket client connected", extra={"connection_id": connection_id, "email": email}
    )
    return response(200, {"message": "connected"})
