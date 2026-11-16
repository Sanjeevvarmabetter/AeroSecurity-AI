"""Provider adapters against httpx.MockTransport. No network and no real keys are used."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.intelligence.base import GenerationResult, LLMProvider, Message, ModelInfo, ProviderHealth
from app.intelligence.errors import (
    InvalidModelOutput,
    NotConfigured,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.intelligence.ollama import OllamaProvider
from app.intelligence.openrouter import OpenRouterProvider

KEY = "sk-test-NOT-A-REAL-KEY-12345"
Handler = Callable[[httpx.Request], httpx.Response]
OK_BODY = {
    "model": "m1",
    "choices": [{"message": {"content": '{"a": 1}'}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 11, "completion_tokens": 3},
}


def orp(
    handler: Handler, *, key: str = KEY, retries: int = 2, sleeps: list[float] | None = None
) -> OpenRouterProvider:
    return OpenRouterProvider(
        "m1",
        api_key=key,
        base_url="https://or.example/api/v1",
        timeout_s=5,
        max_tokens=100,
        temperature=0.1,
        max_retries=retries,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
    )


def olp(handler: Handler, model: str = "q1") -> OllamaProvider:
    return OllamaProvider(
        model,
        base_url="http://ollama.local:11434",
        timeout_s=5,
        max_tokens=100,
        temperature=0.1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


class Out(BaseModel):
    answer: str
    refs: list[str] = []


# ---- OpenRouter ---------------------------------------------------------------------------------------
def test_openrouter_request_shape_and_result() -> None:
    seen: dict[str, object] = {}

    def h(r: httpx.Request) -> httpx.Response:
        seen.update(auth=r.headers["authorization"], body=json.loads(r.content), url=str(r.url))
        return httpx.Response(200, json=OK_BODY)

    res = orp(h).generate("hi", system="sys")
    assert seen["auth"] == f"Bearer {KEY}" and seen["url"] == "https://or.example/api/v1/chat/completions"
    body = seen["body"]
    assert isinstance(body, dict) and body["model"] == "m1" and body["max_tokens"] == 100
    assert [m["role"] for m in body["messages"]] == ["system", "user"] and "response_format" not in body
    assert (res.text, res.prompt_tokens, res.completion_tokens) == ('{"a": 1}', 11, 3)


def test_openrouter_structured_requests_json_mode() -> None:
    bodies: list[dict[str, object]] = []

    def h(r: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(r.content))
        return httpx.Response(200, json={**OK_BODY, "choices": [{"message": {"content": '{"answer": "x"}'}}]})

    out = orp(h).generate_structured("q", Out)
    assert out.value.answer == "x" and bodies[0]["response_format"] == {"type": "json_object"}
    messages: Any = bodies[0]["messages"]
    assert "JSON Schema" in messages[0]["content"]


def _reject(status: int) -> Handler:
    def handler(r: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": f"bad key {KEY}"}})

    return handler


def test_openrouter_requires_a_key_and_never_leaks_it() -> None:
    with pytest.raises(NotConfigured):
        orp(lambda r: httpx.Response(200, json=OK_BODY), key="").generate("x")
    for status, exc in ((401, ProviderAuthError), (403, ProviderAuthError), (402, ProviderAuthError)):
        with pytest.raises(exc) as ei:
            orp(_reject(status)).generate("x")
        assert KEY not in str(ei.value)  # message is ours, not the upstream body


def test_openrouter_rate_limit_retries_with_backoff_then_raises() -> None:
    sleeps: list[float] = []
    calls = {"n": 0}

    def h(r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    with pytest.raises(ProviderRateLimited):
        orp(h, retries=2, sleeps=sleeps).generate("x")
    assert calls["n"] == 3 and len(sleeps) == 2 and sleeps[0] < sleeps[1] + 1  # backoff between attempts


def test_openrouter_recovers_from_transient_5xx() -> None:
    seq = iter([httpx.Response(503), httpx.Response(200, json=OK_BODY)])
    assert orp(lambda r: next(seq)).generate("x").text == '{"a": 1}'


def test_openrouter_5xx_timeout_and_transport_errors() -> None:
    with pytest.raises(ProviderUnavailable):
        orp(lambda r: httpx.Response(500), retries=1).generate("x")

    def timeout(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=r)

    with pytest.raises(ProviderTimeout):
        orp(timeout, retries=1).generate("x")

    def down(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=r)

    with pytest.raises(ProviderUnavailable):
        orp(down, retries=0).generate("x")


def test_openrouter_bad_request_and_odd_responses() -> None:
    with pytest.raises(ProviderBadRequest, match="HTTP 400"):
        orp(lambda r: httpx.Response(400, json={"error": {"message": "unsupported param"}})).generate("x")
    with pytest.raises(ProviderBadRequest, match="unexpected response shape"):
        orp(lambda r: httpx.Response(200, json={"nope": 1})).generate("x")
    with pytest.raises(ProviderBadRequest, match="unexpected response shape"):
        orp(lambda r: httpx.Response(200, content=b"<html>")).generate("x")


def test_openrouter_empty_completion_retried_once_then_unavailable() -> None:
    empty = {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}
    seq = iter([httpx.Response(200, json=empty), httpx.Response(200, json=OK_BODY)])
    assert orp(lambda r: next(seq)).generate("x").text == '{"a": 1}'
    with pytest.raises(ProviderUnavailable, match="empty response twice"):
        orp(lambda r: httpx.Response(200, json=empty)).generate("x")


def test_openrouter_reasoning_budget_exhaustion_gets_an_actionable_error() -> None:
    """Real-world case: reasoning models burn max_tokens thinking and return no content (finish_reason=length)."""
    calls = {"n": 0}

    def h(r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": None, "reasoning": "thinking..."}, "finish_reason": "length"}
                ]
            },
        )

    with pytest.raises(ProviderBadRequest, match="AI_MAX_OUTPUT_TOKENS"):
        orp(h).generate("x")
    assert calls["n"] == 1  # not retried: it cannot help


def test_openrouter_health_and_model_listing() -> None:
    def h(r: httpx.Request) -> httpx.Response:
        if r.url.path.endswith("/auth/key"):
            return httpx.Response(
                200 if r.headers.get("authorization") == f"Bearer {KEY}" else 401, json={"data": {}}
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "b/free-model:free",
                        "context_length": 1000,
                        "supported_parameters": ["response_format"],
                        "pricing": {"prompt": "0", "completion": "0"},
                    },
                    {
                        "id": "a/paid",
                        "context_length": 2000,
                        "supported_parameters": ["response_format"],
                        "pricing": {"prompt": "0.1", "completion": "0.2"},
                    },
                    {
                        "id": "c/no-json",
                        "context_length": 3,
                        "supported_parameters": ["temperature"],
                        "pricing": {},
                    },
                ]
            },
        )

    assert orp(h).health_check() == ProviderHealth(True, "ok", orp(h).health_check().latency_ms)
    assert orp(h, key="wrong").health_check().detail == "API key rejected"
    assert orp(h, key="").health_check() == ProviderHealth(False, "API key not configured")
    models = orp(h).list_models()
    assert [m.id for m in models] == ["a/paid", "b/free-model:free"]  # JSON-capable only, sorted
    assert [m.free for m in models] == [False, True]


# ---- Ollama -------------------------------------------------------------------------------------------
def test_ollama_chat_request_and_result() -> None:
    seen: dict[str, object] = {}

    def h(r: httpx.Request) -> httpx.Response:
        seen.update(body=json.loads(r.content), url=str(r.url))
        return httpx.Response(
            200,
            json={
                "model": "q1",
                "message": {"content": '{"answer": "ok"}'},
                "prompt_eval_count": 20,
                "eval_count": 5,
            },
        )

    out = olp(h).generate_structured("q", Out, system="s")
    body = seen["body"]
    assert seen["url"] == "http://ollama.local:11434/api/chat" and isinstance(body, dict)
    assert body["stream"] is False and body["format"] == "json" and body["options"]["num_predict"] == 100
    assert (
        out.value.answer == "ok"
        and out.generation.prompt_tokens == 20
        and out.generation.completion_tokens == 5
    )


def test_ollama_error_mapping() -> None:
    with pytest.raises(ProviderBadRequest, match="ollama pull"):
        olp(lambda r: httpx.Response(404, json={"error": "model not found"})).generate("x")
    with pytest.raises(ProviderUnavailable):
        olp(lambda r: httpx.Response(500)).generate("x")
    with pytest.raises(NotConfigured):
        olp(lambda r: httpx.Response(200), model="").generate("x")

    def down(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=r)

    with pytest.raises(ProviderUnavailable, match="ollama serve"):
        olp(down).generate("x")

    def slow(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=r)

    with pytest.raises(ProviderTimeout, match="AI_TIMEOUT_S"):
        olp(slow).generate("x")
    with pytest.raises(ProviderBadRequest, match="unexpected response shape"):
        olp(lambda r: httpx.Response(200, json={"oops": 1})).generate("x")


def test_ollama_health_and_models() -> None:
    def h(r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"models": [{"name": "z:7b", "size": 5}, {"name": "a:1b", "size": 3}]}
        )

    assert olp(h).health_check().ok is True
    assert [m.id for m in olp(h).list_models()] == ["a:1b", "z:7b"]

    def down(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=r)

    assert (
        olp(down).health_check() == ProviderHealth(False, "not reachable") and olp(down).list_models() == []
    )


# ---- generate_structured behaviour (provider-independent) ---------------------------------------------
class Scripted(LLMProvider):
    name = "fake"

    def __init__(self, replies: list[str]) -> None:
        super().__init__("fake-model", timeout_s=1, max_tokens=10, temperature=0)
        self.replies, self.seen = list(replies), []  # type: list[str], list[list[Message]]

    def _complete(self, messages: list[Message], *, json_mode: bool) -> GenerationResult:
        self.seen.append(messages)
        return GenerationResult(self.replies.pop(0), self.model)

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(True, "ok")

    def list_models(self) -> list[ModelInfo]:
        return []


def test_structured_output_tolerates_fences_and_prose() -> None:
    for raw in (
        '```json\n{"answer": "a"}\n```',
        'Sure! Here you go: {"answer": "a"} Hope that helps.',
        '{"answer":"a","extra":1}',
    ):
        assert Scripted([raw]).generate_structured("q", Out).value.answer == "a"


def test_malformed_json_is_repaired_once() -> None:
    p = Scripted(['{"answer": ', '{"answer": "fixed"}'])
    r = p.generate_structured("q", Out)
    assert r.value.answer == "fixed" and r.attempts == 2 and r.notes
    repair = p.seen[1][-1].content
    assert "invalid" in repair and "JSONDecodeError" in repair  # only the error is quoted back


def test_schema_violations_exhaust_repairs_then_raise() -> None:
    p = Scripted(['{"wrong": 1}', '{"also_wrong": 2}'])
    with pytest.raises(InvalidModelOutput, match="answer"):
        p.generate_structured("q", Out)
    assert len(p.seen) == 2
    with pytest.raises(InvalidModelOutput):
        Scripted(["not json at all"]).generate_structured("q", Out, max_repairs=0)


def test_semantic_validator_triggers_repair() -> None:
    def no_e9(v: Out) -> None:
        if "E9" in v.refs:
            raise ValueError("unknown evidence reference(s) ['E9']")

    p = Scripted(['{"answer": "x", "refs": ["E9"]}', '{"answer": "x", "refs": ["E1"]}'])
    r = p.generate_structured("q", Out, validate=no_e9)
    assert r.value.refs == ["E1"] and r.attempts == 2 and "unknown evidence" in p.seen[1][-1].content
