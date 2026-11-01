"""SQLAlchemy ORM models.

The declarative base lives here; domain models (equipment, work orders,
evidence) are added by later tasks and will subclass ``Base``.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all Insmart ORM models."""
