"""Depot generique.

Convention de transaction : **un depot ne valide jamais la transaction**. Il
travaille sur la ``Session`` qui lui est fournie ; c'est le service appelant qui
ouvre et valide l'unite de travail (``with database.session() as session:``). Cette
regle evite les commits partiels lors d'un import qui touche plusieurs tables.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.base import Base

__all__ = ["BaseRepository", "ModelT"]

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Operations communes a tous les depots.

    Args:
        session: Session SQLAlchemy active, fournie par le service appelant.
    """

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        if not hasattr(self, "model"):  # pragma: no cover - erreur de programmation
            raise TypeError(f"{type(self).__name__} doit definir un attribut de classe 'model'")
        self._session = session

    @property
    def session(self) -> Session:
        """Session utilisee par ce depot."""
        return self._session

    # ------------------------------------------------------------------ #
    # Lecture
    # ------------------------------------------------------------------ #
    def get(self, entity_id: int) -> ModelT | None:
        """Retourne une entite par sa cle primaire, ou ``None``."""
        return self._session.get(self.model, entity_id)

    def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[ModelT]:
        """Retourne toutes les entites, avec pagination optionnelle.

        Args:
            limit: Nombre maximal d'elements retournes.
            offset: Nombre d'elements ignores en tete.

        Returns:
            La liste des entites.
        """
        statement = select(self.model).offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement).all())

    def count(self) -> int:
        """Retourne le nombre total d'entites."""
        statement = select(func.count()).select_from(self.model)
        return int(self._session.scalar(statement) or 0)

    def exists(self, entity_id: int) -> bool:
        """Indique si une entite existe pour cette cle primaire."""
        return self.get(entity_id) is not None

    # ------------------------------------------------------------------ #
    # Ecriture
    # ------------------------------------------------------------------ #
    def add(self, entity: ModelT) -> ModelT:
        """Ajoute une entite a la session (sans validation de transaction)."""
        self._session.add(entity)
        return entity

    def add_all(self, entities: Sequence[ModelT]) -> list[ModelT]:
        """Ajoute plusieurs entites a la session."""
        items = list(entities)
        self._session.add_all(items)
        return items

    def flush(self) -> None:
        """Force l'envoi des ecritures en attente (pour obtenir les identifiants)."""
        self._session.flush()

    def update(self, entity: ModelT, **values: Any) -> ModelT:
        """Met a jour les attributs fournis d'une entite.

        Args:
            entity: Entite deja rattachee a la session.
            **values: Attributs a modifier.

        Returns:
            L'entite modifiee.

        Raises:
            AttributeError: Un attribut inconnu a ete fourni.
        """
        for key, value in values.items():
            if not hasattr(entity, key):
                raise AttributeError(f"{type(entity).__name__} n'a pas d'attribut '{key}'")
            setattr(entity, key, value)
        return entity

    def delete(self, entity: ModelT) -> None:
        """Supprime une entite.

        Reserve aux corrections explicites demandees par l'utilisateur :
        l'application ne supprime jamais de donnee automatiquement.
        """
        self._session.delete(entity)
