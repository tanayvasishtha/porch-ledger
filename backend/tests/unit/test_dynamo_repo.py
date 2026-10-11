"""DynamoRepository request shapes: Stubber asserts exact API params."""

import asyncio
from typing import Any

import boto3
from botocore.stub import ANY, Stubber

from porch.adapters.aws.dynamo_repo import DynamoRepository
from tests.helpers import mkvisit


def _client() -> Any:
    # boto3-stubs overloads on literal service names; tests keep it dynamic.
    return boto3.Session(
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    ).client("dynamodb")


def test_save_visits_writes_item_and_pointer() -> None:
    client = _client()
    repo = DynamoRepository(client, "porch")
    visit = mkvisit("v1", 1000, house_id="h1")
    with Stubber(client) as stubber:
        stubber.add_response(
            "get_item",
            {},
            {"TableName": "porch", "Key": {"PK": {"S": "VISIT#v1"}, "SK": {"S": "META"}}},
        )
        stubber.add_response(
            "put_item",
            {},
            {
                "TableName": "porch",
                "Item": {
                    "PK": {"S": "HOUSE#h1"},
                    "SK": {"S": "VISIT#0000000001000#v1"},
                    "body": {"S": ANY},
                    "version": {"N": "1"},
                },
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )
        stubber.add_response(
            "put_item",
            {},
            {
                "TableName": "porch",
                "Item": {
                    "PK": {"S": "VISIT#v1"},
                    "SK": {"S": "META"},
                    "house_id": {"S": "h1"},
                    "start_ms": {"N": "1000"},
                },
            },
        )
        stubber.add_response(
            "update_item",
            {"Attributes": {"version": {"N": "1"}}},
            {
                "TableName": "porch",
                "Key": {"PK": {"S": "HOUSE#h1"}, "SK": {"S": "VERSION"}},
                "UpdateExpression": "ADD #v :one",
                "ExpressionAttributeNames": {"#v": "version"},
                "ExpressionAttributeValues": {":one": {"N": "1"}},
                "ReturnValues": "UPDATED_NEW",
            },
        )
        asyncio.run(repo.save_visits([visit]))
        stubber.assert_no_pending_responses()


def test_visits_between_queries_sk_window() -> None:
    client = _client()
    repo = DynamoRepository(client, "porch")
    with Stubber(client) as stubber:
        stubber.add_response(
            "query",
            {"Items": []},
            {
                "TableName": "porch",
                "KeyConditionExpression": "#pk = :pk AND #sk >= :lo AND #sk < :hi",
                "ExpressionAttributeNames": {"#pk": "PK", "#sk": "SK"},
                "ExpressionAttributeValues": {
                    ":pk": {"S": "HOUSE#h1"},
                    ":lo": {"S": "VISIT#0000000001000#"},
                    ":hi": {"S": "VISIT#0000000002000#"},
                },
            },
        )
        out = asyncio.run(repo.visits_between("h1", 1000, 2000))
        assert out == []
        stubber.assert_no_pending_responses()


def test_bump_version_uses_atomic_add() -> None:
    client = _client()
    repo = DynamoRepository(client, "porch")
    with Stubber(client) as stubber:
        stubber.add_response(
            "update_item",
            {"Attributes": {"version": {"N": "7"}}},
            {
                "TableName": "porch",
                "Key": {"PK": {"S": "HOUSE#h1"}, "SK": {"S": "VERSION"}},
                "UpdateExpression": "ADD #v :one",
                "ExpressionAttributeNames": {"#v": "version"},
                "ExpressionAttributeValues": {":one": {"N": "1"}},
                "ReturnValues": "UPDATED_NEW",
            },
        )
        assert asyncio.run(repo.bump_version("h1")) == 7
        stubber.assert_no_pending_responses()


def test_cursor_and_state_keys() -> None:
    client = _client()
    repo = DynamoRepository(client, "porch")
    with Stubber(client) as stubber:
        stubber.add_response(
            "put_item",
            {},
            {
                "TableName": "porch",
                "Item": {
                    "PK": {"S": "DEVICE#d1"},
                    "SK": {"S": "CURSOR"},
                    "ms": {"N": "42"},
                },
            },
        )
        stubber.add_response(
            "get_item",
            {"Item": {"ms": {"N": "42"}}},
            {
                "TableName": "porch",
                "Key": {"PK": {"S": "DEVICE#d1"}, "SK": {"S": "CURSOR"}},
            },
        )
        asyncio.run(repo.set_cursor("d1", 42))
        assert asyncio.run(repo.get_cursor("d1")) == 42
        stubber.assert_no_pending_responses()
