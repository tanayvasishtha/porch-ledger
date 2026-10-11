"""Adapters: one per external system, each behind a Protocol port."""

from porch.adapters.cassette import Cassette, CassetteCorruptError, CassetteMissError
from porch.adapters.codec import dumps_visit, loads_visit

__all__ = [
    "Cassette",
    "CassetteCorruptError",
    "CassetteMissError",
    "dumps_visit",
    "loads_visit",
]
