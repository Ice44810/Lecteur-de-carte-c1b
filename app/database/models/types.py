"""Types de colonnes personnalises.

SQLite ne conserve pas le decalage horaire d'une date. Pour garantir qu'une date
relue de la base est strictement identique a celle qui a ete ecrite, le type
:class:`UTCDateTime` normalise systematiquement en UTC a l'ecriture et rattache
le fuseau UTC a la lecture.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Dialect
from sqlalchemy.types import TypeDecorator

__all__ = ["UTCDateTime"]


class UTCDateTime(TypeDecorator[datetime]):
    """Colonne ``DATETIME`` toujours stockee et relue en UTC.

    Un ``datetime`` naif fourni a l'ecriture est considere comme deja exprime en
    UTC, conformement a la convention de l'application.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> datetime | None:
        """Normalise la valeur en UTC avant ecriture."""
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"UTCDateTime attend un datetime, recu {type(value).__name__}")
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        """Rattache le fuseau UTC a la valeur relue."""
        if value is None:
            return None
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
