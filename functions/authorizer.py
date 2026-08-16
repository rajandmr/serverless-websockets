"""Authorize a WebSocket $connect request using a verified Cognito access token."""

from typing import Any

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes.api_gateway_authorizer_event import (
    APIGatewayAuthorizerRequestEvent,
    APIGatewayAuthorizerResponseWebSocket,
)
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError

logger = Logger()
cognito_idp = boto3.client("cognito-idp")


def _verified_email(token: str) -> str | None:
    try:
        user = cognito_idp.get_user(AccessToken=token)
    except ClientError:
        return None
    attributes = {attr["Name"]: attr.get("Value") for attr in user["UserAttributes"]}
    return attributes.get("email")


@logger.inject_lambda_context(log_event=True)
def handler(event: dict[str, Any], _context: LambdaContext) -> dict[str, Any]:
    authorizer_event = APIGatewayAuthorizerRequestEvent(event)
    token = authorizer_event.query_string_parameters.get("token")
    email = _verified_email(token) if token else None

    if email is None:
        logger.warning(
            "Rejected WebSocket connect: missing or invalid Cognito access token"
        )
        deny = APIGatewayAuthorizerResponseWebSocket.from_route_arn(
            authorizer_event.method_arn, principal_id="anonymous"
        )
        deny.deny_all_routes()
        return deny.asdict()

    logger.info("Authorized WebSocket connect", extra={"email": email})
    allow = APIGatewayAuthorizerResponseWebSocket.from_route_arn(
        authorizer_event.method_arn, principal_id=email, context={"email": email}
    )
    allow.allow_all_routes()
    return allow.asdict()
