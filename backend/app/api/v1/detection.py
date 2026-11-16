from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import Principal, Role, require_role
from app.detection.engine import run_detection, sync_rule_registry
from app.detection.rules import ALL_RULES
from app.models import Anomaly, DetectionRule
from app.schemas.detection import DetectionRunRequest, RuleConfigUpdate, RuleOut

viewer = Depends(require_role(Role.VIEWER))
analyst = require_role(Role.ANALYST)

router = APIRouter(prefix="/detection", tags=["detection"], dependencies=[viewer])
Db = Annotated[Session, Depends(get_session)]
RuleId = Annotated[str, Path(pattern=r"^DET-\d{3}$")]

CATEGORY_MAP = {
    "DET-001": "POSITION_ANOMALY",
    "DET-002": "VELOCITY_ANOMALY",
    "DET-003": "ALTITUDE_ANOMALY",
    "DET-004": "IDENTITY_CONFLICT",
    "DET-005": "EMERGENCY_SQUAWK",
    "DET-006": "DATA_INTEGRITY",
    "DET-007": "TRAJECTORY_ANOMALY",
    "DET-008": "AIRPORT_TRAFFIC",
}


def _effective_config(rule_id: str, stored: dict[str, object] | None) -> dict[str, object]:
    cls = ALL_RULES.get(rule_id)
    defaults = cls.config_model().model_dump() if cls else {}
    return {**defaults, **(stored or {})}


@router.get("/rules", response_model=list[RuleOut])
def list_rules(db: Db) -> list[RuleOut]:
    sync_rule_registry(db)
    counts = dict(db.execute(select(Anomaly.rule_id, func.count(Anomaly.id)).group_by(Anomaly.rule_id)).all())
    rules = db.scalars(select(DetectionRule).order_by(DetectionRule.id)).all()
    return [
        RuleOut(
            id=r.id,
            name=r.name,
            description=r.description,
            version=r.version,
            enabled=r.enabled,
            config=_effective_config(r.id, r.config),
            findings_count=counts.get(r.id, 0),
            category=CATEGORY_MAP.get(r.id, "DETECTION"),
        )
        for r in rules
    ]


@router.get("/rules/{rule_id}", response_model=RuleOut)
def get_rule(db: Db, rule_id: RuleId) -> RuleOut:
    sync_rule_registry(db)
    r = db.get(DetectionRule, rule_id)
    if r is None:
        raise HTTPException(404, f"rule {rule_id} not found")
    cnt = db.scalar(select(func.count(Anomaly.id)).where(Anomaly.rule_id == rule_id)) or 0
    return RuleOut(
        id=r.id,
        name=r.name,
        description=r.description,
        version=r.version,
        enabled=r.enabled,
        config=_effective_config(r.id, r.config),
        findings_count=cnt,
        category=CATEGORY_MAP.get(r.id, "DETECTION"),
    )


@router.patch("/rules/{rule_id}", response_model=RuleOut)
def update_rule(
    db: Db,
    rule_id: RuleId,
    body: RuleConfigUpdate,
    who: Annotated[Principal, Depends(analyst)],
) -> RuleOut:
    sync_rule_registry(db)
    r = db.get(DetectionRule, rule_id)
    if r is None:
        raise HTTPException(404, f"rule {rule_id} not found")

    if body.enabled is not None:
        r.enabled = body.enabled

    if body.config is not None:
        cls = ALL_RULES.get(rule_id)
        if cls:
            try:
                # Validate against the rule's pydantic config model
                cls.config_model.model_validate(body.config)
            except Exception as e:
                raise HTTPException(422, f"invalid config for {rule_id}: {e}") from e
        r.config = body.config

    db.commit()
    db.refresh(r)
    cnt = db.scalar(select(func.count(Anomaly.id)).where(Anomaly.rule_id == rule_id)) or 0
    return RuleOut(
        id=r.id,
        name=r.name,
        description=r.description,
        version=r.version,
        enabled=r.enabled,
        config=_effective_config(r.id, r.config),
        findings_count=cnt,
        category=CATEGORY_MAP.get(r.id, "DETECTION"),
    )


@router.post("/run")
def trigger_detection(
    db: Db,
    who: Annotated[Principal, Depends(analyst)],
    body: DetectionRunRequest | None = None,
) -> dict[str, object]:
    body = body or DetectionRunRequest()
    report = run_detection(
        db,
        rule_ids=body.rule_ids,
        icao24=body.icao24,
        actor=who.actor,
    )
    return report.as_dict()
