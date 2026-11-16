"""python -m app.detection.cli run [--rule DET-001 ...] [--icao24 abc123] [--start ISO --end ISO]"""

import argparse
import json
import sys
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_engine
from app.core.logging import configure_logging
from app.detection.engine import run_detection, summarize_anomalies


def _dt(v: str) -> datetime:
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamps need a timezone, e.g. 2026-09-30T00:00:00Z")
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aerosec-detect")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run detection rules and persist anomalies")
    r.add_argument("--rule", action="append", dest="rules")
    r.add_argument("--icao24")
    r.add_argument("--start", type=_dt)
    r.add_argument("--end", type=_dt)
    sub.add_parser("summary", help="count stored anomalies")
    args = p.parse_args(argv)
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    try:
        with Session(get_engine()) as session:
            if args.cmd == "summary":
                print(json.dumps({k: dict(v) for k, v in summarize_anomalies(session).items()}, indent=2))
            else:
                rep = run_detection(
                    session,
                    rule_ids=args.rules,
                    icao24=args.icao24,
                    start=args.start,
                    end=args.end,
                    actor="cli",
                )
                print(json.dumps(rep.as_dict(), indent=2))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
