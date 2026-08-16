import json
import os
from collections.abc import Iterator
from typing import Any

import boto3
from aws_lambda_powertools.utilities.data_classes import APIGatewayWebSocketEvent


def connections_table() -> Any:
    return boto3.resource("dynamodb").Table(os.environ["CONNECTIONS_TABLE"])


def fetch_all_items(table: Any, **query_kwargs: Any) -> Iterator[dict[str, Any]]:
    """Yield every item across all pages of a DynamoDB Query."""
    kwargs: dict[str, Any] = dict(query_kwargs)
    while True:
        page = table.query(**kwargs)
        yield from page.get("Items", [])

        last_evaluated_key = page.get("LastEvaluatedKey")
        if last_evaluated_key is None:
            return
        kwargs["ExclusiveStartKey"] = last_evaluated_key


def management_client(event: APIGatewayWebSocketEvent) -> Any:
    endpoint_url = f"https://{event.request_context.domain_name}/{event.request_context.stage}"
    return boto3.client("apigatewaymanagementapi", endpoint_url=endpoint_url)


def response(status_code: int, body: dict[str, str]) -> dict[str, Any]:
    return {"statusCode": status_code, "body": json.dumps(body)}
