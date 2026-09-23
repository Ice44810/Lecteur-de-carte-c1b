"""Service d'import des fichiers tachygraphiques.

Flux cible (section 6 du cahier des charges) :

.. code-block:: text

    selection du fichier -> validation de l'extension -> calcul du SHA-256
    -> controle de doublon -> copie du fichier original (immuable)
    -> decodage -> validation -> enregistrement en base -> analyse -> resultat

ETAT D'AVANCEMENT

* **Implemente** : :meth:`ImportService.inspect`, qui realise toutes les etapes
  **en lecture seule** : validation de l'extension, lecture de la taille, calcul de
  l'empreinte SHA-256 et detection de doublon. Cette methode n'ecrit rien, ni sur le
  disque ni en base, et permet a l'interface d'informer l'utilisateur avant toute
  action.
* **Implemente** : :meth:`ImportService.history` et :meth:`ImportService.get_details`,
  qui alimentent la page « Historique des telechargements ».
* **Non implemente (phase 3)** : :meth:`ImportService.import_file`, qui effectue les
  ecritures (copie archivee, enregistrement en base, declenchement de l'analyse).

Ce decoupage est volontaire : la phase 1 livre le socle et ne doit pas ecrire de
donnees metier. L'ordre des phases est defini en section 29 du cahier des charges.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config.logging_config import get_logger
from app.core.enums import FileType, ParsingStatus
from app.core.exceptions import StorageError
from app.core.hashing import sha256_file
from app.database.models import TachographFile
from app.database.repositories import ImportRepository
from app.parser import detect_file_type
from app.services.base import BaseService

__all__ = ["ImportService", "FileInspection", "ImportRecord"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FileInspection:
    """Resultat de l'examen d'un fichier avant import (lecture seule).

    Attributes:
        path: Chemin du fichier examine.
        filename: Nom du fichier.
        file_type: Type detecte d'apres l'extension.
        file_size: Taille en octets.
        sha256: Empreinte SHA-256 du contenu.
        is_duplicate: Indique qu'un fichier de meme contenu est deja importe.
        existing_file_id: Identifiant de l'import existant, le cas echeant.
        existing_imported_at: Date de l'import existant, le cas echeant.
        decoding_available: Indique si le decodage de ce format est disponible.
    """

    path: Path
    filename: str
    file_type: FileType
    file_size: int
    sha256: str
    is_duplicate: bool
    existing_file_id: int | None = None
    existing_imported_at: datetime | None = None
    decoding_available: bool = False

    @property
    def duplicate_message(self) -> str | None:
        """Message a afficher lorsque le fichier a deja ete importe.

        Returns:
            Un message de la forme ``"Ce fichier a deja ete importe le 20/09/2026."``,
            ou ``None`` si le fichier est nouveau.
        """
        if not self.is_duplicate:
            return None
        if self.existing_imported_at is None:  # pragma: no cover - incoherence de donnees
            return "Ce fichier a deja ete importe."
        return f"Ce fichier a deja ete importe le {self.existing_imported_at.strftime('%d/%m/%Y')}."

    @property
    def human_size(self) -> str:
        """Taille lisible du fichier."""
        size = float(self.file_size)
        for unit in ("o", "Ko", "Mo", "Go"):
            if size < 1024 or unit == "Go":
                return f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} Go"  # pragma: no cover - inatteignable


@dataclass(frozen=True, slots=True)
class ImportRecord:
    """Ligne du journal des telechargements destinee a l'interface.

    Attributes:
        id: Identifiant technique.
        imported_at: Date et heure de l'import (UTC).
        filename: Nom du fichier importe.
        file_type: Type de telechargement.
        file_size: Taille en octets.
        human_size: Taille lisible.
        sha256: Empreinte complete.
        short_sha256: Debut de l'empreinte, pour affichage compact.
        parsing_status: Etat du decodage.
        parsing_error: Message d'erreur eventuel.
        original_path: Chemin de la copie archivee.
        driver_display_name: Conducteur rattache, si connu.
        vehicle_registration: Vehicule rattache, si connu.
    """

    id: int
    imported_at: datetime
    filename: str
    file_type: FileType
    file_size: int
    human_size: str
    sha256: str
    short_sha256: str
    parsing_status: ParsingStatus
    parsing_error: str | None
    original_path: str
    driver_display_name: str | None = None
    vehicle_registration: str | None = None

    @property
    def directory(self) -> Path:
        """Repertoire contenant la copie archivee."""
        return Path(self.original_path).parent


class ImportService(BaseService):
    """Import et consultation des fichiers tachygraphiques."""

    # ------------------------------------------------------------------ #
    # Examen prealable (lecture seule)
    # ------------------------------------------------------------------ #
    def inspect(self, path: Path | str) -> FileInspection:
        """Examine un fichier sans rien ecrire.

        Realise les etapes non destructives du flux d'import : validation de
        l'extension, lecture de la taille, calcul de l'empreinte SHA-256 et
        recherche d'un doublon. Le fichier source n'est ouvert qu'en lecture.

        Args:
            path: Chemin du fichier a examiner.

        Returns:
            Le resultat de l'examen.

        Raises:
            UnsupportedFileTypeError: L'extension n'est ni ``.C1B`` ni ``.V1B``.
            StorageError: Le fichier est introuvable ou illisible.
        """
        file_path = Path(path).expanduser()
        file_type = detect_file_type(file_path.name)

        try:
            file_size = file_path.stat().st_size
        except FileNotFoundError as exc:
            raise StorageError(
                f"Le fichier {file_path.name} est introuvable.",
                cause="Le fichier a ete deplace ou supprime depuis sa selection.",
                action="Selectionnez a nouveau le fichier.",
                technical_detail=str(exc),
            ) from exc
        except OSError as exc:
            raise StorageError(
                f"Le fichier {file_path.name} n'a pas pu etre lu.",
                cause="Les droits d'acces sont insuffisants.",
                action="Verifiez les permissions du fichier.",
                technical_detail=str(exc),
            ) from exc

        digest = sha256_file(file_path)
        logger.info(
            "Examen du fichier %s : type %s, %d octets, empreinte calculee",
            file_path.name,
            file_type.value,
            file_size,
        )

        with self._session() as session:
            existing = ImportRepository(session).get_by_sha256(digest)
            existing_id = existing.id if existing is not None else None
            existing_date = existing.imported_at if existing is not None else None

        if existing_id is not None:
            logger.info("Fichier %s deja importe (import #%s)", file_path.name, existing_id)

        from app.parser import get_parser_for

        parser_class = get_parser_for(file_type)
        probe = parser_class(b"", filename=file_path.name)

        return FileInspection(
            path=file_path,
            filename=file_path.name,
            file_type=file_type,
            file_size=file_size,
            sha256=digest,
            is_duplicate=existing_id is not None,
            existing_file_id=existing_id,
            existing_imported_at=existing_date,
            decoding_available=probe.decoding_available,
        )

    # ------------------------------------------------------------------ #
    # Journal des telechargements
    # ------------------------------------------------------------------ #
    def count(self) -> int:
        """Retourne le nombre total de fichiers importes."""
        with self._session() as session:
            return ImportRepository(session).count()

    def count_by_type(self, file_type: FileType) -> int:
        """Retourne le nombre de fichiers importes d'un type donne."""
        with self._session() as session:
            return ImportRepository(session).count_by_type(file_type)

    def last_import_datetime(self) -> datetime | None:
        """Retourne la date du dernier telechargement importe, ou ``None``."""
        with self._session() as session:
            return ImportRepository(session).last_import_datetime()

    def history(
        self,
        *,
        file_type: FileType | None = None,
        parsing_status: ParsingStatus | None = None,
        driver_id: int | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> tuple[ImportRecord, ...]:
        """Retourne l'historique des telechargements, filtre.

        Args:
            file_type: Restreint a un type de telechargement.
            parsing_status: Restreint a un etat de decodage.
            driver_id: Restreint a un conducteur.
            search: Fragment recherche dans le nom de fichier ou l'empreinte.
            limit: Nombre maximal de lignes.

        Returns:
            Les lignes du journal, du plus recent au plus ancien.
        """
        with self._session() as session:
            files = ImportRepository(session).list_filtered(
                file_type=file_type,
                parsing_status=parsing_status,
                driver_id=driver_id,
                search=search,
                limit=limit,
            )
            return tuple(self._to_record(item) for item in files)

    def get_details(self, file_id: int) -> ImportRecord | None:
        """Retourne le detail d'un import, ou ``None`` s'il n'existe pas."""
        with self._session() as session:
            item = ImportRepository(session).get(file_id)
            return self._to_record(item) if item is not None else None

    # ------------------------------------------------------------------ #
    # Ecriture (phase 3)
    # ------------------------------------------------------------------ #
    def import_file(self, path: Path | str) -> ImportRecord:
        """Importe un fichier : archivage, enregistrement et decodage.

        Args:
            path: Chemin du fichier a importer.

        Returns:
            La ligne de journal creee.

        Raises:
            NotImplementedError: Fonctionnalite prevue en phase 3. Les etapes en
                lecture seule sont deja disponibles via :meth:`inspect`.
        """
        raise NotImplementedError(
            "L'import effectif (copie archivee et enregistrement en base) est prevu "
            "en phase 3. La phase 1 livre le socle : utilisez inspect() pour "
            "valider un fichier, calculer son empreinte et detecter un doublon."
        )

    @staticmethod
    def _to_record(item: TachographFile) -> ImportRecord:
        """Construit une ligne de journal pendant que la session est ouverte."""
        return ImportRecord(
            id=item.id,
            imported_at=item.imported_at,
            filename=item.filename,
            file_type=item.file_type,
            file_size=item.file_size,
            human_size=item.human_size,
            sha256=item.sha256,
            short_sha256=item.short_sha256,
            parsing_status=item.parsing_status,
            parsing_error=item.parsing_error,
            original_path=item.original_path,
            driver_display_name=item.driver.display_name if item.driver is not None else None,
            vehicle_registration=(item.vehicle.registration if item.vehicle is not None else None),
        )
