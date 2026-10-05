"""Base declarative SQLAlchemy et mixins communs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.database.models.types import UTCDateTime

__all__ = ["Base", "TimestampMixin", "NAMING_CONVENTION"]

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Convention de nommage des contraintes.

Des noms deterministes sont indispensables pour ecrire des migrations fiables :
sans cela, SQLite genere des noms anonymes impossibles a cibler.
"""


class Base(DeclarativeBase):
    """Classe de base de tous les modeles ORM."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def to_dict(self, *, exclude: set[str] | None = None) -> dict[str, Any]:
        """Retourne les colonnes de l'instance sous forme de dictionnaire.

        Utilise par les rapports et la future serialisation API. Les relations ne
        sont pas incluses, afin d'eviter tout chargement implicite.

        Args:
            exclude: Noms de colonnes a omettre.

        Returns:
            Un dictionnaire ``nom_de_colonne -> valeur``.
        """
        skipped = exclude or set()
        return {
            column.key: getattr(self, column.key)
            for column in self.__table__.columns
            if column.key not in skipped
        }

    def __repr__(self) -> str:
        """Representation technique courte, sans donnee personnelle."""
        identifier = getattr(self, "id", None)
        return f"<{type(self).__name__} id={identifier}>"


class TimestampMixin:
    """Ajoute les colonnes de tracabilite ``created_at`` et ``updated_at``.

    Les horodatages sont produits par la base (``CURRENT_TIMESTAMP``) afin de
    rester coherents meme si plusieurs processus ecrivent.
    """

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        doc="Date de creation de l'enregistrement (UTC).",
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        doc="Date de derniere modification de l'enregistrement (UTC).",
    )
