"""Depot des vehicules."""

from __future__ import annotations

from sqlalchemy import select

from app.database.models import Vehicle
from app.database.repositories.base import BaseRepository

__all__ = ["VehicleRepository"]


class VehicleRepository(BaseRepository[Vehicle]):
    """Acces aux vehicules, identifies par leur immatriculation."""

    model = Vehicle

    def get_by_registration(self, registration: str) -> Vehicle | None:
        """Retourne le vehicule portant cette immatriculation, ou ``None``."""
        statement = select(Vehicle).where(Vehicle.registration == registration)
        return self._session.scalars(statement).first()

    def get_by_vin(self, vin: str) -> Vehicle | None:
        """Retourne le vehicule portant ce VIN, ou ``None``."""
        statement = select(Vehicle).where(Vehicle.vin == vin)
        return self._session.scalars(statement).first()

    def list_ordered(self, *, limit: int | None = None) -> list[Vehicle]:
        """Retourne les vehicules tries par immatriculation."""
        statement = select(Vehicle).order_by(Vehicle.registration)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement).all())

    def get_or_create(self, registration: str, **defaults: object) -> tuple[Vehicle, bool]:
        """Retourne le vehicule correspondant, en le creant si necessaire.

        Args:
            registration: Immatriculation, identifiant metier.
            **defaults: Valeurs appliquees uniquement a la creation.

        Returns:
            Un couple ``(vehicule, cree)``.
        """
        existing = self.get_by_registration(registration)
        if existing is not None:
            return existing, False
        vehicle = Vehicle(registration=registration, **defaults)
        self.add(vehicle)
        self.flush()
        return vehicle, True
