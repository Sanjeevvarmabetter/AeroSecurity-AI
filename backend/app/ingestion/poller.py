"""Long-running collection loop for live providers. Deliberately slow: credits and terms are limited."""

import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session

from app.ingestion.base import ObservationProvider
from app.ingestion.schema import ImportReport
from app.ingestion.service import SourceDisabledError, ingest

log = logging.getLogger(__name__)
MAX_CONSECUTIVE_FAILURES = 5


class PollerStopped(Exception):
    """Too many consecutive failures; the operator should look at data_sources.last_error."""


def poll(
    session_factory: Callable[[], AbstractContextManager[Session]],
    provider: ObservationProvider,
    *,
    polls: int,
    interval_s: float,
    on_report: Callable[[ImportReport], None],
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run `polls` collections (0 = until interrupted), `interval_s` apart. Returns the number that succeeded.

    A disabled source stops immediately (an operator decision). Transient failures are recorded by `ingest`
    on the data source, logged, and retried; MAX_CONSECUTIVE_FAILURES in a row stops the loop.
    """
    done = failures = ok = 0
    while polls == 0 or done < polls:
        try:
            with session_factory() as session:
                report = ingest(session, provider, actor="poller")
            on_report(report)
            ok += 1
            failures = 0
        except SourceDisabledError:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad poll must not end a long-running collector
            failures += 1
            log.warning("poll %d failed (%d in a row): %s: %s", done + 1, failures, type(exc).__name__, exc)
            if failures >= MAX_CONSECUTIVE_FAILURES:
                raise PollerStopped(f"{failures} consecutive failures; last: {type(exc).__name__}") from exc
        done += 1
        if polls == 0 or done < polls:
            sleep(interval_s)
    return ok
