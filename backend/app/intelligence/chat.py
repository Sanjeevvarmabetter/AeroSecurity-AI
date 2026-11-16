"""Conversational assistant: a bounded tool-use loop over the allowlisted, read-only tools in `tools.py`."""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import Principal
from app.intelligence import prompts, tools
from app.intelligence.base import GenerationResult, Message
from app.intelligence.context import clean
from app.intelligence.errors import AIError
from app.intelligence.schemas import Citation
from app.intelligence.service import ProviderFactory, certainty_warnings, effective_settings
from app.models import AuditLog, ChatMessage, Conversation

log = logging.getLogger(__name__)


# Statements of absence. They are only trustworthy when a tool actually returned an empty result.
_ABSENCE = re.compile(
    r"\b(?:no|not any|none|zero|without|never)\b[^.;]{0,40}"
    r"\b(?:detections?|anomal(?:y|ies)|events?|findings?|records?|documents?|observations?)\b"
    r"|\b(?:has|have|had) not been (?:detected|recorded|observed|flagged)\b",
    re.IGNORECASE,
)


class ChatStep(BaseModel):
    """One model turn: either call a tool or give the final answer."""

    model_config = ConfigDict(extra="ignore")
    action: Literal["tool", "answer"]
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    answer: str | None = Field(default=None, max_length=4000)
    citations: list[Citation] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def _shape(self) -> "ChatStep":
        if self.action == "tool" and not self.tool:
            raise ValueError("action 'tool' requires a tool name")
        if self.action == "answer" and not (self.answer and self.answer.strip()):
            raise ValueError("action 'answer' requires non-empty answer text")
        return self


class ConversationError(Exception):
    status_code = 409


@dataclass
class ToolLog:
    tool: str
    arguments: dict[str, Any]
    ok: bool
    error: str | None = None
    records: list[str] = field(default_factory=list)
    empty: bool = False  # the tool ran fine but returned no records


@dataclass
class ChatResult:
    conversation_id: str
    answer: str
    citations: list[dict[str, str]]
    tool_calls: list[ToolLog]
    warnings: list[str]
    provider: str
    model: str


def _title(msg: str) -> str:
    return str(clean(msg, 80)) or "Conversation"


def _load(
    session: Session, who: Principal, conversation_id: str | None, first_message: str, cap: int
) -> Conversation:
    if conversation_id is None:
        conv = Conversation(id=str(uuid.uuid4()), owner=who.actor, title=_title(first_message))
        session.add(conv)
        session.flush()
        return conv
    found = session.get(Conversation, conversation_id)
    if found is None or (found.owner != who.actor and who.role.name != "ADMIN"):
        raise ConversationError("conversation not found")  # same answer for 'missing' and 'not yours'
    conv = found
    n = len(session.scalars(select(ChatMessage.id).where(ChatMessage.conversation_id == conv.id)).all())
    if n >= cap:
        raise ConversationError("this conversation reached its message limit; start a new one")
    return conv


def _history(session: Session, conv: Conversation, keep: int) -> tuple[list[Message], set[str]]:
    """Prior user messages and FINAL assistant answers only (raw tool results are not replayed)."""
    rows = session.scalars(
        select(ChatMessage).where(ChatMessage.conversation_id == conv.id).order_by(ChatMessage.id)
    ).all()
    turns = [r for r in rows if r.role == "user" or (r.role == "assistant" and not r.tool_name)]
    refs = {c["ref"] for r in turns if r.citations for c in r.citations}
    return [Message(r.role, r.content) for r in turns[-keep:]] if keep else [], refs


def _save(session: Session, conv: Conversation, role: str, content: str, **kw: Any) -> ChatMessage:
    m = ChatMessage(conversation_id=conv.id, role=role, content=content, **kw)
    session.add(m)
    session.flush()
    return m


