"""Backend container entrypoint.

Decision (documented in CLAUDE.md): run ``alembic upgrade head`` ONLY when at
least one migration revision exists on disk. Phase 1 has no revisions, so the
step is a clean, logged skip — a missing revision file must never fail
startup. From Phase 2 onward the same code path migrates automatically.

Then start uvicorn. No secrets are printed.
"""

import os
import sys
from pathlib import Path


def _alembic_has_revisions() -> bool:
    # In the image: /app/app/scripts/entrypoint.py -> parents[1] is /app/app
    versions_dir = Path(__file__).resolve().parents[1] / "database" / "migrations" / "versions"
    if not versions_dir.is_dir():
        return False
    return any(p.suffix == ".py" and p.name != "__init__.py" for p in versions_dir.iterdir())


def _run_migrations() -> None:
    if _alembic_has_revisions():
        import alembic  # imported lazily so the check stays cheap
        from alembic.config import Config as AlembicConfig

        # In the image alembic.ini sits at /app/alembic.ini (parents[2]).
        cfg = AlembicConfig(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        cfg.set_main_option("script_location", "app/database/migrations")
        import app.database  # ensure models are importable for autogenerate in Phase 2+

        from alembic import command

        command.upgrade(cfg, "head")
    else:
        print("[entrypoint] no Alembic revisions present — skipping migrations (Phase 1)")


def main() -> int:
    _run_migrations()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
