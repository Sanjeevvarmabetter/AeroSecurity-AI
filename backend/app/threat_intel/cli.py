"""python -m app.threat_intel.cli arxiv "ADS-B security" --max 6"""

import argparse
import json
import sys

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_engine
from app.core.logging import configure_logging
from app.core.security import Principal, Role
from app.threat_intel import service
from app.threat_intel.arxiv import ArxivError


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aerosec-intel")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("arxiv", help="import abstracts from arXiv's public API")
    a.add_argument("query")
    a.add_argument("--max", type=int, default=6, dest="max_results")
    args = p.parse_args(argv)
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    try:
        with Session(get_engine()) as session:
            print(
                json.dumps(
                    service.import_arxiv(session, Principal(Role.ADMIN, "cli"), args.query, args.max_results)
                )
            )
    except (ArxivError, service.IntelError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
