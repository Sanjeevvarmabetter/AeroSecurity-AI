"""OpenSky REST adapter (states/all) with OAuth2 client credentials, rate limiting and backoff.

DISABLED BY DEFAULT: OpenSky's terms restrict operational/commercial use. The data_sources row is created
with enabled=false and ingestion refuses to run until an operator enables it after confirming authorisation.
"""

import logging
import random
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from app.core.config import Settings
from app.ingestion.base import ObservationProvider
from app.ingestion.schema import NormalizedObservation, Rejection
from app.ingestion.validation import normalize

log = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 25 * 1024 * 1024
_TOKEN_MARGIN_S = 30.0


class ProviderError(Exception):
    """Provider call failed after retries. Message never contains credentials."""


class OpenSkyApiProvider(ObservationProvider):
    name = "opensky-api"
    kind = "api"
    terms_url = "https://opensky-network.org/about/terms-of-use"
    default_enabled = False

    def __init__(
        self,
        settings: Settings,
        *,
        bbox: tuple[float, float, float, float] | None = None,  # lamin, lomin, lamax, lomax
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.s = settings
        self.bbox = bbox
        self.client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0))
        self._sleep, self._clock = sleep, clock
        self._token: str | None = None
        self._token_expiry = 0.0
        self._last_request: float | None = None

    # -- auth ---------------------------------------------------------------------------------
    def _has_credentials(self) -> bool:
        return bool(
            self.s.opensky_client_id.get_secret_value() and self.s.opensky_client_secret.get_secret_value()
        )

    def _bearer(self) -> dict[str, str]:
        if not self._has_credentials():
            return {}  # anonymous access (lowest limits)
        if self._token is None or self._clock() >= self._token_expiry:
            self._refresh_token()
        return {"Authorization": f"Bearer {self._token}"}

    def _refresh_token(self) -> None:
        resp = self.client.post(
            self.s.opensky_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.s.opensky_client_id.get_secret_value(),
                "client_secret": self.s.opensky_client_secret.get_secret_value(),
            },
        )
        if resp.status_code != 200:
            raise ProviderError(f"token request failed (HTTP {resp.status_code})")
        body = resp.json()
        self._token = str(body["access_token"])
        self._token_expiry = self._clock() + float(body.get("expires_in", 300)) - _TOKEN_MARGIN_S

    # -- requests -----------------------------------------------------------------------------
    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self.s.opensky_min_interval_s - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._clock()

    def _get_states(self) -> dict[str, Any]:
        params: dict[str, float] = {}
        if self.bbox:
            params = dict(zip(("lamin", "lomin", "lamax", "lomax"), self.bbox, strict=True))
        refreshed = False
        for attempt in range(self.s.opensky_max_retries + 1):
            self._throttle()
            try:
                resp = self.client.get(
                    f"{self.s.opensky_api_base_url}/states/all", params=params, headers=self._bearer()
                )
            except httpx.TransportError as exc:
                log.warning("OpenSky transport error: %s", type(exc).__name__)
                delay = self._backoff(attempt, None)
            else:
                if resp.status_code == 200:
                    if len(resp.content) > MAX_RESPONSE_BYTES:
                        raise ProviderError("response too large")
                    data = resp.json()
                    if not isinstance(data, dict):
                        raise ProviderError("unexpected response shape")
                    return data
                if resp.status_code == 401 and self._has_credentials() and not refreshed:
                    self._token, refreshed = None, True  # token expired server-side; retry once
                    continue
                if resp.status_code not in (429, 500, 502, 503, 504):
                    raise ProviderError(f"unexpected HTTP {resp.status_code}")
                retry_after = resp.headers.get("X-Rate-Limit-Retry-After-Seconds") or resp.headers.get(
                    "Retry-After"
                )
                delay = self._backoff(attempt, retry_after)
                log.warning("OpenSky HTTP %s; retrying in %.1fs", resp.status_code, delay)
            if attempt < self.s.opensky_max_retries:
                self._sleep(delay)
        raise ProviderError("OpenSky unavailable after retries")

    @staticmethod
    def _backoff(attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), 900.0)
            except ValueError:
                pass
        return min(2.0**attempt, 300.0) + random.uniform(0, 1)  # noqa: S311  # nosec B311

    # -- normalisation ------------------------------------------------------------------------
    def fetch(self) -> Iterator[NormalizedObservation | Rejection]:
        data = self._get_states()
        response_time = data.get("time")
        for i, st in enumerate(data.get("states") or []):
            if not isinstance(st, list) or len(st) < 17:
                yield Rejection("malformed_state", i)
                continue
            yield normalize(
                {
                    "icao24": st[0],
                    "callsign": st[1],
                    "origin_country": st[2],
                    "observed_at": st[3] if st[3] is not None else (st[4] or response_time),
                    "last_contact": st[4],
                    "lon": st[5],
                    "lat": st[6],
                    "baro_altitude_m": st[7],
                    "on_ground": st[8],
                    "velocity_ms": st[9],
                    "heading_deg": st[10],
                    "vertical_rate_ms": st[11],
                    "geo_altitude_m": st[13],
                    "squawk": st[14],
                    "position_source": st[16],
                    "extra": {"spi": st[15], "response_time": response_time},
                },
                i,
            )
