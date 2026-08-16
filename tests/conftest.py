"""Shared fakes and helpers for handler unit tests."""

from __future__ import annotations

import json
from typing import Any


class FakeContext:
    function_name = "test-function"
    memory_limit_in_mb = 128
    invoked_function_arn = (
        "arn:aws:lambda:us-east-1:123456789012:function:test-function"
    )
    aws_request_id = "test-request-id"


def websocket_event(
    *,
    connection_id: str = "sender-1",
    body: str | None = None,
    route_key: str = "sendmessage",
    authorizer: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "body": body,
        "isBase64Encoded": False,
        "requestContext": {
            "connectionId": connection_id,
            "domainName": "example.execute-api.us-east-1.amazonaws.com",
            "stage": "dev",
            "routeKey": route_key,
            "authorizer": authorizer or {},
        },
    }


def authorizer_event(
    *,
    token: str | None = None,
    method_arn: str = "arn:aws:execute-api:us-east-1:123456789012:abc123/dev/$connect",
) -> dict[str, Any]:
    return {
        "type": "REQUEST",
        "methodArn": method_arn,
        "queryStringParameters": {"token": token} if token else {},
        "headers": {},
        "requestContext": {
            "connectionId": "sender-1",
            "domainName": "example.execute-api.us-east-1.amazonaws.com",
            "stage": "dev",
        },
    }


class FakeTable:
    def __init__(self, pages: list[dict[str, Any]] | None = None) -> None:
        self.pages = pages or [{"Items": []}]
        self.put_items: list[dict[str, str]] = []
        self.deleted_keys: list[dict[str, str]] = []
        self.scan_calls: list[dict[str, Any]] = []
        self.query_calls: list[dict[str, Any]] = []

    def put_item(self, *, Item: dict[str, str]) -> None:
        self.put_items.append(Item)

    def delete_item(self, *, Key: dict[str, str]) -> None:
        self.deleted_keys.append(Key)

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        self.scan_calls.append(kwargs)
        return self.pages[len(self.scan_calls) - 1]

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_calls.append(kwargs)
        return self.pages[len(self.query_calls) - 1]


class GoneException(Exception):
    pass


class FakeManagementClient:
    class exceptions:
        GoneException = GoneException

    def __init__(
        self,
        gone_connection_id: str | None = None,
        error_connection_id: str | None = None,
    ) -> None:
        self.gone_connection_id = gone_connection_id
        self.error_connection_id = error_connection_id
        self.sent: list[tuple[str, bytes]] = []

    def post_to_connection(self, *, ConnectionId: str, Data: bytes) -> None:
        if ConnectionId == self.gone_connection_id:
            raise GoneException()
        if ConnectionId == self.error_connection_id:
            from botocore.exceptions import ClientError

            raise ClientError(
                {"Error": {"Code": "InternalServerError"}}, "PostToConnection"
            )
        self.sent.append((ConnectionId, Data))


def response_body(response: dict[str, Any]) -> dict[str, str]:
    return json.loads(response["body"])


class FakeCognitoClient:
    def __init__(
        self,
        valid_token: str | None = None,
        email: str | None = None,
        username: str = "user-1",
    ) -> None:
        self.valid_token = valid_token
        self.email = email
        self.username = username
        self.get_user_calls: list[str] = []

    def get_user(self, *, AccessToken: str) -> dict[str, Any]:
        self.get_user_calls.append(AccessToken)
        if AccessToken != self.valid_token:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "NotAuthorizedException"}}, "GetUser")

        attributes = [{"Name": "email", "Value": self.email}] if self.email else []
        return {"Username": self.username, "UserAttributes": attributes}
