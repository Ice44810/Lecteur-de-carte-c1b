"""Depot des conducteurs."""

from __future__ import annotations

from sqlalchemy import select

from app.database.models import Driver
from app.database.repositories.base import BaseRepository

__all__ = ["DriverRepository"]


class DriverRepository(BaseRepository[Driver]):
    """Acces aux conducteurs, identifies par leur numero de carte."""

    model = Driver

    def get_by_card_number(self, card_number: str) -> Driver | None:
        """Retourne le conducteur portant ce numero de carte, ou ``None``."""
        statement = select(Driver).where(Driver.card_number == card_number)
        return self._session.scalars(statement).first()

    def list_ordered(self, *, limit: int | None = None) -> list[Driver]:
        """Retourne les conducteurs tries par nom puis prenom.

        Les conducteurs dont le nom n'est pas encore connu apparaissent en fin de
        liste, tries par numero de carte.
        """
        statement = select(Driver).order_by(
            Driver.last_name.is_(None),
            Driver.last_name,
            Driver.first_name,
            Driver.card_number,
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement).all())

    def search(self, term: str, *, limit: int = 50) -> list[Driver]:
        """Recherche un conducteur par nom, prenom ou numero de carte.

        Args:
            term: Fragment recherche (insensible a la casse).
            limit: Nombre maximal de resultats.

        Returns:
            Les conducteurs correspondants.
        """
        pattern = f"%{term.strip()}%"
        statement = (
            select(Driver)
            .where(
                Driver.card_number.ilike(pattern)
                | Driver.last_name.ilike(pattern)
                | Driver.first_name.ilike(pattern)
            )
            .order_by(Driver.last_name, Driver.first_name)
            .limit(limit)
        )
        return list(self._session.scalars(statement).all())

    def get_or_create(self, card_number: str, **defaults: object) -> tuple[Driver, bool]:
        """Retourne le conducteur correspondant, en le creant si necessaire.

        Args:
            card_number: Numero de carte, identifiant metier.
            **defaults: Valeurs appliquees uniquement a la creation.

        Returns:
            Un couple ``(conducteur, cree)`` ou ``cree`` vaut ``True`` si
            l'enregistrement vient d'etre ajoute.
        """
        existing = self.get_by_card_number(card_number)
        if existing is not None:
            return existing, False
        driver = Driver(card_number=card_number, **defaults)
        self.add(driver)
        self.flush()
        return driver, True
