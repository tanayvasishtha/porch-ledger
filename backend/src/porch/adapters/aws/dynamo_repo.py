"""DynamoDB Repository: the single-table design the Lambda worker uses.

Layout: visits live at HOUSE#<h>/VISIT#<padded start_ms>#<id> so a day
window is one Query; a VISIT#<id>/META pointer row maps id to the visit
key; HOUSE#<h>/VERSION is an atomic counter; DEVICE#<d>/CURSOR and
DEVICE#<d>/STATE hold the ingest watermark and resumable stitch state.

Writes go through conditional updates on the stored version so two
workers cannot clobber each other; a failed condition re-reads and
retries a bounded number of times before raising PortError.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, TypeVar

from botocore.exceptions import ClientError
from pydantic import TypeAdapter
from types_boto3_dynamodb.client import DynamoDBClient

from porch.adapters.aws.clients import aws_port_error
from porch.adapters.cassette import Cassette
from porch.adapters.codec import (
    dumps_device_state,
    dumps_visit,
    loads_device_state,
    loads_visit,
)
from porch.domain import DeviceState, Visit
from porch.ports import PortError

T = TypeVar("T")

_ADAPTER = "dynamo"
_VERSION = 1
_MAX_WRITE_ATTEMPTS = 3
_ITEM: TypeAdapter[dict[str, Any] | None] = TypeAdapter(dict[str, Any] | None)
_VISIT_LIST: TypeAdapter[list[Visit]] = TypeAdapter(list[Visit])
_OPT_VISIT: TypeAdapter[Visit | None] = TypeAdapter(Visit | None)


def _visit_pk(house_id: str) -> str:
    return f"HOUSE#{house_id}"


def _visit_sk(start_ms: int, visit_id: str) -> str:
    return f"VISIT#{start_ms:013d}#{visit_id}"


def _pointer_pk(visit_id: str) -> str:
    return f"VISIT#{visit_id}"


def _device_pk(device_id: str) -> str:
    return f"DEVICE#{device_id}"


def _key(pk: str, sk: str) -> dict[str, dict[str, str]]:
    return {"PK": {"S": pk}, "SK": {"S": sk}}


class DynamoRepository:
    def __init__(
        self,
        client: DynamoDBClient,
        table_name: str,
        cassette: Cassette | None = None,
    ) -> None:
        self._client = client
        self._table = table_name
        self._cassette = cassette

    async def _call(
        self,
        op: str,
        request: dict[str, Any],
        fn: Callable[[], Awaitable[T]],
        codec: TypeAdapter[T],
    ) -> T:
        """Record through the cassette when one is configured."""
        if self._cassette is not None:
            return await self._cassette.call(_ADAPTER, _VERSION, {"op": op, **request}, fn, codec)
        return await fn()

    async def save_visits(self, visits: list[Visit]) -> None:
        changed_houses: set[str] = set()
        for visit in visits:
            merged = await self._upsert(visit)
            if merged is not None:
                changed_houses.add(merged.house_id)
        for house_id in sorted(changed_houses):
            await self.bump_version(house_id)

    async def _upsert(self, visit: Visit) -> Visit | None:
        """Merge-write one visit; returns the merged visit when it changed."""
        for _ in range(_MAX_WRITE_ATTEMPTS):
            stored = await self._read(visit.id)
            if stored is None:
                merged = visit
                condition = "attribute_not_exists(PK)"
                expected = None
            else:
                merged = replace(
                    visit,
                    claimed_by=visit.claimed_by or stored.claimed_by,
                    version=stored.version,
                )
                if merged == stored:
                    return None
                merged = replace(merged, version=stored.version + 1)
                condition = "#v = :expected"
                expected = stored.version
            if await self._write_item(merged, condition, expected):
                return merged
        msg = f"dynamo._upsert: concurrent writes for {visit.id}"
        raise PortError(msg)

    async def _write_item(self, visit: Visit, condition: str, expected: int | None) -> bool:
        """Conditional PutItem for one visit plus its pointer; False on conflict."""

        def put() -> bool:
            item = {
                **_key(_visit_pk(visit.house_id), _visit_sk(visit.start_ms, visit.id)),
                "body": {"S": dumps_visit(visit)},
                "version": {"N": str(visit.version)},
            }
            try:
                if expected is not None:
                    self._client.put_item(
                        TableName=self._table,
                        Item=item,
                        ConditionExpression=condition,
                        ExpressionAttributeNames={"#v": "version"},
                        ExpressionAttributeValues={":expected": {"N": str(expected)}},
                    )
                else:
                    self._client.put_item(
                        TableName=self._table,
                        Item=item,
                        ConditionExpression=condition,
                    )
                self._client.put_item(
                    TableName=self._table,
                    Item={
                        **_key(_pointer_pk(visit.id), "META"),
                        "house_id": {"S": visit.house_id},
                        "start_ms": {"N": str(visit.start_ms)},
                    },
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    return False
                raise aws_port_error("dynamo", "PutItem", exc) from exc
            return True

        return await asyncio.to_thread(put)

    async def _read(self, visit_id: str) -> Visit | None:
        """Pointer -> visit item; None when absent."""
        pointer = await self._call(
            "get_pointer",
            {"visit_id": visit_id},
            lambda: self._get_item(_pointer_pk(visit_id), "META"),
            _ITEM,
        )
        if pointer is None:
            return None
        item = await self._call(
            "get_visit",
            {"visit_id": visit_id},
            lambda: self._get_item(
                _visit_pk(pointer["house_id"]["S"]),
                _visit_sk(int(pointer["start_ms"]["N"]), visit_id),
            ),
            _ITEM,
        )
        if item is None or "body" not in item:
            return None
        return loads_visit(item["body"]["S"])

    async def _get_item(self, pk: str, sk: str) -> dict[str, Any] | None:
        def get() -> dict[str, Any] | None:
            try:
                out = self._client.get_item(TableName=self._table, Key=_key(pk, sk))
            except ClientError as exc:
                raise aws_port_error("dynamo", "GetItem", exc) from exc
            item = out.get("Item")
            return dict(item) if item is not None else None

        return await asyncio.to_thread(get)

    async def visits_between(self, house_id: str, start_ms: int, end_ms: int) -> list[Visit]:
        def scan() -> list[Visit]:
            # SK BETWEEN bounds; end_ms exclusive, so cap the hi key below it.
            lo = _visit_sk(start_ms, "")
            hi = _visit_sk(end_ms, "")
            items: list[dict[str, Any]] = []
            kwargs: dict[str, Any] = {
                "TableName": self._table,
                "KeyConditionExpression": "#pk = :pk AND #sk BETWEEN :lo AND :hi",
                "ExpressionAttributeNames": {"#pk": "PK", "#sk": "SK"},
                "ExpressionAttributeValues": {
                    ":pk": {"S": _visit_pk(house_id)},
                    ":lo": {"S": lo},
                    ":hi": {"S": hi},
                },
            }
            while True:
                try:
                    page = self._client.query(**kwargs)
                except ClientError as exc:
                    raise aws_port_error("dynamo", "Query", exc) from exc
                items.extend(page.get("Items", []))
                last = page.get("LastEvaluatedKey")
                if last is None:
                    break
                kwargs["ExclusiveStartKey"] = last
            return [loads_visit(item["body"]["S"]) for item in items]

        return await self._call(
            "visits_between",
            {"house_id": house_id, "start_ms": start_ms, "end_ms": end_ms},
            lambda: asyncio.to_thread(scan),
            _VISIT_LIST,
        )

    async def get_visit(self, visit_id: str) -> Visit | None:
        return await self._call(
            "read_visit",
            {"visit_id": visit_id},
            lambda: self._read(visit_id),
            _OPT_VISIT,
        )

    async def claim(self, visit_id: str, resident_id: str) -> Visit | None:
        for _ in range(_MAX_WRITE_ATTEMPTS):
            stored = await self._read(visit_id)
            if stored is None:
                return None
            updated = replace(stored, claimed_by=resident_id, version=stored.version + 1)
            if await self._write_item(updated, "#v = :expected", stored.version):
                await self.bump_version(stored.house_id)
                return updated
        msg = f"dynamo.claim: concurrent writes for {visit_id}"
        raise PortError(msg)

    async def house_version(self, house_id: str) -> int:
        item = await self._get_item(_visit_pk(house_id), "VERSION")
        if item is None or "version" not in item:
            return 0
        return int(item["version"]["N"])

    async def bump_version(self, house_id: str) -> int:
        def update() -> int:
            try:
                out = self._client.update_item(
                    TableName=self._table,
                    Key=_key(_visit_pk(house_id), "VERSION"),
                    UpdateExpression="ADD #v :one",
                    ExpressionAttributeNames={"#v": "version"},
                    ExpressionAttributeValues={":one": {"N": "1"}},
                    ReturnValues="UPDATED_NEW",
                )
            except ClientError as exc:
                raise aws_port_error("dynamo", "UpdateItem", exc) from exc
            return int(out["Attributes"]["version"]["N"])

        return await asyncio.to_thread(update)

    async def get_cursor(self, device_id: str) -> int | None:
        item = await self._get_item(_device_pk(device_id), "CURSOR")
        if item is None or "ms" not in item:
            return None
        return int(item["ms"]["N"])

    async def set_cursor(self, device_id: str, ms: int) -> None:
        def put() -> None:
            try:
                self._client.put_item(
                    TableName=self._table,
                    Item={**_key(_device_pk(device_id), "CURSOR"), "ms": {"N": str(ms)}},
                )
            except ClientError as exc:
                raise aws_port_error("dynamo", "PutItem", exc) from exc

        await asyncio.to_thread(put)

    async def get_device_state(self, device_id: str) -> DeviceState | None:
        item = await self._get_item(_device_pk(device_id), "STATE")
        if item is None or "body" not in item:
            return None
        return loads_device_state(item["body"]["S"])

    async def set_device_state(self, device_id: str, state: DeviceState) -> None:
        def put() -> None:
            try:
                self._client.put_item(
                    TableName=self._table,
                    Item={
                        **_key(_device_pk(device_id), "STATE"),
                        "body": {"S": dumps_device_state(state)},
                    },
                )
            except ClientError as exc:
                raise aws_port_error("dynamo", "PutItem", exc) from exc

        await asyncio.to_thread(put)
