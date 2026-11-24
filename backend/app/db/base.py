"""Declarative base shared by every SQLAlchemy model."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Explicit names make migrations, indexes, and constraints predictable.
# Check constraints are always given a full name in the models, so no "ck"
# entry is needed here.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
