"""
Declarative base + naming convention for all SQLAlchemy models.

Why a custom naming convention? Two reasons:
1. Auto-generated constraint names are stable across migrations (Alembic
   won't generate surprise diffs).
2. Error messages from PostgreSQL reference predictable names.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """All PanelMind ORM models inherit from this."""

    metadata = metadata

    # Subclasses can override these defaults. We use timezone-aware UTC
    # everywhere — never naive datetimes.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover — debug helper
        cls = type(self).__name__
        attrs = ", ".join(
            f"{k}={v!r}"
            for k, v in self.__dict__.items()
            if not k.startswith("_") and not callable(v)
        )
        return f"{cls}({attrs})"

    def to_dict(self) -> dict[str, Any]:
        """Serialise the row to a plain dict. Excludes SQLAlchemy internals."""
        out: dict[str, Any] = {}
        for col in self.__table__.columns:
            val = getattr(self, col.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            out[col.name] = val
        return out
