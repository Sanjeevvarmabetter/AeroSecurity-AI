from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy.orm import Session

from app.ingestion.poller import MAX_CONSECUTIVE_FAILURES, PollerStopped, poll
from app.ingestion.schema import ImportReport
from app.ingestion.service import SourceDisabledError
from tests.test_integration_ingest import FakeProvider, obs

pytestmark = pytest.mark.integration


def factory(db: Session):  # type: ignore[no-untyped-def]
    @contextmanager
    def f() -> Iterator[Session]:
        yield db

    return f


def test_polls_the_requested_number_of_times_with_the_interval(db_session: Session) -> None:
    reports: list[ImportReport] = []
    sleeps: list[float] = []
    n = poll(
        factory(db_session),
        FakeProvider([obs()]),
        polls=3,
        interval_s=300,
        on_report=reports.append,
        sleep=sleeps.append,
    )
    assert n == 3 and len(reports) == 3 and sleeps == [300, 300]  # no sleep after the last poll
    assert (
        reports[0].inserted == 1 and reports[1].duplicates == 1
    )  # repeated identical fixes are not re-stored


def test_disabled_source_stops_immediately(db_session: Session) -> None:
    p = FakeProvider([obs()])
    p.default_enabled = False
    with pytest.raises(SourceDisabledError):
        poll(factory(db_session), p, polls=0, interval_s=1, on_report=lambda r: None, sleep=lambda s: None)


def test_transient_failures_are_survived_but_a_streak_stops_the_loop(db_session: Session) -> None:
    class Flaky(FakeProvider):
        calls = 0

        def fetch(self):  # type: ignore[no-untyped-def]
            Flaky.calls += 1
            if Flaky.calls <= 2:
                raise RuntimeError("temporary outage")
            yield from self.items

    Flaky.calls = 0
    reports: list[ImportReport] = []
    assert (
        poll(
            factory(db_session),
            Flaky([obs()]),
            polls=4,
            interval_s=0,
            on_report=reports.append,
            sleep=lambda s: None,
        )
        == 2
    )
    assert len(reports) == 2  # two failed polls were skipped, the rest succeeded

    class Dead(FakeProvider):
        def fetch(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("down")
            yield

    with pytest.raises(PollerStopped, match=str(MAX_CONSECUTIVE_FAILURES)):
        poll(
            factory(db_session),
            Dead([]),
            polls=0,
            interval_s=0,
            on_report=lambda r: None,
            sleep=lambda s: None,
        )
