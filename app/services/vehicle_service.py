"""Service des vehicules."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.logging_config import get_logger
from app.core.exceptions import TachyError
from app.database.models import Vehicle
from app.database.repositories import ActivityRepository, VehicleRepository
from app.services.base import BaseService

__all__ = ["VehicleService", "VehicleSummary", "VehicleNotFoundError", "VehicleConflictError"]

logger = get_logger(__name__)


class VehicleNotFoundError(TachyError):
    """Le vehicule demande n'existe pas."""

    default_message = "Ce vehicule n'existe pas."
    default_cause = "La fiche a peut-etre ete supprimee depuis l'ouverture de la liste."
    default_action = "Revenez a la liste des vehicules et actualisez-la."


class VehicleConflictError(TachyError):
    """La saisie contredit une fiche vehicule existante."""

    default_message = "Ce vehicule est deja enregistre avec d'autres informations."
    default_cause = (
        "L'immatriculation ou le VIN saisi correspond a une fiche existante dont les "
        "informations different de celles saisies."
    )
    default_action = "Verifiez la saisie. La fiche existante n'a pas ete modifiee."


def _clean(value: str | None, *, upper: bool = False) -> str | None:
    """Retire les espaces superflus et convertit une chaine vide en ``None``."""
    if value is None:
        return None
    cleaned = value.strip()
    if upper:
        cleaned = cleaned.upper()
    return cleaned or None


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
        in_fleet: Appartenance confirmee a la flotte (``False`` : fiche creee par un
            import, a confirmer).
    """

    id: int
    registration: str
    registration_country: str | None = None
    vin: str | None = None
    tachograph_identifier: str | None = None
    activities_count: int = 0
    in_fleet: bool = False

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
        """Cree, complete ou retourne une fiche vehicule.

        Si l'immatriculation existe deja, seuls les champs encore vides de la fiche
        sont completes ; une valeur contradictoire est refusee. Un VIN deja attribue
        a un autre vehicule est egalement refuse avec un message explicite.

        Args:
            registration: Immatriculation, identifiant metier obligatoire.
            registration_country: Pays d'immatriculation.
            vin: Numero d'identification du vehicule.
            tachograph_identifier: Identifiant de l'unite embarquee.

        Returns:
            La fiche creee ou existante.

        Raises:
            ValueError: L'immatriculation est vide.
            VehicleConflictError: La saisie contredit une fiche existante, ou le VIN
                est deja attribue a un autre vehicule.
        """
        normalized = registration.strip().upper()
        if not normalized:
            raise ValueError("l'immatriculation est obligatoire")

        values: dict[str, str | None] = {
            "registration_country": _clean(registration_country, upper=True),
            "vin": _clean(vin, upper=True),
            "tachograph_identifier": _clean(tachograph_identifier),
        }

        with self._session() as session:
            repository = VehicleRepository(session)
            if values["vin"] is not None:
                owner = repository.get_by_vin(values["vin"])
                if owner is not None and owner.registration != normalized:
                    raise VehicleConflictError(
                        "Ce VIN est deja attribue a un autre vehicule.",
                        cause=f"Le VIN saisi figure sur la fiche du vehicule {owner.registration}.",
                        technical_detail=f"vin en conflit avec vehicle_id={owner.id}",
                    )
            vehicle, created = repository.get_or_create(normalized, **values)
            if created:
                logger.info("Vehicule cree : %s", normalized)
            else:
                self._complete(vehicle, values)
            # Une saisie explicite vaut confirmation de l'appartenance a la flotte.
            vehicle.in_fleet = True
            return self._to_summary(session, vehicle)

    def set_in_fleet(self, vehicle_id: int, in_fleet: bool) -> VehicleSummary:
        """Confirme ou retire l'appartenance d'un vehicule a la flotte.

        Raises:
            VehicleNotFoundError: Aucun vehicule ne porte cet identifiant.
        """
        with self._session() as session:
            vehicle = VehicleRepository(session).get(vehicle_id)
            if vehicle is None:
                raise VehicleNotFoundError(technical_detail=f"vehicle_id={vehicle_id}")
            vehicle.in_fleet = True if in_fleet else None
            return self._to_summary(session, vehicle)

    @staticmethod
    def _complete(vehicle: Vehicle, values: dict[str, str | None]) -> None:
        """Complete les champs vides d'une fiche existante, sans jamais en ecraser.

        Raises:
            VehicleConflictError: Une valeur saisie contredit la valeur enregistree.
        """
        conflicts = [
            field_name
            for field_name, value in values.items()
            if value is not None
            and getattr(vehicle, field_name) is not None
            and getattr(vehicle, field_name).casefold() != value.casefold()
        ]
        if conflicts:
            raise VehicleConflictError(
                technical_detail=f"vehicule {vehicle.registration} : champs en conflit {conflicts}"
            )
        for field_name, value in values.items():
            if value is not None and getattr(vehicle, field_name) is None:
                setattr(vehicle, field_name, value)

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
            activities_count=repository.count_for_vehicle(vehicle.id),
            in_fleet=bool(vehicle.in_fleet),
        )
