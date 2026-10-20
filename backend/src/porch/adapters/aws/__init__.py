"""AWS adapters plus the one wiring point for the live worker."""

from porch.adapters.aws.clients import AwsClients, build_clients
from porch.adapters.aws.nova import NovaDescriber
from porch.adapters.aws.polly import PollySpeech
from porch.adapters.aws.rekognition import RekognitionLabeler
from porch.adapters.aws.rekognition_text import RekognitionTextReader
from porch.adapters.aws.s3_media import S3MediaStore
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
    "RekognitionTextReader",
    "S3MediaStore",
    "build_clients",
    "build_live_ports",
]


def build_live_ports(
    settings: Settings,
    house: House,
    clock: Clock,
    cassette: Cassette,
    clients: AwsClients | None = None,
) -> tuple[EnrichPorts, RekognitionLabeler, S3MediaStore]:
    """Wire the real AWS ports for the worker: one client set, one cassette."""
    clients = clients or build_clients(settings)
    media = S3MediaStore(clients.s3, settings, cassette)
    labeler = RekognitionLabeler(clients.rekognition, settings, cassette)
    enrich = EnrichPorts(
        media=media,
        reader=RekognitionTextReader(clients.rekognition, settings, cassette),
        describer=NovaDescriber(clients.bedrock, media, settings, cassette),
        weather=OpenMeteoWeather(house, settings, clock, cassette),
    )
    return enrich, labeler, media
