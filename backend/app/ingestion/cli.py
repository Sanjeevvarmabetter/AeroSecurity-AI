"""Operator CLI: python -m app.ingestion.cli <command>."""

import argparse
import json
import logging
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_engine
from app.core.logging import configure_logging
from app.ingestion.aircraft_metadata import import_aircraft_metadata
from app.ingestion.airports import import_airports
from app.ingestion.opensky_api import OpenSkyApiProvider
from app.ingestion.opensky_csv import OpenSkyCsvProvider
from app.ingestion.poller import poll
from app.ingestion.schema import ImportReport
from app.ingestion.service import ingest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aerosec-ingest")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("opensky-csv", help="import an OpenSky state_vectors_data4 CSV or .tar.gz extract")
    c.add_argument("path", type=Path)
    a = sub.add_parser("airports", help="import OurAirports airports.csv")
    a.add_argument("path", type=Path)
    m = sub.add_parser(
        "aircraft-metadata", help="enrich observed aircraft from the OpenSky aircraft database CSV"
    )
    m.add_argument("path", type=Path)
    o = sub.add_parser("opensky-api", help="poll OpenSky REST API (source must be enabled by an operator)")
    o.add_argument("--bbox", type=float, nargs=4, metavar=("LAMIN", "LOMIN", "LAMAX", "LOMAX"), required=True)
    o.add_argument("--polls", type=int, default=1, help="number of polls; 0 = keep polling until stopped")
    o.add_argument(
        "--interval", type=float, default=300.0, help="seconds between polls (anonymous credits are scarce)"
    )
    args = p.parse_args(argv)

    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    try:
        with Session(get_engine()) as session:
            if args.cmd == "airports":
                reports = [import_airports(session, args.path, actor="cli")]
            elif args.cmd == "aircraft-metadata":
                reports = [import_aircraft_metadata(session, args.path, actor="cli")]
            elif args.cmd == "opensky-csv":
                reports = [
                    ingest(
                        session, OpenSkyCsvProvider(args.path), batch_size=s.ingest_batch_size, actor="cli"
                    )
                ]
            else:
                provider = OpenSkyApiProvider(s, bbox=tuple(args.bbox))
                reports = []

                def show(r: ImportReport) -> None:
                    print(json.dumps(r.as_dict()), flush=True)

                poll(
                    lambda: Session(get_engine()),
                    provider,
                    polls=args.polls,
                    interval_s=max(args.interval, s.opensky_min_interval_s),
                    on_report=show,
                )
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        logging.getLogger(__name__).error("ingestion failed: %s", type(exc).__name__)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for r in reports:
        print(json.dumps(r.as_dict()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
