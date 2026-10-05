"""Enregistrement en base des donnees decodees d'un fichier tachygraphique.

DONNEE DECODEE -> DONNEE METIER : ce module traduit un
:class:`~app.parser.models.ParseResult` en conducteur, vehicules et activites.

Regles appliquees :

* **aucune donnee saisie n'est ecrasee** : une fiche conducteur ou vehicule existante
  n'est completee que sur ses champs vides ;
* **aucune activite n'est enregistree deux fois** : un telechargement couvre en
  general des journees deja importees. Une activite qui chevauche une activite deja
  enregistree pour le meme conducteur est ignoree, sauf si elle prolonge la meme
  activite (meme debut et meme nature), cas d'une journee incomplete au moment du
  telechargement precedent ;
* chaque activite reste rattachee au fichier dont elle provient.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.config.logging_config import get_logger, mask_card_number
from app.core.timeutils import seconds_between
from app.database.models import Activity, Driver, TachographFile
from app.database.repositories import ActivityRepository, DriverRepository, VehicleRepository
from app.parser.models import DecodedDriverIdentification, ParseResult

__all__ = ["StoredData", "store_decoded_data"]

logger = get_logger(__name__)

_DRIVER_FIELDS = (
    "first_name",
    "last_name",
    "birth_date",
    "card_issuing_country",
    "card_issue_date",
    "card_expiry_date",
    "card_validity_begin",
    "card_issuing_authority",
    "preferred_language",
    "licence_number",
    "licence_issuing_authority",
    "licence_issuing_country",
)
"""Champs de la fiche conducteur alimentes par le decodage, s'ils sont vides."""


@dataclass(frozen=True, slots=True)
class StoredData:
    """Bilan de l'enregistrement d'un fichier decode.

    Attributes:
        driver_id: Conducteur rattache, s'il a ete identifie.
        activities_added: Nombre d'activites enregistrees.
        activities_extended: Activites deja connues dont la fin a ete prolongee.
        activities_skipped: Activites deja connues, non enregistrees a nouveau.
        vehicles_added: Nombre de vehicules ajoutes au referentiel.
    """

    driver_id: int | None
    activities_added: int = 0
    activities_extended: int = 0
    activities_skipped: int = 0
    vehicles_added: int = 0

    def summary(self) -> str:
        """Resume lisible de l'enregistrement."""
        parts = [f"{self.activities_added} activite(s) ajoutee(s)"]
        if self.activities_skipped:
            parts.append(f"{self.activities_skipped} deja connue(s)")
        if self.vehicles_added:
            parts.append(f"{self.vehicles_added} vehicule(s) ajoute(s)")
        return ", ".join(parts)


def store_decoded_data(
    session: Session, file_record: TachographFile, result: ParseResult
) -> StoredData:
    """Enregistre le conducteur, les vehicules et les activites d'un fichier decode.

    Args:
        session: Session ouverte par le service appelant (aucune validation ici).
        file_record: Fichier importe, deja enregistre (identifiant connu).
        result: Resultat du decodage.

    Returns:
        Le bilan de l'enregistrement.
    """
    if result.driver is None:
        return StoredData(driver_id=None)

    driver = _driver(session, result.driver)
    file_record.driver_id = driver.id

    vehicles = VehicleRepository(session)
    vehicle_ids: dict[str, int] = {}
    vehicles_added = 0
    for use in result.vehicles_used:
        registration = use.registration.strip().upper()
        if registration in vehicle_ids:
            continue
        vehicle, created = vehicles.get_or_create(
            registration, registration_country=use.registration_country
        )
        vehicles_added += int(created)
        vehicle_ids[registration] = vehicle.id

    added, extended, skipped = _activities(session, driver.id, file_record.id, result, vehicle_ids)
    stored = StoredData(
        driver_id=driver.id,
        activities_added=added,
        activities_extended=extended,
        activities_skipped=skipped,
        vehicles_added=vehicles_added,
    )
    logger.info(
        "Fichier #%s (carte %s) : %s",
        file_record.id,
        mask_card_number(driver.card_number),
        stored.summary(),
    )
    return stored


def _driver(session: Session, decoded: DecodedDriverIdentification) -> Driver:
    """Retrouve ou cree la fiche conducteur, et complete ses champs vides."""
    from app.services.driver_service import normalize_card_number

    repository = DriverRepository(session)
    card_number = normalize_card_number(decoded.card_number)
    values = {field: getattr(decoded, field) for field in _DRIVER_FIELDS}
    driver, created = repository.get_or_create(card_number, **values)
    if not created:
        for field, value in values.items():
            if value is not None and getattr(driver, field) is None:
                setattr(driver, field, value)
    return driver


def _activities(
    session: Session,
    driver_id: int,
    file_id: int,
    result: ParseResult,
    vehicle_ids: dict[str, int],
) -> tuple[int, int, int]:
    """Ajoute les activites nouvelles, en ignorant celles deja connues.

    Returns:
        Le nombre d'activites ajoutees, prolongees et ignorees.
    """
    if not result.activities:
        return 0, 0, 0
    repository = ActivityRepository(session)
    existing = repository.list_for_driver(
        driver_id,
        period_start=min(item.start for item in result.activities),
        period_end=max(item.end for item in result.activities),
    )
    known_items = _KnownActivities(existing)
    by_start = {(item.start_datetime, item.activity_type): item for item in existing}

    added = extended = skipped = 0
    new_items: list[Activity] = []
    for decoded in result.activities:
        start, end = decoded.start, decoded.end
        known = by_start.get((start, decoded.activity_type))
        if known is not None:
            if end > known.end_datetime and not known_items.overlaps(
                known.end_datetime, end, exclude=known
            ):
                known.end_datetime = end
                known.duration_seconds = seconds_between(known.start_datetime, end)
                extended += 1
            else:
                skipped += 1
            continue
        if known_items.overlaps(start, end):
            skipped += 1
            continue
        new_items.append(
            Activity.from_bounds(
                driver_id=driver_id,
                activity_type=decoded.activity_type,
                start_datetime=start,
                end_datetime=end,
                vehicle_id=(
                    vehicle_ids.get(decoded.vehicle_registration.strip().upper())
                    if decoded.vehicle_registration
                    else None
                ),
                source_file_id=file_id,
                card_inserted=decoded.card_inserted,
                manual_entry=decoded.manual_entry,
                crew=decoded.crew,
            )
        )
        added += 1
    repository.add_all(new_items)
    return added, extended, skipped


class _KnownActivities:
    """Activites deja enregistrees, triees, avec recherche de chevauchement rapide.

    ``prefix_end[k]`` est la plus grande fin parmi les ``k + 1`` premieres activites :
    la recherche remonte depuis la position d'insertion et s'arrete des qu'aucune
    activite anterieure ne peut plus atteindre le debut recherche.
    """

    def __init__(self, items: list[Activity]) -> None:
        self.items = sorted(items, key=lambda item: item.start_datetime)
        self.starts = [item.start_datetime for item in self.items]
        self.prefix_end: list[datetime] = []
        for item in self.items:
            last = self.prefix_end[-1] if self.prefix_end else item.end_datetime
            self.prefix_end.append(max(last, item.end_datetime))

    def overlaps(self, start: datetime, end: datetime, *, exclude: Activity | None = None) -> bool:
        """Indique si ``[start, end[`` chevauche une activite connue (hors ``exclude``)."""
        index = bisect.bisect_left(self.starts, end) - 1
        while index >= 0 and self.prefix_end[index] > start:
            item = self.items[index]
            if item is not exclude and item.end_datetime > start:
                return True
            index -= 1
        return False
