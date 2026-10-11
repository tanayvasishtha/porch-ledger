"""AWS adapters plus the one wiring point for the live worker."""

from porch.adapters.aws.clients import AwsClients, build_clients
from porch.adapters.aws.nova import NovaDescriber
from porch.adapters.aws.polly import PollySpeech
from porch.adapters.aws.rekognition import RekognitionLabeler
from porch.adapters.aws.s3_media import S3MediaStore
from porch.adapters.aws.textract import TextractReader
from porch.adapters.cassette import Cassette
from porch.adapters.openmeteo import OpenMeteoWeather
from porch.config import Settings
from porch.domain import House
from porch.pipeline.enrich import EnrichPorts
from porch.ports import Clock

__all__ = [
    "AwsClients",
    "NovaDescriber",
    "PollySpeech",
    "RekognitionLabeler",
    "S3MediaStore",
    "TextractReader",
    "build_clients",
    "build_live_ports",
]


def build_live_ports(
    settings: Settings, house: House, clock: Clock, cassette: Cassette
) -> tuple[EnrichPorts, RekognitionLabeler, S3MediaStore]:
    """Wire the real AWS ports for the worker: one client set, one cassette."""
    clients = build_clients(settings)
    media = S3MediaStore(clients.s3, settings, cassette)
    labeler = RekognitionLabeler(clients.rekognition, settings, cassette)
    enrich = EnrichPorts(
        media=media,
        reader=TextractReader(clients.textract, settings, cassette),
        describer=NovaDescriber(clients.bedrock, media, settings, cassette),
        weather=OpenMeteoWeather(house, settings, clock, cassette),
    )
    return enrich, labeler, media
