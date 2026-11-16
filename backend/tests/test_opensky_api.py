"""Provider adapter tests against httpx.MockTransport (no network). Payload layout follows OpenSky docs."""

from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.ingestion.opensky_api import OpenSkyApiProvider, ProviderError
from app.ingestion.schema import NormalizedObservation, Rejection

STATE = [
    "4b1806",
    "SWR32F  ",
    "Switzerland",
    1794827049,
    1794827050,
    5.9974,
    46.1626,
    1973.58,
    False,
    109.87,
    225.76,
    14.63,
    None,
    2019.3,
    "5723",
    False,
    0,
]
TOKEN_URL = "https://auth.example/token"


def settings(**kw: SecretStr) -> Settings:
    return Settings.model_validate(
        {
            "database_url": "postgresql+psycopg://u:p@h/d",
            "opensky_token_url": TOKEN_URL,
            "opensky_min_interval_s": 10.0,
            "opensky_max_retries": 3,
            **kw,
        }
    )


class Env:
    def __init__(self, handler: httpx.MockTransport) -> None:
        self.now, self.sleeps = 0.0, []  # type: float, list[float]
        self.client = httpx.Client(transport=handler)

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s

    def provider(self, s: Settings) -> OpenSkyApiProvider:
        return OpenSkyApiProvider(s, client=self.client, sleep=self.sleep, clock=lambda: self.now)


def mk(handler: Callable[[httpx.Request], httpx.Response]) -> Env:
    return Env(httpx.MockTransport(handler))


def test_parses_states_and_flags_malformed() -> None:
    env = mk(lambda r: httpx.Response(200, json={"time": 1794827051, "states": [STATE, ["short"]]}))
    out = list(env.provider(settings()).fetch())
    o = out[0]
    assert isinstance(o, NormalizedObservation) and o.icao24 == "4b1806" and o.lat == 46.1626
    assert o.velocity_ms == 109.87 and o.geo_altitude_m == 2019.3 and o.squawk == "5723"
    assert out[1] == Rejection("malformed_state", 1)


def test_null_states_is_empty_not_error() -> None:
    env = mk(lambda r: httpx.Response(200, json={"time": 1, "states": None}))
    assert list(env.provider(settings()).fetch()) == []


def test_oauth_token_cached_then_refreshed_on_expiry() -> None:
    calls = {"token": 0}

    def handler(r: httpx.Request) -> httpx.Response:
        if str(r.url) == TOKEN_URL:
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": f"tok{calls['token']}", "expires_in": 100})
        assert r.headers["authorization"] == f"Bearer tok{calls['token']}"
        return httpx.Response(200, json={"time": 1794827051, "states": []})

    env = mk(handler)
    p = env.provider(settings(opensky_client_id=SecretStr("id"), opensky_client_secret=SecretStr("sec")))
    list(p.fetch())
    list(p.fetch())
    assert calls["token"] == 1
    env.now += 200  # past expiry
    list(p.fetch())
    assert calls["token"] == 2


def test_401_triggers_single_token_refresh() -> None:
    seq = iter([401, 200])
    tokens = {"n": 0}

    def handler(r: httpx.Request) -> httpx.Response:
        if str(r.url) == TOKEN_URL:
            tokens["n"] += 1
            return httpx.Response(200, json={"access_token": "t", "expires_in": 1000})
        return httpx.Response(next(seq), json={"time": 1, "states": []})

    env = mk(handler)
    list(
        env.provider(settings(opensky_client_id=SecretStr("i"), opensky_client_secret=SecretStr("s"))).fetch()
    )
    assert tokens["n"] == 2


def test_429_honours_retry_after_then_succeeds() -> None:
    seq = iter(
        [
            httpx.Response(429, headers={"X-Rate-Limit-Retry-After-Seconds": "42"}),
            httpx.Response(200, json={"time": 1, "states": []}),
        ]
    )
    env = mk(lambda r: next(seq))
    list(env.provider(settings()).fetch())
    assert 42.0 in env.sleeps


def test_exponential_backoff_then_gives_up_without_leaking_secrets() -> None:
    times: list[float] = []
    holder: dict[str, Env] = {}

    def handler(r: httpx.Request) -> httpx.Response:
        times.append(holder["env"].now)
        return httpx.Response(503)

    env = holder["env"] = mk(handler)
    p = env.provider(settings(opensky_client_secret=SecretStr("TOPSECRET")))
    with pytest.raises(ProviderError) as ei:
        list(p.fetch())
    assert "TOPSECRET" not in str(ei.value)
    assert len(times) == 4  # 1 try + 3 retries
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    assert all(g >= 10.0 - 1e-9 for g in gaps)  # min interval always respected
    assert gaps[0] <= gaps[1] <= gaps[2]  # waits never shrink


def test_min_interval_enforced_between_polls() -> None:
    env = mk(lambda r: httpx.Response(200, json={"time": 1, "states": []}))
    p = env.provider(settings())
    list(p.fetch())
    list(p.fetch())
    assert env.sleeps and env.sleeps[0] == pytest.approx(10.0)


def test_non_retryable_status_fails_fast() -> None:
    env = mk(lambda r: httpx.Response(404))
    with pytest.raises(ProviderError, match="HTTP 404"):
        list(env.provider(settings()).fetch())
    assert env.sleeps == []


def test_bbox_sent_as_query_params() -> None:
    seen: dict[str, str] = {}

    def handler(r: httpx.Request) -> httpx.Response:
        seen.update(r.url.params)
        return httpx.Response(200, json={"time": 1, "states": []})

    env = mk(handler)
    list(
        OpenSkyApiProvider(
            settings(), bbox=(45, 5, 48, 11), client=env.client, sleep=env.sleep, clock=lambda: env.now
        ).fetch()
    )
    assert seen == {"lamin": "45", "lomin": "5", "lamax": "48", "lomax": "11"}
