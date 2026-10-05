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
* **Implemente** : :meth:`ImportService.import_file`, qui archive une copie immuable
  du fichier, verifie son empreinte, controle sa taille et l'enregistre dans le
  journal des telechargements avec son etat de decodage.
* **Non implemente (phase 4)** : l'extraction du contenu binaire et l'enregistrement
  des conducteurs et activites decodes. Tant que les structures ne sont pas
  confirmees, un fichier archive porte l'etat « Non pris en charge » et la raison
  precise ; le decodage pourra etre rejoue sur l'archive sans nouvel import.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config.logging_config import get_logger
from app.config.settings import Settings, get_settings
from app.core.enums import FileType, ParsingStatus
from app.core.exceptions import DuplicateFileError, ImportError_, ParsingError, StorageError
from app.core.hashing import sha256_file
from app.core.timeutils import utcnow
from app.database.database import Database
from app.database.models import TachographFile
from app.database.repositories import ImportRepository
from app.parser import detect_file_type, get_parser_for
from app.parser.c1b_parser import content_digest
from app.parser.models import DiagnosticLevel, ParseResult
from app.services.base import BaseService
from app.services.decoded_data import store_decoded_data

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
        content_sha256: Empreinte du contenu hors signatures (fichiers de carte).
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
    content_sha256: str | None = None

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


ARCHIVE_FILE_MODE = 0o444
"""Droits de la copie archivee : lecture seule pour tous."""


@dataclass(frozen=True, slots=True)
class _DecodeOutcome:
    """Resultat interne du decodage d'un fichier archive."""

    status: ParsingStatus
    message: str | None = None
    result: ParseResult | None = None


