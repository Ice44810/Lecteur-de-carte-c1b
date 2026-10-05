"""Service de telechargement d'une carte conducteur.

Enchaine, sans intervention de l'utilisateur, les etapes qui suivent l'insertion
d'une carte :

.. code-block:: text

    lecture de la carte -> fichier .C1B dans imports/ -> import (archivage immuable,
    journal des telechargements)

Le service ne connait pas Qt : la detection de l'insertion et l'execution en tache de
fond relevent de l'interface (:mod:`app.ui.cards.card_watcher`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.card_reader.interface import CardReaderInterface
from app.card_reader.tachograph_card import CardDownload, TachographCard
from app.config.logging_config import get_logger
from app.config.settings import Settings, get_settings
from app.core.exceptions import DuplicateFileError, StorageError
from app.core.timeutils import utcnow
from app.database.database import Database
from app.services.base import BaseService
from app.services.import_service import ImportRecord, ImportService

__all__ = ["CardImportResult", "CardDownloadService"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CardImportResult:
    """Resultat d'un telechargement de carte suivi de son import.

    Attributes:
        download: Donnees lues sur la carte.
        path: Fichier ``.C1B`` ecrit dans le repertoire des imports.
        record: Ligne du journal creee, ou ``None`` si le contenu etait deja importe.
        existing_file_id: Import existant de meme contenu, en cas de doublon.
    """

    download: CardDownload
    path: Path
    record: ImportRecord | None = None
    existing_file_id: int | None = None

    @property
    def is_duplicate(self) -> bool:
        """Indique que ce contenu avait deja ete importe."""
        return self.record is None

    def summary(self) -> str:
        """Message de synthese destine a l'utilisateur."""
        generation = "1re et 2e generation" if self.download.has_generation_2 else "1re generation"
        if self.record is None:
            return (
                f"Carte telechargee ({self.download.size} octets, {generation}) : "
                "ces donnees avaient deja ete importees, aucun nouvel import."
            )
        return (
            f"Carte telechargee et archivee ({self.download.size} octets, {generation}) - "
            f"import #{self.record.id}, etat : {self.record.parsing_status.label}."
        )


class CardDownloadService(BaseService):
    """Telecharge une carte conducteur et importe le fichier obtenu.

    Args:
        database: Base a utiliser.
        settings: Configuration, pour situer les repertoires d'import et d'archivage.
    """

    def __init__(
        self, database: Database | None = None, *, settings: Settings | None = None
    ) -> None:
        super().__init__(database)
        self._settings = settings or get_settings()
        self._imports = ImportService(self.database, settings=self._settings)

    def download_and_import(self, reader: CardReaderInterface) -> CardImportResult:
        """Lit la carte inseree, enregistre le fichier ``.C1B`` puis l'importe.

        La connexion a la carte est toujours fermee a la fin, y compris en cas
        d'erreur, afin que le lecteur reste disponible.

        Args:
            reader: Lecteur contenant la carte.

        Returns:
            Le resultat du telechargement et de l'import.

        Raises:
            UnconfirmedStructureError: La sequence de lecture n'est pas referencee.
            NoCardPresentError: Aucune carte n'est inseree.
            CardCommunicationError: La lecture a echoue ou la carte n'est pas une
                carte conducteur.
            StorageError: Le fichier n'a pas pu etre ecrit ou archive.
        """
        try:
            download = TachographCard(reader).download()
        finally:
            reader.disconnect()

        path = self._write(download)
        try:
            record = self._imports.import_file(path)
        except DuplicateFileError as exc:
            logger.info("Telechargement de carte deja importe (import #%s)", exc.existing_file_id)
            return CardImportResult(
                download=download, path=path, existing_file_id=exc.existing_file_id
            )
        return CardImportResult(download=download, path=path, record=record)

    def _write(self, download: CardDownload) -> Path:
        """Ecrit le telechargement dans le repertoire des imports, sans jamais ecraser.

        Raises:
            StorageError: Le fichier n'a pas pu etre ecrit.
        """
        directory = self._settings.imports_dir
        stamp = utcnow().strftime("%Y%m%d_%H%M%S")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            for index in range(100):
                suffix = f"_{index}" if index else ""
                path = directory / f"carte_{stamp}{suffix}.C1B"
                try:
                    with path.open("xb") as handle:
                        handle.write(download.payload)
                        handle.flush()
                        os.fsync(handle.fileno())
                except FileExistsError:
                    continue
                logger.info("Telechargement de carte enregistre : %s", path.name)
                return path
        except OSError as exc:
            raise StorageError(
                "Le fichier telecharge depuis la carte n'a pas pu etre enregistre.",
                cause="Le repertoire des imports est inaccessible ou le disque est plein.",
                action=f"Verifiez l'espace disque et les droits sur {directory}.",
                technical_detail=str(exc),
            ) from exc
        raise StorageError(
            "Le fichier telecharge depuis la carte n'a pas pu etre enregistre.",
            cause="Trop de telechargements portent deja le meme horodatage.",
            action="Patientez quelques secondes puis recommencez.",
        )
