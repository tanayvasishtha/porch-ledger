"""Typed boto3 clients, built once from Settings.

One factory builds every client with the same botocore Config (timeouts
and standard retry mode). Tests hand in Stubber-wrapped clients instead
of calling the factory.
"""

from __future__ import annotations

from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from types_boto3_bedrock_runtime import BedrockRuntimeClient
from types_boto3_dynamodb.client import DynamoDBClient
from types_boto3_polly import PollyClient
from types_boto3_rekognition import RekognitionClient
from types_boto3_s3 import S3Client
from types_boto3_ssm.client import SSMClient
from types_boto3_textract import TextractClient

from porch.config import Settings
from porch.ports import PortError

_TIMEOUT_S = 10
_MAX_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class AwsClients:
    """Every service client the adapters need, in one place."""

    s3: S3Client
    dynamodb: DynamoDBClient
    ssm: SSMClient
    rekognition: RekognitionClient
    textract: TextractClient
    polly: PollyClient
    bedrock: BedrockRuntimeClient


def build_clients(settings: Settings) -> AwsClients:
    config = Config(
        connect_timeout=_TIMEOUT_S,
        read_timeout=_TIMEOUT_S,
        retries={"max_attempts": _MAX_ATTEMPTS, "mode": "standard"},
    )
    region = settings.aws.region
    return AwsClients(
        s3=boto3.client("s3", region_name=region, config=config),
        dynamodb=boto3.client("dynamodb", region_name=region, config=config),
        ssm=boto3.client("ssm", region_name=region, config=config),
        rekognition=boto3.client("rekognition", region_name=region, config=config),
        textract=boto3.client("textract", region_name=region, config=config),
        polly=boto3.client("polly", region_name=region, config=config),
        bedrock=boto3.client("bedrock-runtime", region_name=region, config=config),
    )


def aws_port_error(service: str, operation: str, exc: ClientError | BotoCoreError) -> PortError:
    """Translate a boto failure into PortError naming service, op and code."""
    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        code = error.get("Code", "ClientError") if isinstance(error, dict) else "ClientError"
    else:
        code = type(exc).__name__
    return PortError(f"{service}.{operation}: {code}")
