"""Provider abstraction. The detection engine depends only on stored observations, never on a provider."""

from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.ingestion.schema import NormalizedObservation, Rejection


class ObservationProvider(ABC):
    #: Stable identifier stored in data_sources.name
    name: str
    #: "dataset" (offline file) or "api" (live network provider)
    kind: str
    terms_url: str | None = None
    #: Live providers default to disabled until usage rights are confirmed by an operator.
    default_enabled: bool = False

    @abstractmethod
    def fetch(self) -> Iterator[NormalizedObservation | Rejection]:
        """Yield normalised observations or rejections. Must not raise for a single bad record."""
