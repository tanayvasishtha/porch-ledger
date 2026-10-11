"""AWS Lambda entry points: cloud context builder and the ingest worker.

The API runs under the Lambda Web Adapter (infra/run.sh starts uvicorn
with porch.cli:cloud_app); this module builds the same AppContext against
DynamoDB and S3 instead of SQLite and the filesystem. The ingest worker
runs on a schedule: Ring token, house file and secrets come from SSM/S3
at cold start.
"""

import asyncio
import dataclasses
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx2
from botocore.exceptions import BotoCoreError, ClientError
from strands.models import BedrockModel
from types_boto3_s3 import S3Client
from types_boto3_ssm import SSMClient

from porch.adapters.aws import build_live_ports
from porch.adapters.aws.clients import AwsClients, aws_port_error, build_clients
from porch.adapters.aws.dynamo_repo import DynamoRepository
from porch.adapters.aws.s3_media import S3MediaStore
from porch.adapters.cassette import Cassette
from porch.adapters.local.house_file import loads_house
from porch.adapters.ring.client import RingClient
from porch.adapters.ring.playground import RingMediaFetcher, RingSource
from porch.api.deps import AppContext
from porch.clock import SystemClock
from porch.config import Settings
from porch.domain import House
from porch.pipeline.agent import PorchClerk
from porch.pipeline.ingest import IngestConfig, IngestPorts, IngestService
from porch.ports import Clock

logger = logging.getLogger(__name__)

_RING_TOKEN_PARAM = "/porch/ring/access_token"
_WEBHOOK_SECRET_PARAM = "/porch/ring/webhook_secret"
_KEY_PARAM = "/porch/house/{house_id}/key_sha256"
# Short enough that a rotated Ring token is picked up between invocations.
_TOKEN_TTL_S = 60
_LIVE_CASSETTE = Cassette(Path.cwd(), "live")


class SsmSecrets:
    """SSM parameter reads with a small cache; None means absent."""

    def __init__(self, client: SSMClient, clock: Clock) -> None:
        self._client = client
        self._clock = clock
        self._cache: dict[str, tuple[str | None, int]] = {}

    def get(self, name: str, ttl_s: int | None = None) -> str | None:
        """Read a SecureString; ttl_s=None caches for the cold start's life."""
        now = self._clock.now_ms()
        hit = self._cache.get(name)
        if hit is not None and now < hit[1]:
            return hit[0]
        try:
            out = self._client.get_parameter(Name=name, WithDecryption=True)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ParameterNotFound":
                raise aws_port_error("ssm", "GetParameter", exc) from exc
            value = None
        else:
            value = out.get("Parameter", {}).get("Value")
        expiry = now + ttl_s * 1000 if ttl_s is not None else now + 2**60
        self._cache[name] = (value, expiry)
        return value


def _load_house(settings: Settings, s3: S3Client) -> House:
    r"""House JSON from an s3:// URI or a packaged file path.

    Path normalizes s3:// to s3:\ on Windows, so match loosely.
    """
    raw = str(settings.api.house_file).replace("\\", "/")
    if raw.startswith("s3:"):
        rest = raw.removeprefix("s3:").lstrip("/")
        bucket, _, key = rest.partition("/")
        try:
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        except (ClientError, BotoCoreError) as exc:
            raise aws_port_error("s3", "GetObject", exc) from exc
        return loads_house(body.decode("utf-8"))
    return loads_house(Path(raw).read_text(encoding="utf-8"))


def build_cloud_context(settings: Settings, clients: AwsClients | None = None) -> AppContext:
    """AppContext backed by DynamoDB + S3; secrets come from SSM once."""
    clients = clients or build_clients(settings)
    clock = SystemClock()
    house = _load_house(settings, clients.s3)
    ssm = SsmSecrets(clients.ssm, clock)
    key_sha = ssm.get(_KEY_PARAM.format(house_id=house.id))
    api = settings.api.model_copy(update={"house_key_sha256": key_sha})
    settings = settings.model_copy(update={"api": api})
    # The webhook route resolves its secret from the env var named in
    # settings; seed it from SSM so the same lookup works in Lambda.
    secret = ssm.get(_WEBHOOK_SECRET_PARAM)
    if secret is not None:
        os.environ.setdefault(settings.ring.webhook_secret_env, secret)
    return AppContext(
        settings=settings,
        repo=DynamoRepository(clients.dynamodb, settings.aws.table_name),
        media=S3MediaStore(clients.s3, settings, _LIVE_CASSETTE),
        house=house,
        clock=clock,
    )


async def _ingest_once(
    settings: Settings,
    clients: AwsClients,
    clock: Clock,
    ssm: SsmSecrets,
    http: httpx2.AsyncClient | None = None,
) -> dict[str, Any]:
    """One worker run; testable with fakes since all clients are injected."""
    token = ssm.get(_RING_TOKEN_PARAM, ttl_s=_TOKEN_TTL_S)
    if token is None:
        logger.warning("no Ring access token at %s; skipping", _RING_TOKEN_PARAM)
        return {"skipped": "no_ring_token"}
    house = _load_house(settings, clients.s3)
    repo = DynamoRepository(clients.dynamodb, settings.aws.table_name)
    enrich, labeler, media = build_live_ports(
        settings, house, clock, _LIVE_CASSETTE, clients=clients
    )
    ring = RingClient(settings, token, client=http)
    device_id = settings.ring.device_id
    if not device_id:
        devices = await ring.devices()
        if not devices:
            logger.warning("Ring account returned no devices; skipping")
            return {"skipped": "no_devices"}
        device_id = str(devices[0]["id"])
    clerk = (
        PorchClerk(
            model=BedrockModel(
                model_id=settings.agent.model_id,
                region_name=settings.aws.region,
            ),
            ports=enrich,
            house=house,
            settings=settings,
            clock=clock,
        )
        if settings.agent.enabled
        else None
    )
    service = IngestService(
        IngestPorts(
            source=RingSource(ring, device_id, repo, _LIVE_CASSETTE),
            fetcher=RingMediaFetcher(ring, device_id, settings, _LIVE_CASSETTE, clock),
            media=media,
            labeler=labeler,
            enrich=enrich,
            repo=repo,
        ),
        IngestConfig(
            house=house,
            settings=settings,
            clock=clock,
            device_id=device_id,
        ),
        clerk=clerk,
    )
    report = await service.run_once()
    logger.info("ingest %s", json.dumps(dataclasses.asdict(report)))
    return dataclasses.asdict(report)


def ingest_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge entry point: one ingest sweep for the configured device."""
    settings = Settings()
    clock = SystemClock()
    clients = build_clients(settings)
    ssm = SsmSecrets(clients.ssm, clock)
    return asyncio.run(_ingest_once(settings, clients, clock, ssm))
