"""Open-Meteo rain outlook behind the Weather port.

One hourly forecast call, cached per (lat, lon, hours) for
weather.cache_ttl_s using the injected Clock. Network and HTTP failures
become PortError; a response without hourly data reads as None.
"""

from __future__ import annotations

from datetime import datetime

import httpx2
from pydantic import TypeAdapter

from porch.adapters.cassette import Cassette, JsonValue
from porch.config import Settings
from porch.domain import House, RainRisk
from porch.ports import Clock, PortError, Weather

_ADAPTER = "openmeteo_forecast"
_VERSION = 1
_PAYLOAD = TypeAdapter(dict[str, JsonValue])
_NOON_HOUR = 12


class OpenMeteoWeather(Weather):
    def __init__(
        self,
        house: House,
        settings: Settings,
        clock: Clock,
        cassette: Cassette,
        client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._house = house
        self._base_url = settings.weather.base_url
        self._timeout_s = settings.weather.timeout_s
        self._ttl_ms = settings.weather.cache_ttl_s * 1000
        self._clock = clock
        self._cassette = cassette
        # Injected in tests (MockTransport); None builds a client per call.
        self._client = client
        self._cache: dict[tuple[float, float, int], tuple[int, RainRisk | None]] = {}

    async def max_rain_probability_pct(self, hours: int) -> RainRisk | None:
        key = (self._house.latitude, self._house.longitude, hours)
        cached = self._cache.get(key)
        now_ms = self._clock.now_ms()
        if cached is not None and now_ms - cached[0] < self._ttl_ms:
            return cached[1]
        request: dict[str, JsonValue] = {
            "latitude": self._house.latitude,
            "longitude": self._house.longitude,
            "timezone": self._house.timezone,
            "hours": hours,
            "base_url": self._base_url,
        }
        payload = await self._cassette.call(
            _ADAPTER, _VERSION, request, lambda: self._fetch(hours), _PAYLOAD
        )
        risk = _rain_risk(payload)
        self._cache[key] = (now_ms, risk)
        return risk

    async def _fetch(self, hours: int) -> dict[str, JsonValue]:
        params: dict[str, str | int | float] = {
            "latitude": self._house.latitude,
            "longitude": self._house.longitude,
            "hourly": "precipitation_probability",
            "forecast_hours": hours,
            "timezone": self._house.timezone,
        }
        try:
            if self._client is not None:
                response = await self._client.get(self._base_url, params=params)
            else:
                async with httpx2.AsyncClient(timeout=self._timeout_s) as client:
                    response = await client.get(self._base_url, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx2.HTTPError, ValueError) as exc:
            msg = f"openmeteo.forecast: {type(exc).__name__}"
            raise PortError(msg) from exc
        if not isinstance(payload, dict):
            msg = "openmeteo.forecast: non-object response"
            raise PortError(msg)
        return payload


def _rain_risk(payload: dict[str, JsonValue]) -> RainRisk | None:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        return None
    probabilities = hourly.get("precipitation_probability")
    times = hourly.get("time")
    if not isinstance(probabilities, list) or not isinstance(times, list):
        return None
    pairs = [
        (time, probability)
        for time, probability in zip(times, probabilities, strict=False)
        if isinstance(time, str) and isinstance(probability, int | float)
    ]
    if not pairs:
        return None
    best = max(probability for _, probability in pairs)
    first = next(time for time, probability in pairs if probability == best)
    return RainRisk(probability_pct=int(best), by_local_time=_hour_label(first))


def _hour_label(iso_local: str) -> str:
    """Render an ISO local hour the way copy.py renders the clock."""
    try:
        moment = datetime.fromisoformat(iso_local)
    except ValueError:
        return iso_local
    hour = moment.hour % _NOON_HOUR or _NOON_HOUR
    period = "am" if moment.hour < _NOON_HOUR else "pm"
    return f"{hour}:{moment.minute:02d} {period}"
