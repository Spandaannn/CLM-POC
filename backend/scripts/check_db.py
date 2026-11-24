"""Verify the PostgreSQL connection and check that every table exists.

Run from the backend directory:

    python scripts/check_db.py

Exit code 0 means the database is reachable and the initial migration has
been applied. Exit code 1 means something is missing.
"""

import sys
from pathlib import Path

# Allow "python scripts/check_db.py" to import the app package.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    try:
        # Imported inside main so a missing .env or driver produces a short,
        # readable message instead of a traceback.
        from app.db.health import APP_TABLES, find_missing_tables, get_server_version

        version = get_server_version()
    except Exception as exc:  # connection failures have several underlying types
        print("Database check FAILED")
        print(f"  {type(exc).__name__}: {exc}")
        print()
        print("Check that:")
        print("  1. backend/.env exists and DATABASE_URL is correct")
        print("  2. PostgreSQL is running and reachable")
        print("  3. the PostgreSQL client library (libpq) is available to psycopg")
        return 1

    print("Database connection OK")
    print(f"  {version.splitlines()[0]}")

    missing = find_missing_tables()
    if missing:
        print()
        print("Missing tables: " + ", ".join(sorted(missing)))
        print("Apply the migration with: alembic upgrade head")
        return 1

    print()
    print(f"All {len(APP_TABLES)} application tables are present:")
    for table in sorted(APP_TABLES):
        print(f"  - {table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
