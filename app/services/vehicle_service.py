"""Service des vehicules."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.logging_config import get_logger
from app.core.exceptions import TachyError
from app.database.models import Vehicle
from app.database.repositories import ActivityRepository, VehicleRepository
from app.services.base import BaseService

__all__ = ["VehicleService", "VehicleSummary", "VehicleNotFoundError"]

logger = get_logger(__name__)


class VehicleNotFoundError(TachyError):
    """Le vehicule demande n'existe pas."""

    default_message = "Ce vehicule n'existe pas."
    default_cause = "La fiche a peut-etre ete supprimee depuis l'ouverture de la liste."
    default_action = "Revenez a la liste des vehicules et actualisez-la."


@dataclass(frozen=True, slots=True)
class VehicleSummary:
    """Vue d'un vehicule destinee a l'interface.

    Attributes:
        id: Identifiant technique.
        registration: Immatriculation.
        registration_country: Pays d'immatriculation, si connu.
        vin: Numero d'identification du vehicule, si connu.
        tachograph_identifier: Identifiant de l'unite embarquee, si connu.
        activities_count: Nombre d'activites rattachees.
    """

    id: int
    registration: str
    registration_country: str | None = None
    vin: str | None = None
    tachograph_identifier: str | None = None
    activities_count: int = 0

    @property
    def display_name(self) -> str:
        """Libelle affichable du vehicule."""
        return self.registration


class VehicleService(BaseService):
    """Consultation et gestion des fiches vehicules."""

    def count(self) -> int:
        """Retourne le nombre de vehicules enregistres."""
        with self._session() as session:
            return VehicleRepository(session).count()

    def list_vehicles(self, *, limit: int | None = None) -> tuple[VehicleSummary, ...]:
        """Retourne les vehicules, tries par immatriculation."""
        with self._session() as session:
            vehicles = VehicleRepository(session).list_ordered(limit=limit)
            return tuple(self._to_summary(session, vehicle) for vehicle in vehicles)

    def get(self, vehicle_id: int) -> VehicleSummary:
        """Retourne une fiche vehicule.

        Args:
            vehicle_id: Identifiant du vehicule.

        Returns:
            La fiche correspondante.

        Raises:
            VehicleNotFoundError: Aucun vehicule ne porte cet identifiant.
        """
        with self._session() as session:
            vehicle = VehicleRepository(session).get(vehicle_id)
            if vehicle is None:
                raise VehicleNotFoundError(technical_detail=f"vehicle_id={vehicle_id}")
            return self._to_summary(session, vehicle)

    def create(
        self,
        *,
        registration: str,
        registration_country: str | None = None,
        vin: str | None = None,
        tachograph_identifier: str | None = None,
    ) -> VehicleSummary:
        """Cree ou retourne une fiche vehicule.

        Args:
            registration: Immatriculation, identifiant metier obligatoire.
            registration_country: Pays d'immatriculation.
            vin: Numero d'identification du vehicule.
            tachograph_identifier: Identifiant de l'unite embarquee.

        Returns:
            La fiche creee ou existante.

        Raises:
            ValueError: L'immatriculation est vide.
        """
        normalized = registration.strip().upper()
        if not normalized:
            raise ValueError("l'immatriculation est obligatoire")

        with self._session() as session:
            vehicle, created = VehicleRepository(session).get_or_create(
                normalized,
                registration_country=registration_country or None,
                vin=vin or None,
                tachograph_identifier=tachograph_identifier or None,
            )
            if created:
                logger.info("Vehicule cree : %s", normalized)
            return self._to_summary(session, vehicle)

    @staticmethod
    def _to_summary(session: object, vehicle: Vehicle) -> VehicleSummary:
        """Construit un objet de transfert pendant que la session est ouverte."""
        repository = ActivityRepository(session)  # type: ignore[arg-type]
        return VehicleSummary(
            id=vehicle.id,
            registration=vehicle.registration,
            registration_country=vehicle.registration_country,
            vin=vehicle.vin,
            tachograph_identifier=vehicle.tachograph_identifier,
            activities_count=len(repository.list_for_vehicle(vehicle.id)),
        )
