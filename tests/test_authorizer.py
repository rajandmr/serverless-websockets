"""Unit tests for functions/authorizer.py."""

from __future__ import annotations

import pytest

from functions import authorizer
from tests.conftest import FakeCognitoClient, FakeContext, authorizer_event


def test_authorizer_allows_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeCognitoClient(valid_token="good-token", email="user@example.com")
    monkeypatch.setattr(authorizer, "cognito_idp", client)

    result = authorizer.handler(authorizer_event(token="good-token"), FakeContext())

    assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"
    assert result["context"] == {"email": "user@example.com"}


def test_authorizer_denies_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeCognitoClient(valid_token="good-token", email="user@example.com")
    monkeypatch.setattr(authorizer, "cognito_idp", client)

    result = authorizer.handler(authorizer_event(token=None), FakeContext())

    assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"
    assert client.get_user_calls == []


def test_authorizer_denies_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeCognitoClient(valid_token="good-token", email="user@example.com")
    monkeypatch.setattr(authorizer, "cognito_idp", client)

    result = authorizer.handler(authorizer_event(token="bad-token"), FakeContext())

    assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"
