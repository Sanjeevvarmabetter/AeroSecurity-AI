"""Bearer-token authentication with role hierarchy (viewer < analyst < admin). Fails closed."""

import hashlib
import hmac
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import Settings, get_settings


class Role(IntEnum):
    VIEWER = 1
    ANALYST = 2
    ADMIN = 3


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated caller. `key_id` is a short fingerprint of the token (not reversible), so audit records
    identify which credential acted without ever storing it."""

    role: Role
    key_id: str

    @property
    def actor(self) -> str:
        return f"{self.role.name.lower()}:{self.key_id}"


def resolve_role(token: str | None, settings: Settings) -> Role | None:
    """Constant-time comparison against every configured token; unconfigured (empty) roles never match."""
    if not token:
        return None
    matched: Role | None = None
    for role, secret in (
        (Role.ADMIN, settings.api_token_admin),
        (Role.ANALYST, settings.api_token_analyst),
        (Role.VIEWER, settings.api_token_viewer),
    ):
        value = secret.get_secret_value()
        if value and hmac.compare_digest(token.encode(), value.encode()):
            matched = matched or role
    return matched


def require_role(minimum: Role) -> Callable[[Request, Settings], Principal]:
    def dependency(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> Principal:
        token = _extract_bearer(request)
        role = resolve_role(token, settings)
        if role is None or token is None:
            raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
        if role < minimum:
            raise HTTPException(403, f"{minimum.name.lower()} role required")
        return Principal(role, hashlib.sha256(token.encode()).hexdigest()[:8])

    return dependency


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-process sliding-window limiter, keyed by token hash (or client address when anonymous).

    Single-process only; a shared store would be required for multiple workers (documented limitation).
    """

    def __init__(self, app, limit_per_minute: int, exempt: tuple[str, ...] = ("/healthz",)) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.limit, self.exempt = limit_per_minute, exempt
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.exempt:
            return await call_next(request)
        token = _extract_bearer(request)
        key = (
            hashlib.sha256(token.encode()).hexdigest()[:16]
            if token
            else (request.client.host if request.client else "?")
        )
        now, window = time.monotonic(), self.hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.limit:
            retry = max(1, int(60 - (now - window[0])))
            return JSONResponse(
                {"error": {"code": "rate_limited", "message": "Too many requests", "details": None}},
                429,
                headers={"Retry-After": str(retry)},
            )
        window.append(now)
        return await call_next(request)


class SlidingWindowLimiter:
    """Per-key limiter for expensive operations (AI calls cost money/compute). In-process, single worker."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_s: float = 60.0) -> int | None:
        """Return None if allowed, else seconds to wait."""
        now, q = time.monotonic(), self.hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            return max(1, int(window_s - (now - q[0])))
        q.append(now)
        return None


ai_limiter = SlidingWindowLimiter()
