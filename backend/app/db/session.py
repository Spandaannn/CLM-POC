"""SQLAlchemy engine and session handling."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# pool_pre_ping replaces connections that the database has dropped, which is
# common when PostgreSQL or the machine has been idle for a while.
engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Yield one database session per request and always close it.

    FastAPI endpoints can depend on this later. Transactions are not committed
    automatically; the endpoint/service decides when to call commit().
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