class ImportService(BaseService):
    """Import et consultation des fichiers tachygraphiques.

    Args:
        database: Base a utiliser.
        settings: Configuration, pour situer le repertoire d'archivage.
    """

    def __init__(
        self, database: Database | None = None, *, settings: Settings | None = None
    ) -> None:
        super().__init__(database)
        self._settings = settings or get_settings()

    @property
    def originals_directory(self) -> Path:
        """Repertoire d'archivage immuable des fichiers originaux."""
        return self._settings.originals_dir

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

        content = self._content_digest(file_type, file_path)
        with self._session() as session:
            repository = ImportRepository(session)
            existing = repository.get_by_sha256(digest)
            if existing is None and content is not None:
                existing = repository.get_by_content_sha256(content)
            existing_id = existing.id if existing is not None else None
            existing_date = existing.imported_at if existing is not None else None

        if existing_id is not None:
            logger.info("Fichier %s deja importe (import #%s)", file_path.name, existing_id)

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
            content_sha256=content,
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
    # Ecriture
    # ------------------------------------------------------------------ #
    def import_file(self, path: Path | str) -> ImportRecord:
        """Importe un fichier : archivage immuable puis enregistrement au journal.

        Etapes, dans l'ordre : examen (extension, empreinte, doublon), copie du
        fichier dans ``originals/`` avec verification de l'empreinte de la copie,
        passage de la copie en lecture seule, controle de la taille, puis
        enregistrement dans le journal des telechargements.

        Le fichier source n'est jamais modifie ni deplace. Un fichier vide ou tronque
        est archive malgre tout, avec l'etat « Echec » et la raison : l'original reste
        ainsi disponible pour un nouvel examen.

        Args:
            path: Chemin du fichier a importer.

        Returns:
            La ligne de journal creee.

        Raises:
            UnsupportedFileTypeError: L'extension n'est ni ``.C1B`` ni ``.V1B``.
            DuplicateFileError: Un fichier de meme contenu est deja importe.
            StorageError: Le fichier n'a pas pu etre lu ou archive.
        """
        inspection = self.inspect(path)
        if inspection.is_duplicate:
            raise DuplicateFileError(
                inspection.duplicate_message,
                existing_file_id=inspection.existing_file_id,
                sha256=inspection.sha256,
            )

        archived = self._archive(inspection)
        outcome = self._decode(inspection.file_type, archived, filename=inspection.filename)

        with self._session() as session:
            repository = ImportRepository(session)
            existing = repository.get_by_sha256(inspection.sha256)
            if existing is not None:
                # Import concurrent du meme contenu entre l'examen et l'ecriture.
                raise DuplicateFileError(existing_file_id=existing.id, sha256=inspection.sha256)
            record = TachographFile(
                filename=inspection.filename[:255],
                file_type=inspection.file_type,
                sha256=inspection.sha256,
                content_sha256=inspection.content_sha256,
                original_path=str(archived),
                file_size=inspection.file_size,
                parsing_status=outcome.status,
                parsing_error=outcome.message,
                parsed_at=utcnow(),
            )
            repository.add(record)
            repository.flush()
            self._store(session, record, outcome)
            repository.flush()
            session.refresh(record)
            result = self._to_record(record)
        status = outcome.status

        logger.info(
            "Fichier %s importe (import #%s, etat %s)",
            inspection.filename,
            result.id,
            status.value,
        )
        return result

    def _archive(self, inspection: FileInspection) -> Path:
        """Copie le fichier dans le repertoire d'archivage, en lecture seule.

        La copie est nommee d'apres son empreinte : deux contenus differents ne
        peuvent pas s'ecraser, et une copie laissee par un import interrompu est
        reutilisee apres verification plutot que dupliquee.

        Returns:
            Le chemin de la copie archivee.

        Raises:
            StorageError: La copie a echoue, ou son empreinte differe de celle du
                fichier examine (fichier modifie pendant l'import).
        """
        digest = inspection.sha256
        directory = self.originals_directory / digest[:2]
        target = directory / f"{digest}{inspection.file_type.extension}"

        if target.exists():
            if sha256_file(target) == digest:
                logger.info("Copie archivee deja presente, reutilisee : %s", target.name)
                return target
            raise StorageError(
                "Une copie archivee est incoherente.",
                cause=(
                    f"Le fichier {target} existe mais son contenu ne correspond pas a son "
                    "empreinte."
                ),
                action=(
                    "Ne supprimez rien. Signalez l'anomalie : l'archive doit etre verifiee "
                    "avant tout nouvel import de ce fichier."
                ),
                technical_detail=f"empreinte attendue {digest}",
            )

        temporary = directory / f".{digest}.partial"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # La copie est forcee sur disque depuis le descripteur d'ecriture : Windows
            # refuse fsync sur un fichier ouvert en lecture seule.
            with inspection.path.open("rb") as source, temporary.open("wb") as copy:
                shutil.copyfileobj(source, copy)
                copy.flush()
                os.fsync(copy.fileno())
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise StorageError(
                f"Le fichier {inspection.filename} n'a pas pu etre archive.",
                cause="Le repertoire d'archivage est inaccessible ou le disque est plein.",
                action=f"Verifiez l'espace disque et les droits sur {self.originals_directory}.",
                technical_detail=str(exc),
            ) from exc

        if sha256_file(temporary) != digest:
            temporary.unlink(missing_ok=True)
            raise StorageError(
                f"Le fichier {inspection.filename} a change pendant l'import.",
                cause="Son contenu ne correspond plus a l'empreinte calculee lors de l'examen.",
                action="Attendez la fin de la copie ou du telechargement, puis reessayez.",
            )

        try:
            os.chmod(temporary, ARCHIVE_FILE_MODE)
            os.replace(temporary, target)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise StorageError(
                f"Le fichier {inspection.filename} n'a pas pu etre archive.",
                cause="La copie n'a pas pu etre finalisee dans le repertoire d'archivage.",
                action=f"Verifiez les droits sur {self.originals_directory}.",
                technical_detail=str(exc),
            ) from exc
        logger.info("Fichier %s archive sous %s", inspection.filename, target.name)
        return target

    # ------------------------------------------------------------------ #
    # Decodage
    # ------------------------------------------------------------------ #
    def redecode(self, file_id: int) -> ImportRecord:
        """Decode a nouveau un fichier archive et enregistre ses donnees.

        Sert aux fichiers archives avant que leur format ne soit decodable : le
        decodage est rejoue sur la copie archivee, sans nouvel import. Les activites
        deja connues ne sont pas dupliquees.

        Args:
            file_id: Identifiant de l'import.

        Returns:
            La ligne de journal mise a jour.

        Raises:
            ImportError_: L'import n'existe pas.
            StorageError: La copie archivee est illisible.
        """
        with self._session() as session:
            record = ImportRepository(session).get(file_id)
            if record is None:
                raise ImportError_(
                    "Cet import n'existe pas.",
                    cause="Il a peut-etre ete supprime depuis l'ouverture de l'historique.",
                    action="Actualisez l'historique des telechargements.",
                    technical_detail=f"file_id={file_id}",
                )
            archived = Path(record.original_path)
            outcome = self._decode(record.file_type, archived, filename=record.filename)
            if record.content_sha256 is None and record.file_type is FileType.C1B:
                record.content_sha256 = self._content_digest(record.file_type, archived)
            record.parsing_status = outcome.status
            record.parsing_error = outcome.message
            record.parsed_at = utcnow()
            self._store(session, record, outcome)
            session.flush()
            result = self._to_record(record)
        logger.info("Import #%s decode a nouveau : etat %s", file_id, outcome.status.value)
        return result

    def redecode_pending(self) -> tuple[ImportRecord, ...]:
        """Decode a nouveau les fichiers archives en attente de decodage.

        Returns:
            Les lignes de journal mises a jour.
        """
        with self._session() as session:
            identifiers = [item.id for item in ImportRepository(session).list_pending_parsing()]
        return tuple(self.redecode(identifier) for identifier in identifiers)

    @staticmethod
    def _content_digest(file_type: FileType, path: Path) -> str | None:
        """Empreinte du contenu hors signatures, pour un fichier de carte."""
        if file_type is not FileType.C1B:
            return None
        try:
            payload = path.read_bytes()
        except OSError:
            return None
        return content_digest(payload)

    @staticmethod
    def _decode(file_type: FileType, archived: Path, *, filename: str) -> _DecodeOutcome:
        """Decode un fichier archive.

        Returns:
            L'etat de decodage, la raison a conserver et le resultat eventuel.

        Raises:
            StorageError: La copie archivee est illisible.
        """
        try:
            payload = archived.read_bytes()
        except OSError as exc:
            raise StorageError(
                f"La copie archivee de {filename} n'a pas pu etre relue.",
                cause="Le repertoire d'archivage est inaccessible ou le fichier a disparu.",
                action=f"Verifiez les droits sur {archived.parent}.",
                technical_detail=str(exc),
            ) from exc
        # Le nom d'origine est conserve dans les messages : c'est celui que
        # l'utilisateur connait, et non le nom technique de l'archive.
        parser = get_parser_for(file_type)(payload, filename=filename)
        try:
            parser.validate()
        except ParsingError as exc:
            return _DecodeOutcome(ParsingStatus.FAILED, f"{exc.message} {exc.cause}")
        if not parser.decoding_available:
            codes = ", ".join(question.code for question in parser.blocking_questions)
            return _DecodeOutcome(
                ParsingStatus.UNSUPPORTED,
                "Fichier archive sans decodage : les structures binaires de ce format "
                "doivent d'abord etre confirmees avec la specification officielle"
                + (f" ({codes})." if codes else "."),
            )
        try:
            result = parser.parse()
        except ParsingError as exc:
            return _DecodeOutcome(ParsingStatus.FAILED, f"{exc.message} {exc.cause}")
        problems = [
            item.message
            for item in result.diagnostics
            if item.level in (DiagnosticLevel.WARNING, DiagnosticLevel.ERROR)
        ]
        if result.driver is None:
            return _DecodeOutcome(
                ParsingStatus.FAILED,
                "Le conducteur n'a pas pu etre identifie. " + " ".join(problems),
                result,
            )
        status = ParsingStatus.SUCCESS if not problems else ParsingStatus.PARTIAL
        return _DecodeOutcome(status, " ".join(problems) or None, result)

    @staticmethod
    def _store(session: Session, record: TachographFile, outcome: _DecodeOutcome) -> None:
        """Enregistre les donnees decodees, et en resume le bilan dans le journal."""
        if outcome.result is None or outcome.status is ParsingStatus.FAILED:
            return
        stored = store_decoded_data(session, record, outcome.result)
        summary = f"{outcome.result.summary()} - {stored.summary()}."
        record.parsing_error = (
            f"{summary} {record.parsing_error}" if record.parsing_error else summary
        )[:2000]

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
