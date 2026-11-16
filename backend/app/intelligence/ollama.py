"""Ollama (local). The base URL comes from configuration only, never from a request."""

import logging
import time

import httpx

from app.intelligence.base import GenerationResult, LLMProvider, Message, ModelInfo, ProviderHealth
from app.intelligence.errors import (
    NotConfigured,
    ProviderBadRequest,
    ProviderTimeout,
    ProviderUnavailable,
)

log = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        timeout_s: float,
        max_tokens: int,
        temperature: float,
        client: httpx.Client | None = None,
        **kw: object,
    ) -> None:
        super().__init__(model, timeout_s=timeout_s, max_tokens=max_tokens, temperature=temperature, **kw)  # type: ignore[arg-type]
        self._base = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=5.0))

    def _complete(self, messages: list[Message], *, json_mode: bool) -> GenerationResult:
        if not self.model:
            raise NotConfigured("OLLAMA_MODEL is not configured")
        payload: dict[str, object] = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        t0 = time.monotonic()
        try:
            resp = self._client.post(f"{self._base}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(
                "Ollama request timed out (a large local model may need a longer AI_TIMEOUT_S)"
            ) from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailable("Ollama is not reachable; is `ollama serve` running?") from exc
        if resp.status_code == 404:
            raise ProviderBadRequest(f"Ollama does not have model '{self.model}' (run `ollama pull`)")
        if resp.status_code >= 500:
            raise ProviderUnavailable(f"Ollama error (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise ProviderBadRequest(f"Ollama rejected the request (HTTP {resp.status_code})")
        try:
            data = resp.json()
            text = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderBadRequest("Ollama returned an unexpected response shape") from exc
        if not str(text).strip():
            raise ProviderBadRequest("model returned an empty response")
        return GenerationResult(
            text,
            str(data.get("model", self.model)),
            data.get("prompt_eval_count"),
            data.get("eval_count"),
            int((time.monotonic() - t0) * 1000),
        )

    def health_check(self) -> ProviderHealth:
        t0 = time.monotonic()
        try:
            r = self._client.get(f"{self._base}/api/tags", timeout=5.0)
        except httpx.HTTPError:
            return ProviderHealth(False, "not reachable")
        ms = int((time.monotonic() - t0) * 1000)
        return ProviderHealth(
            r.status_code == 200, "ok" if r.status_code == 200 else f"HTTP {r.status_code}", ms
        )

    def list_models(self) -> list[ModelInfo]:
        try:
            r = self._client.get(f"{self._base}/api/tags", timeout=5.0)
            return sorted(
                (ModelInfo(m["name"], size_bytes=m.get("size")) for m in r.json().get("models", [])),
                key=lambda x: x.id,
            )
        except (httpx.HTTPError, ValueError, KeyError):
            return []
