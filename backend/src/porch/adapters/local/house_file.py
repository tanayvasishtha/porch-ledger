"""Load a house fixture JSON file into the domain House."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from porch.domain import House, Point, Resident


class _ResidentFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    aliases: tuple[str, ...] = ()


class _HouseFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    timezone: str
    residents: tuple[_ResidentFile, ...]
    door_polygon: tuple[Point, ...] | None
    latitude: float
    longitude: float


def load_house(path: Path) -> House:
    """Parse the file and convert; pydantic reports bad fields in one message."""
    return loads_house(path.read_text(encoding="utf-8"))


def loads_house(text: str) -> House:
    """Parse house JSON text (packaged file or an S3 object body)."""
    parsed = _HouseFile.model_validate_json(text)
    return House(
        id=parsed.id,
        timezone=parsed.timezone,
        residents=tuple(
            Resident(id=r.id, display_name=r.display_name, aliases=r.aliases)
            for r in parsed.residents
        ),
        door_polygon=parsed.door_polygon,
        latitude=parsed.latitude,
        longitude=parsed.longitude,
    )
