"""Reject unsupported WebSocket actions without closing the connection."""

from typing import Any

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import (
    APIGatewayWebSocketEvent,
    event_source,
)
from aws_lambda_powertools.utilities.typing import LambdaContext

from utils.helper import response

logger = Logger()


@logger.inject_lambda_context(log_event=True)
@event_source(data_class=APIGatewayWebSocketEvent)
def handler(_event: APIGatewayWebSocketEvent, _context: LambdaContext) -> dict[str, Any]:
    return response(400, {"message": "unsupported action"})
