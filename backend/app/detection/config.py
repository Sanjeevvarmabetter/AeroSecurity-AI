"""Per-rule configuration. Defaults live here; operators may override them in detection_rules.config (JSONB).
Changing behaviour-affecting values must be accompanied by a rule version bump."""

from pydantic import BaseModel, ConfigDict, Field


class RuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimingTolerance(BaseModel):
    """Tolerances measured on real OpenSky data: position timestamps jitter by up to ~1 s, so very short
    intervals must never be trusted for speed estimation."""

    timestamp_uncertainty_s: float = Field(default=1.0, ge=0)
    position_uncertainty_m: float = Field(default=100.0, ge=0)  # per fix


class Det001Config(RuleConfig, TimingTolerance):
    hard_speed_ceiling_ms: float = 1000.0  # no aircraft considered here can exceed this
    civil_speed_ceiling_ms: float = 350.0
    reported_speed_factor: float = 2.0  # displacement speed must also exceed this x reported speed
    gap_s: float = 120.0
    episode_join_s: float = 60.0
    max_evidence_transitions: int = 10


class Det002Config(RuleConfig, TimingTolerance):
    default_max_speed_ms: float = 350.0
    # Ground-speed ceilings by ICAO type code. Deliberately small and incomplete: extend per deployment.
    type_limits_ms: dict[str, float] = Field(
        default_factory=lambda: {
            "PA46": 120.0,
            "C172": 80.0,
            "C182": 90.0,
            "SR22": 120.0,
            "P28A": 80.0,
            "LJ55": 300.0,
            "LJ60": 300.0,
        }
    )
    max_acceleration_ms2: float = 25.0
    accel_max_dt_s: float = 20.0
    run_join_s: float = 30.0


class Det003Config(RuleConfig, TimingTolerance):
    max_vertical_rate_ms: float = 100.0  # altitude-derived lower bound above this is implausible
    inconsistent_reported_vrate_ms: float = 30.0
    vrate_window_min_s: float = 2.0
    vrate_window_max_s: float = 15.0
    altitude_resolution_m: float = 8.0  # barometric altitude is quantised (25 ft)
    baro_geo_divergence_m: float = 1500.0
    baro_geo_divergence_high_m: float = 3000.0
    on_ground_max_altitude_m: float = 6000.0  # no airport is this high
    missing_altitude_min_run: int = 10
    run_join_s: float = 30.0


class Det004Config(RuleConfig, TimingTolerance):
    overlap_s: float = 5.0  # cross-source observations this close in time are "simultaneous"
    plausible_speed_ms: float = 350.0
    min_alternations: int = 3  # out-and-back jumps needed to call same-source interleaving
    window_s: float = 60.0


class Det005Config(RuleConfig):
    episode_gap_s: float = 300.0
    min_observations: int = 2  # a single observation can be a transient while the code is being dialled
    max_evidence_observations: int = 12


class Det006Config(RuleConfig):
    last_contact_tolerance_s: float = 1.0
    future_tolerance_s: float = 60.0
    run_join_s: float = 60.0


class Det007Config(RuleConfig):
    min_baseline_positions: int = 300
    min_baseline_duration_s: float = 600.0
    window_s: float = 30.0
    min_turn_rate_dps: float = 6.0  # standard-rate turn is 3 deg/s
    min_speed_ms: float = 30.0  # heading is noisy at taxi speeds
    robust_z_threshold: float = 8.0
    orbit_window_s: float = 900.0
    orbit_min_rotation_deg: float = 540.0
    orbit_max_radius_m: float = 8000.0
    sample_s: float = 5.0
    run_join_s: float = 60.0


class Det008Config(RuleConfig):
    radius_m: float = 10_000.0
    min_baseline_hours: int = 24
    robust_z_threshold: float = 6.0
    min_count: int = 5  # a spike must also be a meaningful absolute number
    min_ratio_to_median: float = 2.0
