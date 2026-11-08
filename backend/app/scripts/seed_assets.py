"""Assets seed loader.

Reads tickers from an owner-provided config file (``assets_seed.json``) and
inserts them into the ``assets`` table as PENDING (``confirmed=False``). This
loader invents no tickers: it only ever seeds what the owner has placed in the
config file. If the file is absent or empty, it seeds nothing and exits 0.

Run inside the backend container:
    python -m app.scripts.seed_assets [--config /path/to/assets_seed.json]
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.logging import get_logger, setup_logging
from app.database.models import Asset

log = get_logger("app.scripts.seed_assets")

DEFAULT_CONFIG = "assets_seed.json"


def load_seed(path: str) -> list[dict]:
    """Load the owner-provided asset list. Missing/empty file -> [] (no invention)."""
    p = Path(path)
    if not p.exists():
        log.warning("seed config %s not found — seeding nothing", path)
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    assets = data.get("assets", []) if isinstance(data, dict) else data
    return assets if isinstance(assets, list) else []


def seed(session_factory, config_path: str = DEFAULT_CONFIG) -> int:
    rows = load_seed(config_path)
    if not rows:
        log.info("no assets to seed (config %s is empty or absent)", config_path)
        return 0

    # Load existing so we never create duplicates (idempotent seed).
    with session_factory() as session:
        existing = {
            (a.exchange, a.ticker)
            for a in session.execute(
                select(Asset.exchange, Asset.ticker)
            ).all()
        }
        added = 0
        for r in rows:
            exchange = r.get("exchange")
            ticker = str(r.get("ticker"))
            if not exchange or not ticker:
                log.warning("skipping malformed seed row (missing exchange/ticker): %r", r)
                continue
            if (exchange, ticker) in existing:
                continue
            session.add(
                Asset(
                    exchange=exchange,
                    ticker=ticker,
                    name=r.get("name"),
                    provider_ticker=r.get("provider_ticker"),
                    provider_symbol_format=r.get("provider_symbol_format"),
                    market_data_provider=r.get("market_data_provider"),
                    # Owner confirms pending; seed marks confirmed=False unless the
                    # config explicitly says confirmed:true.
                    confirmed=bool(r.get("confirmed", False)),
                )
            )
            existing.add((exchange, ticker))
            added += 1
        session.commit()

    log.info(
        "seeded %d new assets (%d rows in config, %d pre-existing skipped)",
        added,
        len(rows),
        len(rows) - added,
    )
    return added


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="Seed assets from owner config")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="path to assets_seed.json")
    args = parser.parse_args()

    from app.database.engine import get_shared_engine
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=get_shared_engine(), expire_on_commit=False)
    seed(session_factory, args.config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
