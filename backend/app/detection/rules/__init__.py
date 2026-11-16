from app.detection.rules.base import AircraftRule, AirportRule
from app.detection.rules.det001 import ImpossiblePositionTransition
from app.detection.rules.det002 import ImplausibleVelocity
from app.detection.rules.det003 import AltitudeAnomaly
from app.detection.rules.det004 import DuplicateIdentity
from app.detection.rules.det005 import EmergencySquawk
from app.detection.rules.det006 import DataIntegrity
from app.detection.rules.det007 import UnusualTrajectory
from app.detection.rules.det008 import AbnormalAirportTraffic

AIRCRAFT_RULES: dict[str, type[AircraftRule]] = {
    r.rule_id: r
    for r in (
        ImpossiblePositionTransition,
        ImplausibleVelocity,
        AltitudeAnomaly,
        DuplicateIdentity,
        EmergencySquawk,
        DataIntegrity,
        UnusualTrajectory,
    )
}
AIRPORT_RULES: dict[str, type[AirportRule]] = {AbnormalAirportTraffic.rule_id: AbnormalAirportTraffic}
ALL_RULES: dict[str, type[AircraftRule] | type[AirportRule]] = {**AIRCRAFT_RULES, **AIRPORT_RULES}

__all__ = ["AIRCRAFT_RULES", "AIRPORT_RULES", "ALL_RULES", "AircraftRule", "AirportRule"]
