"""Provider abstraction. Both Ollama and OpenRouter implement this; callers never know which is in use."""

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from app.intelligence.errors import InvalidModelOutput

log = logging.getLogger(__name__)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int = 0


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    ok: bool
    detail: str
    latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ModelInfo:
    id: str
    size_bytes: int | None = None
    context_length: int | None = None
    free: bool | None = None


@dataclass(slots=True)
class StructuredResult[T: BaseModel]:
    value: T
    generation: GenerationResult
    attempts: int = 1
    notes: list[str] = field(default_factory=list)


def extract_json(text: str) -> object:
    """Parse a JSON object from model output, tolerating code fences and surrounding prose."""
    t = _FENCE.sub("", text.strip()).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            return json.loads(t[start : end + 1])
        raise


class LLMProvider(ABC):
    name: str

    def __init__(
        self,
        model: str,
        *,
        timeout_s: float,
        max_tokens: int,
        temperature: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model, self.timeout_s, self.max_tokens, self.temperature = (
            model,
            timeout_s,
            max_tokens,
            temperature,
        )
        self._sleep = sleep

    # -- required -----------------------------------------------------------------------------------
    @abstractmethod
    def _complete(self, messages: list[Message], *, json_mode: bool) -> GenerationResult: ...

    @abstractmethod
    def health_check(self) -> ProviderHealth: ...

    @abstractmethod
    def list_models(self) -> list[ModelInfo]: ...

    # -- common behaviour -----------------------------------------------------------------------------
    def generate(self, prompt: str, system: str | None = None) -> GenerationResult:
        msgs = ([Message("system", system)] if system else []) + [Message("user", prompt)]
        return self._complete(msgs, json_mode=False)

    def generate_structured[T: BaseModel](
        self,
        prompt: str,
        schema: type[T],
        system: str | None = None,
        *,
        max_repairs: int = 1,
        validate: Callable[[T], None] | None = None,
    ) -> StructuredResult[T]:
        """Single-turn structured generation. See `structured_chat`."""
        msgs = ([Message("system", system)] if system else []) + [Message("user", prompt)]
        return self.structured_chat(msgs, schema, max_repairs=max_repairs, validate=validate)

    def structured_chat[T: BaseModel](
        self,
        messages: list[Message],
        schema: type[T],
        *,
        max_repairs: int = 1,
        validate: Callable[[T], None] | None = None,
    ) -> StructuredResult[T]:
        """Ask for JSON and validate it against `schema` (plus an optional semantic `validate`). On invalid
        output, ask once more quoting only the error. Persistent failure raises InvalidModelOutput."""
        guide = (
            "Respond with ONE JSON object only, no prose and no code fences, matching this JSON Schema:\n"
            + json.dumps(schema.model_json_schema())
        )
        first = messages[0]
        if first.role == "system":
            msgs = [Message("system", f"{first.content}\n\n{guide}"), *messages[1:]]
        else:
            msgs = [Message("system", guide), *messages]
        base = list(msgs)
        notes: list[str] = []
        last_error = "unknown"
        for attempt in range(1, max_repairs + 2):
            gen = self._complete(msgs, json_mode=True)
            try:
                value = schema.model_validate(extract_json(gen.text))
                if validate is not None:
                    validate(
                        value
                    )  # semantic checks (e.g. evidence references); ValueError triggers a repair
                return StructuredResult(value, gen, attempt, notes)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = _brief(exc)
                notes.append(f"attempt {attempt}: {last_error}")
                log.warning(
                    "%s returned invalid structured output (attempt %d): %s", self.name, attempt, last_error
                )
                fix = f"That was invalid ({last_error}). Return ONLY the corrected JSON object."
                msgs = [*base, Message("assistant", gen.text[:4000]), Message("user", fix)]
        raise InvalidModelOutput(f"model did not return valid structured output: {last_error}")


def _brief(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        errs = exc.errors()[:3]
        return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in errs)
    return f"{type(exc).__name__}: {str(exc)[:120]}"
