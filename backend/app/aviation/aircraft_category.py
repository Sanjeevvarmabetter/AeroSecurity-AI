"""Aviation aircraft category classification based on ICAO type codes and model descriptions."""

JET_TYPES = {
    "A318",
    "A319",
    "A320",
    "A321",
    "A332",
    "A333",
    "A338",
    "A339",
    "A343",
    "A345",
    "A346",
    "A359",
    "A35K",
    "A388",
    "B736",
    "B737",
    "B738",
    "B739",
    "B744",
    "B748",
    "B752",
    "B753",
    "B763",
    "B764",
    "B772",
    "B773",
    "B77L",
    "B77W",
    "B788",
    "B789",
    "B78X",
    "E170",
    "E175",
    "E190",
    "E195",
    "E290",
    "E295",
    "CRJ1",
    "CRJ2",
    "CRJ7",
    "CRJ9",
    "CRJX",
    "ERJ1",
    "ERJ2",
    "ERJ3",
    "ERJ4",
    "LJ35",
    "LJ45",
    "LJ55",
    "LJ60",
    "LJ75",
    "GLF4",
    "GLF5",
    "GLF6",
    "GLEX",
    "FA7X",
    "FA8X",
    "F2TH",
    "F900",
    "C510",
    "C525",
    "C550",
    "C560",
    "C56X",
    "C680",
    "C700",
    "C750",
    "HA420",
    "E55P",
    "E50P",
    "PC24",
}

TURBOPROP_TYPES = {
    "DH8A",
    "DH8B",
    "DH8C",
    "DH8D",
    "AT43",
    "AT45",
    "AT46",
    "AT72",
    "AT75",
    "AT76",
    "PC12",
    "B350",
    "BE20",
    "B190",
    "BE9L",
    "C208",
    "C402",
    "C414",
    "C421",
    "C441",
    "D228",
    "D328",
    "SF34",
    "SW4",
    "JS31",
    "JS32",
    "JS41",
    "E120",
    "F50",
    "ATP",
}

PISTON_TYPES = {
    "C152",
    "C172",
    "C182",
    "C206",
    "C210",
    "PA28",
    "PA32",
    "PA34",
    "PA44",
    "PA46",
    "SR20",
    "SR22",
    "DA20",
    "DA40",
    "DA42",
    "DA62",
    "BE33",
    "BE35",
    "BE36",
    "BE55",
    "BE58",
    "M20P",
    "M20T",
    "AA5",
    "TB20",
    "RV6",
    "RV7",
    "RV8",
    "RV10",
    "P28A",
    "P28R",
    "P32R",
}

HELICOPTER_TYPES = {
    "R22",
    "R44",
    "R66",
    "B06",
    "B206",
    "B407",
    "B412",
    "B429",
    "B505",
    "AS50",
    "AS55",
    "EC20",
    "EC30",
    "EC35",
    "EC45",
    "EC55",
    "H125",
    "H130",
    "H135",
    "H145",
    "H160",
    "H175",
    "H225",
    "A109",
    "A119",
    "A139",
    "A169",
    "A189",
    "S76",
    "S92",
    "UH60",
    "CH47",
    "CH53",
    "MD52",
}

DRONE_TYPES = {"MQ9", "RQ4", "SCAN", "UAV"}
GROUND_TYPES = {"GRND", "VEH", "FOLLOWME", "FIRE", "TOW"}


def classify_aircraft_category(aircraft_type: str | None, model: str | None = None) -> str:
    """Classifies aircraft into one of: JET, TURBOPROP, PISTON, HELICOPTER, DRONE_UAV, GROUND, UNKNOWN."""
    t = (aircraft_type or "").strip().upper()
    m = (model or "").strip().lower()

    if t in JET_TYPES:
        return "JET"
    if t in TURBOPROP_TYPES:
        return "TURBOPROP"
    if t in PISTON_TYPES:
        return "PISTON"
    if t in HELICOPTER_TYPES:
        return "HELICOPTER"
    if t in DRONE_TYPES:
        return "DRONE_UAV"
    if t in GROUND_TYPES:
        return "GROUND"

    # Fallback to model heuristics if type code is unlisted
    if any(
        k in m
        for k in (
            "jet",
            "boeing",
            "airbus",
            "learjet",
            "gulfstream",
            "falcon",
            "citation",
            "challenger",
            "crj",
            "embraer",
        )
    ):
        return "JET"
    if any(k in m for k in ("turboprop", "dash 8", "atr", "king air", "pilatus pc-12", "caravan")):
        return "TURBOPROP"
    if any(
        k in m
        for k in (
            "skyhawk",
            "skylane",
            "piper",
            "cherokee",
            "cirrus",
            "diamond",
            "bonanza",
            "c172",
            "c182",
            "piston",
        )
    ):
        return "PISTON"
    if any(k in m for k in ("helicopter", "rotor", "bell", "eurocopter", "sikorsky", "robinson")):
        return "HELICOPTER"
    if any(k in m for k in ("uav", "drone", "unmanned")):
        return "DRONE_UAV"

    return "UNKNOWN"
