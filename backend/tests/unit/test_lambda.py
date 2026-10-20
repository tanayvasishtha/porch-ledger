"""Lambda entry points: SSM caching, cloud context, worker skips and runs."""

import asyncio
import io
from pathlib import Path
from typing import Any, cast

import httpx2
import pytest
from botocore.exceptions import ClientError
from types_boto3_s3 import S3Client
from types_boto3_ssm import SSMClient

from porch.adapters.aws.clients import AwsClients, build_clients
from porch.aws_lambda import SsmSecrets, _ingest_once, build_cloud_context
from porch.config import AwsSettings, Settings
from tests.helpers import DEMO_FIXTURE, FakeClock, FakeDynamoClient
from tests.unit.test_aws_adapters import _client


class FakeSsm:
    """SSM GetParameter over a dict; counts calls so caching is testable."""

    def __init__(self, params: dict[str, str]) -> None:
        self.params = params
        self.calls = 0

    def get_parameter(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        name = kwargs["Name"]
        if name not in self.params:
            raise ClientError(
                {"Error": {"Code": "ParameterNotFound", "Message": name}},
                "GetParameter",
            )
        return {"Parameter": {"Name": name, "Value": self.params[name]}}


class FakeS3:
    """get_object over an in-memory bucket."""

    def __init__(self, objects: dict[tuple[str, str], bytes]) -> None:
        self.objects = objects

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        return {"Body": io.BytesIO(self.objects[(kwargs["Bucket"], kwargs["Key"])])}


def mkclients(tmp_path: Path, ssm: FakeSsm, s3: FakeS3 | None = None) -> AwsClients:
    return AwsClients(
        s3=cast(S3Client, s3 or FakeS3({})),
        dynamodb=cast(Any, FakeDynamoClient()),
        ssm=cast(SSMClient, ssm),
        rekognition=cast(Any, _client("rekognition")),
        polly=cast(Any, _client("polly")),
        bedrock=cast(Any, _client("bedrock-runtime")),
    )


def test_ssm_cache_hit_and_ttl(tmp_path: Path) -> None:
    ssm = FakeSsm({"/porch/ring/access_token": "tok-1"})
    clock = FakeClock(0)
    cache = SsmSecrets(cast(SSMClient, ssm), clock)
    assert cache.get("/porch/ring/access_token", ttl_s=60) == "tok-1"
    assert cache.get("/porch/ring/access_token", ttl_s=60) == "tok-1"
    assert ssm.calls == 1
    clock.current += 61_000
    assert cache.get("/porch/ring/access_token", ttl_s=60) == "tok-1"
    assert ssm.calls == 2


def test_ssm_cache_no_ttl_lives_for_cold_start(tmp_path: Path) -> None:
    ssm = FakeSsm({"/porch/house/demo/key_sha256": "abc"})
    clock = FakeClock(0)
    cache = SsmSecrets(cast(SSMClient, ssm), clock)
    assert cache.get("/porch/house/demo/key_sha256") == "abc"
    clock.current += 10**9
    assert cache.get("/porch/house/demo/key_sha256") == "abc"
    assert ssm.calls == 1


def test_missing_token_skips(tmp_path: Path) -> None:
    """No Ring token in SSM: a clear skip, not a failed invocation."""
    ssm = FakeSsm({})
    clients = mkclients(tmp_path, ssm)
    secrets = SsmSecrets(cast(SSMClient, ssm), FakeClock(0))
    out = asyncio.run(_ingest_once(Settings(), clients, FakeClock(0), secrets))
    assert out == {"skipped": "no_ring_token"}


def test_worker_polls_first_device_and_stores_cursor(tmp_path: Path) -> None:
    """Empty history: report zeros, cursor untouched, device discovered."""
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if request.url.path == "/v1/devices":
            return httpx2.Response(200, json={"data": [{"id": "dev-9"}]})
        return httpx2.Response(200, json={"data": [], "links": {}})

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    house_file = tmp_path / "house.json"
    house_file.write_text(DEMO_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    settings = Settings(api=Settings().api.model_copy(update={"house_file": house_file}))
    ssm = FakeSsm({"/porch/ring/access_token": "tok"})
    clients = mkclients(tmp_path, ssm)
    out = asyncio.run(
        _ingest_once(
            settings,
            clients,
            FakeClock(0),
            SsmSecrets(cast(SSMClient, ssm), FakeClock(0)),
            http=http,
        )
    )
    assert out == {"events": 0, "snapshots": 0, "visits_closed": 0, "pending": 0}
    assert requests[0].url.path == "/v1/devices"
    assert "/v1/history/devices/dev-9/events" in str(requests[1].url)


def test_cloud_context_reads_secrets(tmp_path: Path) -> None:
    """House key hash lands on settings; webhook secret seeds the env var."""
    house_json = DEMO_FIXTURE.read_bytes()
    s3 = FakeS3({("bkt", "house.json"): house_json})
    ssm = FakeSsm(
        {
            "/porch/house/demo/key_sha256": "deadbeef",
            "/porch/ring/webhook_secret": "whsec",
        }
    )
    api = Settings().api.model_copy(update={"house_file": Path("s3://bkt/house.json")})
    settings = Settings().model_copy(update={"api": api})
    ctx = build_cloud_context(settings, mkclients(tmp_path, ssm, s3))
    assert ctx.settings.api.house_key_sha256 == "deadbeef"
    assert ctx.house.id == "demo"
    assert isinstance(ctx.settings.api.house_file, Path)


def test_house_from_s3_roundtrip(tmp_path: Path) -> None:
    s3 = FakeS3({("bkt", "k.json"): DEMO_FIXTURE.read_bytes()})
    api = Settings().api.model_copy(update={"house_file": Path("s3://bkt/k.json")})
    settings = Settings().model_copy(update={"api": api})
    ssm = FakeSsm({"/porch/house/demo/key_sha256": "x"})
    ctx = build_cloud_context(settings, mkclients(tmp_path, ssm, s3))
    assert ctx.house.residents


def test_build_clients_uses_bedrock_region(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(aws=AwsSettings(region="ap-southeast-2", bedrock_region="us-east-1"))
    clients = build_clients(settings)
    assert clients.bedrock.meta.region_name == "us-east-1"
    assert clients.rekognition.meta.region_name == "ap-southeast-2"
    assert clients.s3.meta.region_name == "ap-southeast-2"