def chat(
    session: Session,
    settings: Settings,
    factory: ProviderFactory,
    who: Principal,
    *,
    conversation_id: str | None,
    message: str,
    provider: str | None,
    model: str | None,
) -> ChatResult:
    eff = effective_settings(session, settings)
    conv = _load(session, who, conversation_id, message, settings.chat_max_messages_per_conversation)
    history, known = _history(session, conv, settings.chat_history_messages)
    _save(session, conv, "user", message)
    session.commit()

    name = provider or eff.provider
    prov = factory(name, model)
    system = prompts.CHAT_SYSTEM + tools.catalog()
    msgs: list[Message] = [Message("system", system), *history, Message("user", message)]
    logs: list[ToolLog] = []
    warnings: list[str] = []
    forced = False
    tokens = 0
    gen_model = prov.model

    def validator(step: ChatStep) -> None:
        if step.action == "tool":
            if forced:
                raise ValueError("the tool-call limit is reached: reply with action 'answer' now")
            if step.tool not in tools.TOOLS:
                raise ValueError(f"unknown tool '{step.tool}'; allowed: {', '.join(tools.TOOLS)}")
        else:
            unknown = sorted({c.ref for c in step.citations} - known)
            if unknown:
                raise ValueError(
                    f"unknown citation(s) {unknown}; cite only ids returned by tools: {sorted(known)}"
                )

    for _ in range(settings.chat_max_tool_calls + 2):
        forced = len(logs) >= settings.chat_max_tool_calls
        if forced:
            msgs.append(
                Message("user", "Tool-call limit reached. Give your final answer now from the results above.")
            )
        try:
            res = prov.structured_chat(msgs, ChatStep, validate=validator)
        except AIError as exc:
            session.add(
                AuditLog(
                    actor=who.actor,
                    action="ai.failed",
                    entity_type="conversation",
                    entity_id=conv.id,
                    details={"kind": "chat", "provider": name, "model": prov.model, "error": str(exc)[:200]},
                )
            )
            session.commit()
            raise
        gen: GenerationResult = res.generation
        gen_model = gen.model or gen_model
        tokens += (gen.prompt_tokens or 0) + (gen.completion_tokens or 0)
        step = res.value

        if step.action == "answer":
            out = step.model_dump(mode="json", include={"citations"})["citations"]
            ans = step.answer or ""
            if not out and not logs:
                warnings.append(
                    "No platform records were retrieved or cited: treat this as general information."
                )
            warnings += certainty_warnings({"a": ans, "c": [c["note"] for c in out]})
            if _ABSENCE.search(ans) and not any(t.ok and t.empty for t in logs):
                warnings.append(
                    "The answer says something is absent, but no tool call returned an empty result for it. "
                    "Verify before relying on this."
                )
            _save(
                session,
                conv,
                "assistant",
                ans,
                citations=out,
                warnings=warnings,
                provider=name,
                model=gen_model,
                tokens=tokens,
            )
            session.commit()
            return ChatResult(conv.id, ans, out, logs, warnings, name, gen_model)

        # -- tool call -----------------------------------------------------------------------------------
        if step.tool is None:  # ChatStep guarantees this; fail loudly rather than assume
            raise ConversationError("tool step without a tool name")
        _save(
            session,
            conv,
            "assistant",
            json.dumps({"tool": step.tool, "arguments": step.arguments})[:2000],
            tool_name=step.tool,
            tool_args=step.arguments,
            provider=name,
            model=gen_model,
        )
        entry = ToolLog(step.tool, step.arguments, ok=True)
        try:
            result = tools.execute(
                session, step.tool, step.arguments, who.role, settings.chat_tool_result_chars
            )
            known |= result.refs
            entry.records = sorted(result.refs)
            entry.empty = not any(isinstance(v, list) and v for v in result.data.values())
            payload = json.dumps(result.data, default=str)
        except tools.ToolError as exc:
            entry.ok, entry.error = False, str(exc)
            payload = json.dumps({"error": str(exc)})
        logs.append(entry)
        _save(session, conv, "tool", payload[: settings.chat_tool_result_chars + 200], tool_name=step.tool)
        session.add(
            AuditLog(
                actor=who.actor,
                action="ai.tool_call",
                entity_type="conversation",
                entity_id=conv.id,
                details={
                    "tool": step.tool,
                    "arguments": clean(step.arguments, 100),
                    "ok": entry.ok,
                    "provider": name,
                },
            )
        )
        session.commit()
        msgs.append(
            Message(
                "assistant", json.dumps({"action": "tool", "tool": step.tool, "arguments": step.arguments})
            )
        )
        msgs.append(Message("user", f'<tool_result tool="{step.tool}">\n{payload}\n</tool_result>'))

    raise ConversationError("the assistant did not produce a final answer")  # pragma: no cover


def conversation_messages(session: Session, conv: Conversation) -> list[ChatMessage]:
    return list(
        session.scalars(
            select(ChatMessage).where(ChatMessage.conversation_id == conv.id).order_by(ChatMessage.id)
        )
    )
