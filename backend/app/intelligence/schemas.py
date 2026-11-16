"""Validated shapes of AI output. Lenient about harmless extras, strict about required content and sizes."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Short = Annotated[str, Field(min_length=1, max_length=400)]
Para = Annotated[str, Field(min_length=1, max_length=1600)]
Ref = Annotated[str, Field(min_length=1, max_length=16)]


class Citation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ref: Ref
    note: Annotated[str, Field(max_length=400)] = ""


class AnomalyExplanation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    what_happened: Para
    rule_triggered: Annotated[str, Field(min_length=1, max_length=700)]
    supporting_evidence: Annotated[list[Citation], Field(max_length=15)] = []
    alternative_explanations: Annotated[list[Short], Field(max_length=8)]
    why_it_may_matter: Annotated[str, Field(min_length=1, max_length=1200)]
    next_steps: Annotated[list[Short], Field(max_length=8)]
    limitations: Annotated[list[Short], Field(max_length=6)] = []

    def refs(self) -> set[str]:
        return {c.ref for c in self.supporting_evidence}


class Observation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: Short
    refs: Annotated[list[Ref], Field(max_length=8)] = []


class AircraftInvestigation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    activity_summary: Para
    unusual_observations: Annotated[list[Observation], Field(max_length=12)] = []
    possible_explanations: Annotated[list[Short], Field(max_length=8)]
    security_implications: Annotated[list[Short], Field(max_length=8)] = []
    recommendations: Annotated[list[Short], Field(max_length=8)]
    evidence_refs: Annotated[list[Ref], Field(max_length=20)] = []
    limitations: Annotated[list[Short], Field(max_length=6)] = []

    def refs(self) -> set[str]:
        return {r for o in self.unusual_observations for r in o.refs} | set(self.evidence_refs)


class Finding(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: Short
    refs: Annotated[list[Ref], Field(max_length=8)] = []


class ThreatCorrelation(BaseModel):
    """Four strictly separated layers, each with its own citation rule (enforced by the service)."""

    model_config = ConfigDict(extra="ignore")
    verified_observations: Annotated[list[Finding], Field(max_length=10)] = []  # platform records only
    external_facts: Annotated[list[Finding], Field(max_length=8)] = []  # what the supplied documents state
    analytical_hypotheses: Annotated[list[Finding], Field(max_length=8)] = []  # reasoning, labelled as such
    ai_interpretation: Para
    consistent_with_categories: Annotated[list[Short], Field(max_length=8)] = []
    gaps_and_limitations: Annotated[list[Short], Field(max_length=8)] = []
    # Set by the SERVICE (never trusted from the model): hypotheses removed because they were not grounded.
    removed_ungrounded_hypotheses: int = 0

    def refs(self) -> set[str]:
        return {
            r
            for group in (self.verified_observations, self.external_facts, self.analytical_hypotheses)
            for f in group
            for r in f.refs
        }
