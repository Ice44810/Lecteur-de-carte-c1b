"""Service des conducteurs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.config.logging_config import get_logger, mask_card_number
from app.core.exceptions import TachyError
from app.database.models import Driver
from app.database.repositories import ActivityRepository, DriverRepository, ImportRepository
from app.services.base import BaseService

__all__ = ["DriverService", "DriverSummary", "DriverNotFoundError"]

logger = get_logger(__name__)


class DriverNotFoundError(TachyError):
    """Le conducteur demande n'existe pas."""

    default_message = "Ce conducteur n'existe pas."
    default_cause = "La fiche a peut-etre ete supprimee depuis l'ouverture de la liste."
    default_action = "Revenez a la liste des conducteurs et actualisez-la."


@dataclass(frozen=True, slots=True)
class DriverSummary:
    """Vue d'un conducteur destinee a l'interface.

    Attributes:
        id: Identifiant technique.
        card_number: Numero de carte.
        display_name: Libelle affichable.
        first_name: Prenom, si connu.
        last_name: Nom, si connu.
        birth_date: Date de naissance, si connue.
        card_issuing_country: Pays emetteur de la carte, si connu.
        card_expiry_date: Date d'expiration de la carte, si connue.
        files_count: Nombre de fichiers importes rattaches au conducteur.
        activities_count: Nombre de periodes d'activite enregistrees.
        last_activity_end: Fin de la derniere activite connue.
    """

    id: int
    card_number: str
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    birth_date: date | None = None
    card_issuing_country: str | None = None
    card_expiry_date: date | None = None
    files_count: int = 0
    activities_count: int = 0
    last_activity_end: date | None = None

    def card_expiry_status(self, reference: date) -> str:
        """Retourne un libelle d'etat de la carte a une date donnee.

        Args:
            reference: Date d'evaluation.

        Returns:
            ``"Inconnue"``, ``"Expiree"`` ou ``"Valide"``.
        """
        if self.card_expiry_date is None:
            return "Inconnue"
        return "Expiree" if self.card_expiry_date < reference else "Valide"


class DriverService(BaseService):
    """Consultation et gestion des fiches conducteurs."""

    def count(self) -> int:
        """Retourne le nombre de conducteurs suivis."""
        with self._session() as session:
            return DriverRepository(session).count()

    def list_drivers(self, *, limit: int | None = None) -> tuple[DriverSummary, ...]:
        """Retourne les conducteurs, tries par nom.

        Args:
            limit: Nombre maximal de fiches retournees.

        Returns:
            Les fiches conducteurs.
        """
        with self._session() as session:
            drivers = DriverRepository(session).list_ordered(limit=limit)
            return tuple(self._to_summary(session, driver) for driver in drivers)

    def search(self, term: str, *, limit: int = 50) -> tuple[DriverSummary, ...]:
        """Recherche des conducteurs par nom, prenom ou numero de carte.

        Args:
            term: Fragment recherche. Une chaine vide retourne la liste complete.
            limit: Nombre maximal de resultats.

        Returns:
            Les fiches correspondantes.
        """
        if not term.strip():
            return self.list_drivers(limit=limit)
        with self._session() as session:
            drivers = DriverRepository(session).search(term, limit=limit)
            return tuple(self._to_summary(session, driver) for driver in drivers)

    def get(self, driver_id: int) -> DriverSummary:
        """Retourne une fiche conducteur.

        Args:
            driver_id: Identifiant du conducteur.

        Returns:
            La fiche correspondante.

        Raises:
            DriverNotFoundError: Aucun conducteur ne porte cet identifiant.
        """
        with self._session() as session:
            driver = DriverRepository(session).get(driver_id)
            if driver is None:
                raise DriverNotFoundError(technical_detail=f"driver_id={driver_id}")
            return self._to_summary(session, driver)

    def get_by_card_number(self, card_number: str) -> DriverSummary | None:
        """Retourne la fiche d'un conducteur par son numero de carte, ou ``None``."""
        with self._session() as session:
            driver = DriverRepository(session).get_by_card_number(card_number)
            return self._to_summary(session, driver) if driver is not None else None

    def create(
        self,
        *,
        card_number: str,
        first_name: str | None = None,
        last_name: str | None = None,
        card_issuing_country: str | None = None,
        card_expiry_date: date | None = None,
    ) -> DriverSummary:
        """Cree ou complete une fiche conducteur saisie manuellement.

        La saisie manuelle est necessaire tant que le decodage des cartes n'est pas
        disponible : elle permet de preparer le referentiel de l'entreprise. Les
        donnees saisies sont conservees telles quelles et ne seront jamais ecrasees
        silencieusement par un decodage ulterieur.

        Args:
            card_number: Numero de carte, identifiant metier obligatoire.
            first_name: Prenom.
            last_name: Nom de famille.
            card_issuing_country: Pays emetteur de la carte.
            card_expiry_date: Date d'expiration de la carte.

        Returns:
            La fiche creee ou existante.

        Raises:
            ValueError: Le numero de carte est vide.
        """
        normalized = card_number.strip()
        if not normalized:
            raise ValueError("le numero de carte est obligatoire")

        with self._session() as session:
            repository = DriverRepository(session)
            driver, created = repository.get_or_create(
                normalized,
                first_name=first_name or None,
                last_name=last_name or None,
                card_issuing_country=card_issuing_country or None,
                card_expiry_date=card_expiry_date,
            )
            if created:
                logger.info("Conducteur cree (carte %s)", mask_card_number(normalized))
            summary = self._to_summary(session, driver)
        return summary

    # ------------------------------------------------------------------ #
    # Interne
    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_summary(session: object, driver: Driver) -> DriverSummary:
        """Construit un objet de transfert pendant que la session est ouverte."""
        assert hasattr(session, "scalars")
        activity_repository = ActivityRepository(session)  # type: ignore[arg-type]
        import_repository = ImportRepository(session)  # type: ignore[arg-type]
        last_end = activity_repository.latest_activity_datetime(driver.id)
        return DriverSummary(
            id=driver.id,
            card_number=driver.card_number,
            display_name=driver.display_name,
            first_name=driver.first_name,
            last_name=driver.last_name,
            birth_date=driver.birth_date,
            card_issuing_country=driver.card_issuing_country,
            card_expiry_date=driver.card_expiry_date,
            files_count=len(import_repository.list_filtered(driver_id=driver.id)),
            activities_count=len(activity_repository.list_for_driver(driver.id)),
            last_activity_end=last_end.date() if last_end is not None else None,
        )
