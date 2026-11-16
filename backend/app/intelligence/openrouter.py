"""OpenRouter (OpenAI-compatible). The API key is sent only as a bearer header and is never logged."""

import logging
import random
import time

import httpx

from app.intelligence.base import GenerationResult, LLMProvider, Message, ModelInfo, ProviderHealth
from app.intelligence.errors import (
    NotConfigured,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)

log = logging.getLogger(__name__)


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(
        self,
        model: str,
        *,
        api_key: str,
        base_url: str,
        timeout_s: float,
        max_tokens: int,
        temperature: float,
        max_retries: int = 2,
        client: httpx.Client | None = None,
        **kw: object,
    ) -> None:
        super().__init__(model, timeout_s=timeout_s, max_tokens=max_tokens, temperature=temperature, **kw)  # type: ignore[arg-type]
        self._key, self._base, self._retries = api_key, base_url.rstrip("/"), max_retries
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=10.0))

    def _headers(self) -> dict[str, str]:
        if not self._key:
            raise NotConfigured("OPENROUTER_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {self._key}",
            "X-Title": "AeroSecurity AI",
            "Content-Type": "application/json",
        }

    def _send(self, method: str, url: str, json: object | None) -> httpx.Response:
        """One HTTP call with a WALL-CLOCK deadline. httpx timeouts are per read, and OpenRouter may trickle
        keep-alive bytes for minutes, so the body is streamed and the total elapsed time is enforced here."""
        deadline = time.monotonic() + self.timeout_s
        with self._client.stream(method, url, headers=self._headers(), json=json) as r:
            chunks: list[bytes] = []
            for chunk in r.iter_bytes():
                chunks.append(chunk)
                if time.monotonic() > deadline:
                    raise httpx.ReadTimeout("overall deadline exceeded")
            return httpx.Response(r.status_code, headers=r.headers, content=b"".join(chunks))

    def _request(self, method: str, path: str, *, json: object | None = None) -> httpx.Response:
        for attempt in range(self._retries + 1):
            try:
                resp = self._send(method, f"{self._base}{path}", json)
            except httpx.TimeoutException as exc:
                if attempt == self._retries:
                    raise ProviderTimeout("OpenRouter request timed out") from exc
            except httpx.TransportError as exc:
                if attempt == self._retries:
                    raise ProviderUnavailable("OpenRouter is unreachable") from exc
            else:
                if resp.status_code in (401, 403):
                    raise ProviderAuthError("OpenRouter rejected the API key")
                if resp.status_code == 402:
                    raise ProviderAuthError("OpenRouter credit/quota exhausted for this key")
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt == self._retries:
                        if resp.status_code == 429:
                            raise ProviderRateLimited(
                                "OpenRouter rate limit reached; try again shortly or choose another model"
                            )
                        raise ProviderUnavailable(f"OpenRouter error (HTTP {resp.status_code})")
                elif resp.status_code >= 400:
                    raise ProviderBadRequest(
                        f"OpenRouter rejected the request (HTTP {resp.status_code}): {_err(resp)}"
                    )
                else:
                    return resp
            delay = min(2.0**attempt, 20.0) + random.uniform(0, 0.5)  # noqa: S311  # nosec B311 - jitter
            log.warning("OpenRouter transient failure; retrying in %.1fs", delay)
            self._sleep(delay)
        raise ProviderUnavailable("OpenRouter unavailable")  # pragma: no cover

    def _complete(self, messages: list[Message], *, json_mode: bool) -> GenerationResult:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        t0 = time.monotonic()
        for attempt in (1, 2):
            resp = self._request("POST", "/chat/completions", json=payload)
            try:
                data = resp.json()
                text = data["choices"][0]["message"]["content"] or ""
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise ProviderBadRequest("OpenRouter returned an unexpected response shape") from exc
            if text.strip():
                break
            if data["choices"][0].get("finish_reason") == "length":
                # Reasoning models can spend the whole budget thinking and never answer. Retrying cannot help.
                raise ProviderBadRequest(
                    "the model used its whole output-token budget on internal reasoning and returned no "
                    "answer; raise AI_MAX_OUTPUT_TOKENS or choose a non-reasoning model"
                )
            if attempt == 2:  # overloaded free providers sometimes return an empty completion once
                raise ProviderUnavailable("model returned an empty response twice")
            self._sleep(2.0)
        u = data.get("usage") or {}
        return GenerationResult(
            text,
            str(data.get("model", self.model)),
            u.get("prompt_tokens"),
            u.get("completion_tokens"),
            int((time.monotonic() - t0) * 1000),
        )

    def health_check(self) -> ProviderHealth:
        if not self._key:
            return ProviderHealth(False, "API key not configured")
        t0 = time.monotonic()
        try:
            r = self._client.get(f"{self._base}/auth/key", headers=self._headers(), timeout=10.0)
        except httpx.HTTPError:
            return ProviderHealth(False, "unreachable")
        ms = int((time.monotonic() - t0) * 1000)
        if r.status_code in (401, 403):
            return ProviderHealth(False, "API key rejected", ms)
        return ProviderHealth(
            r.status_code == 200, "ok" if r.status_code == 200 else f"HTTP {r.status_code}", ms
        )

    def list_models(self) -> list[ModelInfo]:
        try:
            r = self._client.get(f"{self._base}/models", timeout=15.0)  # public endpoint; no key needed
            items = r.json()["data"]
        except (httpx.HTTPError, ValueError, KeyError):
            return []
        out = []
        for m in items:
            params = m.get("supported_parameters") or []
            if "response_format" not in params:
                continue  # we need JSON mode
            p = m.get("pricing") or {}
            out.append(
                ModelInfo(
                    m["id"],
                    context_length=m.get("context_length"),
                    free=str(p.get("prompt")) == "0" and str(p.get("completion")) == "0",
                )
            )
        return sorted(out, key=lambda x: x.id)


def _err(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("error", {}).get("message", ""))[:160]
    except ValueError:
        return ""
