"""Analytics service aggregating platform metrics, fleet statistics, and historical trends."""

from datetime import timedelta
from typing import Any

from sqlalchemy import and_, case, distinct, func, select
from sqlalchemy.orm import Session

from app.aviation.aircraft_category import classify_aircraft_category
from app.models import Aircraft, AircraftObservation, Airport, Anomaly, DataSource, Investigation


def get_overview_analytics(session: Session) -> dict[str, Any]:
    """Generates complete real platform overview statistics from stored backend data."""
    # 1. Total counts
    total_aircraft = session.scalar(select(func.count(Aircraft.id))) or 0
    total_observations = session.scalar(select(func.count(AircraftObservation.id))) or 0
    total_airports = session.scalar(select(func.count(Airport.id))) or 0
    total_anomalies = session.scalar(select(func.count(Anomaly.id))) or 0
    total_investigations = session.scalar(select(func.count(Investigation.id))) or 0

    # 2. Latest data timestamps
    newest_obs_at = session.scalar(select(func.max(AircraftObservation.observed_at)))
    latest_refresh = session.scalar(select(func.max(AircraftObservation.created_at)))

    # 3. Active aircraft in latest snapshot window (last 1 hour of available data)
    active_aircraft_count = 0
    if newest_obs_at:
        window_start = newest_obs_at - timedelta(hours=1)
        active_aircraft_count = (
            session.scalar(
                select(func.count(distinct(AircraftObservation.aircraft_id))).where(
                    AircraftObservation.observed_at >= window_start,
                    AircraftObservation.observed_at <= newest_obs_at,
                )
            )
            or 0
        )

    # 4. Anomalies by severity
    sev_rows = session.execute(
        select(Anomaly.severity, func.count(Anomaly.id)).group_by(Anomaly.severity)
    ).all()
    by_severity = {s: 0 for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    for sev, count in sev_rows:
        by_severity[sev] = count

    # 5. Anomalies by status
    status_rows = session.execute(
        select(Anomaly.status, func.count(Anomaly.id)).group_by(Anomaly.status)
    ).all()
    by_status = {s: 0 for s in ("OPEN", "INVESTIGATING", "FALSE_POSITIVE", "RESOLVED")}
    for st, count in status_rows:
        by_status[st] = count

    # 6. Critical & Emergency events
    critical_events = by_severity["CRITICAL"]
    emergency_squawks = (
        session.scalar(select(func.count(Anomaly.id)).where(Anomaly.detection_type == "EMERGENCY_SQUAWK"))
        or 0
    )

    # 7. Recent Anomalies Feed (last 6)
    recent_anom_rows = session.execute(
        select(Anomaly, Aircraft.icao24, Aircraft.registration)
        .outerjoin(Aircraft, Aircraft.id == Anomaly.aircraft_id)
        .order_by(Anomaly.event_start.desc())
        .limit(6)
    ).all()
    recent_anomalies = [
        {
            "id": f"ANM-{a.id:04d}",
            "rule_id": a.rule_id,
            "title": a.title,
            "severity": a.severity,
            "status": a.status,
            "confidence": a.confidence,
            "icao24": icao,
            "registration": reg,
            "event_start": a.event_start.isoformat() if a.event_start else None,
        }
        for a, icao, reg in recent_anom_rows
    ]

    # 8. Data Sources Health
    sources = session.scalars(select(DataSource).order_by(DataSource.name)).all()
    sources_status = [
        {
            "name": s.name,
            "kind": s.kind,
            "enabled": s.enabled,
            "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
            "last_error": s.last_error,
        }
        for s in sources
    ]

    # 9. Top Aircraft Types
    type_rows = session.execute(
        select(Aircraft.aircraft_type, func.count(Aircraft.id))
        .where(Aircraft.aircraft_type.is_not(None))
        .group_by(Aircraft.aircraft_type)
        .order_by(func.count(Aircraft.id).desc())
        .limit(8)
    ).all()
    top_aircraft_types = [{"type": t, "count": c} for t, c in type_rows]

    # 10. Top Detection Types
    det_type_rows = session.execute(
        select(Anomaly.detection_type, func.count(Anomaly.id))
        .group_by(Anomaly.detection_type)
        .order_by(func.count(Anomaly.id).desc())
    ).all()
    by_detection_type = {dt: c for dt, c in det_type_rows}

    return {
        "total_aircraft": total_aircraft,
        "active_aircraft": active_aircraft_count,
        "total_observations": total_observations,
        "total_airports": total_airports,
        "total_anomalies": total_anomalies,
        "total_investigations": total_investigations,
        "critical_events": critical_events,
        "emergency_squawks": emergency_squawks,
        "newest_observation_at": newest_obs_at.isoformat() if newest_obs_at else None,
        "latest_refresh_at": latest_refresh.isoformat() if latest_refresh else None,
        "by_severity": by_severity,
        "by_status": by_status,
        "by_detection_type": by_detection_type,
        "top_aircraft_types": top_aircraft_types,
        "recent_anomalies": recent_anomalies,
        "data_sources": sources_status,
    }


def get_fleet_analytics(session: Session) -> dict[str, Any]:
    """Generates distribution histograms for speeds, altitudes, aircraft categories and manufacturers."""
    # 1. Altitude distribution (barometric altitude in metres)
    # 0-1000m, 1000-3000m, 3000-6000m, 6000-9000m, 9000-12000m, >12000m
    alt_buckets = session.execute(
        select(
            func.count(case((AircraftObservation.baro_altitude_m < 1000, 1))).label("b0_1k"),
            func.count(
                case(
                    (
                        and_(
                            AircraftObservation.baro_altitude_m >= 1000,
                            AircraftObservation.baro_altitude_m < 3000,
                        ),
                        1,
                    )
                )
            ).label("b1k_3k"),
            func.count(
                case(
                    (
                        and_(
                            AircraftObservation.baro_altitude_m >= 3000,
                            AircraftObservation.baro_altitude_m < 6000,
                        ),
                        1,
                    )
                )
            ).label("b3k_6k"),
            func.count(
                case(
                    (
                        and_(
                            AircraftObservation.baro_altitude_m >= 6000,
                            AircraftObservation.baro_altitude_m < 9000,
                        ),
                        1,
                    )
                )
            ).label("b6k_9k"),
            func.count(
                case(
                    (
                        and_(
                            AircraftObservation.baro_altitude_m >= 9000,
                            AircraftObservation.baro_altitude_m < 12000,
                        ),
                        1,
                    )
                )
            ).label("b9k_12k"),
            func.count(case((AircraftObservation.baro_altitude_m >= 12000, 1))).label("b12k_plus"),
        ).where(AircraftObservation.baro_altitude_m.is_not(None))
    ).one()

    altitude_distribution = [
        {"range": "0 – 1,000 m", "label": "< 3.3k ft", "count": alt_buckets[0]},
        {"range": "1,000 – 3,000 m", "label": "3.3k – 10k ft", "count": alt_buckets[1]},
        {"range": "3,000 – 6,000 m", "label": "10k – 20k ft", "count": alt_buckets[2]},
        {"range": "6,000 – 9,000 m", "label": "20k – 30k ft", "count": alt_buckets[3]},
        {"range": "9,000 – 12,000 m", "label": "30k – 40k ft", "count": alt_buckets[4]},
        {"range": "> 12,000 m", "label": "> 40k ft", "count": alt_buckets[5]},
    ]

    # 2. Speed distribution (reported velocity in m/s)
    # Speed buckets (m/s): 0-50, 50-100, 100-150, 150-200, 200-250, >250 (roughly 100-kt steps)
    spd_buckets = session.execute(
        select(
            func.count(case((AircraftObservation.velocity_ms < 50, 1))).label("b0_50"),
            func.count(
                case((and_(AircraftObservation.velocity_ms >= 50, AircraftObservation.velocity_ms < 100), 1))
            ).label("b50_100"),
            func.count(
                case((and_(AircraftObservation.velocity_ms >= 100, AircraftObservation.velocity_ms < 150), 1))
            ).label("b100_150"),
            func.count(
                case((and_(AircraftObservation.velocity_ms >= 150, AircraftObservation.velocity_ms < 200), 1))
            ).label("b150_200"),
            func.count(
                case((and_(AircraftObservation.velocity_ms >= 200, AircraftObservation.velocity_ms < 250), 1))
            ).label("b200_250"),
            func.count(case((AircraftObservation.velocity_ms >= 250, 1))).label("b250_plus"),
        ).where(AircraftObservation.velocity_ms.is_not(None))
    ).one()

    speed_distribution = [
        {"range": "0 – 50 m/s", "label": "< 100 kt", "count": spd_buckets[0]},
        {"range": "50 – 100 m/s", "label": "100 – 200 kt", "count": spd_buckets[1]},
        {"range": "100 – 150 m/s", "label": "200 – 300 kt", "count": spd_buckets[2]},
        {"range": "150 – 200 m/s", "label": "300 – 400 kt", "count": spd_buckets[3]},
        {"range": "200 – 250 m/s", "label": "400 – 500 kt", "count": spd_buckets[4]},
        {"range": "> 250 m/s", "label": "> 500 kt", "count": spd_buckets[5]},
    ]

    # 3. Aircraft Categories
    all_aircraft = session.execute(select(Aircraft.aircraft_type, Aircraft.model)).all()
    categories: dict[str, int] = {}
    for t, m in all_aircraft:
        cat = classify_aircraft_category(t, m)
        categories[cat] = categories.get(cat, 0) + 1
    category_distribution = [{"category": k, "count": v} for k, v in sorted(categories.items())]

    # 4. Top Manufacturers
    mfg_rows = session.execute(
        select(Aircraft.manufacturer, func.count(Aircraft.id))
        .where(Aircraft.manufacturer.is_not(None))
        .group_by(Aircraft.manufacturer)
        .order_by(func.count(Aircraft.id).desc())
        .limit(6)
    ).all()
    top_manufacturers = [{"manufacturer": m, "count": c} for m, c in mfg_rows]

    # 5. On Ground vs Airborne
    ground_counts = session.execute(
        select(
            func.count(case((AircraftObservation.on_ground.is_(True), 1))),
            func.count(case((AircraftObservation.on_ground.is_(False), 1))),
        )
    ).one()

    return {
        "altitude_distribution": altitude_distribution,
        "speed_distribution": speed_distribution,
        "category_distribution": category_distribution,
        "top_manufacturers": top_manufacturers,
        "on_ground_count": ground_counts[0],
        "airborne_count": ground_counts[1],
    }
