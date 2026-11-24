"""Small helpers for verifying the database connection and schema."""

from sqlalchemy import inspect, text

from app.db.session import engine

# Tables created by the initial migration (alembic_version is managed by Alembic).
APP_TABLES = frozenset(
    {
        "users",
        "contracts",
        "contract_documents",
        "approvals",
        "review_results",
        "obligations",
        "audit_events",
        "user_sessions",
    }
)


def ping_database() -> None:
    """Open a connection and execute a minimal query."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def get_server_version() -> str:
    """Open a connection and return PostgreSQL's version string."""
    with engine.connect() as connection:
        return connection.execute(text("SELECT version()")).scalar_one()


def get_existing_tables() -> set[str]:
    """Return the table names currently present in the database."""
    return set(inspect(engine).get_table_names())


def find_missing_tables() -> set[str]:
    """Return application tables that the database does not yet have."""
    return APP_TABLES - get_existing_tables()
