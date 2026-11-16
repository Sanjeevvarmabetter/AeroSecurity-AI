#!/usr/bin/env python3
"""Download public datasets into datasets/raw (never executed or extracted here).

  OurAirports airports.csv                       (public domain)
  OpenSky aircraft database 2025-08 (~108 MB, crowdsourced, 'as is')
  OpenSky incident extracts (5 aircraft)         (CC BY 4.0, Schaefer et al. 2014)
"""

import sys
from pathlib import Path

import httpx

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
FILES = {
    "airports.csv": ("https://davidmegginson.github.io/ourairports-data/airports.csv", 64 << 20),
    "opensky-aircraft-db-2025-08.csv": (
        "https://s3.opensky-network.org/data-samples/metadata/aircraft-database-complete-2025-08.csv",
        160 << 20,
    ),
    "incident-n722bd_2026-11-01_florida.tar.gz": (
        "https://s3.opensky-network.org/data-samples/incident-data/n722bd_2026-11-01_florida.tar.gz", 16 << 20),
    "incident-n931tt_2026-10-13_wisconsin.tar.gz": (
        "https://s3.opensky-network.org/data-samples/incident-data/n931tt_2026-10-13_wisconsin.tar.gz", 16 << 20),
    "incident-os82_2026-10-18_telaviv-sofia-vienna.tar.gz": (
        "https://s3.opensky-network.org/data-samples/incident-data/os82_2026-10-18_telaviv-sofia-vienna.tar.gz", 16 << 20),
    "incident-xauci_2025-01-31_philadelphia.tar.gz": (
        "https://s3.opensky-network.org/data-samples/incident-data/xauci_2025-01-31_philadelphia.tar.gz", 16 << 20),
    "opensky-fz1073_2026-09-30.tar.gz": (
        "https://s3.opensky-network.org/data-samples/incident-data/fz1073_2026-09-30_dubai-tabuk.tar.gz",
        16 << 20,
    ),
}


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, (url, cap) in FILES.items():
        dest = RAW / name
        if dest.exists():
            print(f"skip {name} (exists)")
            continue
        size = 0
        with httpx.stream("GET", url, timeout=60, follow_redirects=False) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > cap:
                        dest.unlink()
                        print(f"abort {name}: exceeds {cap} bytes", file=sys.stderr)
                        return 1
                    f.write(chunk)
        print(f"ok   {name} ({size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
