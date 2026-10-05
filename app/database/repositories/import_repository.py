"""Depot du journal des imports (fichiers tachygraphiques archives)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.database.models import FileType, ParsingStatus, TachographFile
from app.database.repositories.base import BaseRepository

__all__ = ["ImportRepository"]


class ImportRepository(BaseRepository[TachographFile]):
    """Acces aux fichiers importes.

    L'empreinte SHA-256 est la cle de deduplication : :meth:`get_by_sha256` est
    appelee avant tout nouvel import (section 22 du cahier des charges).
    """

    model = TachographFile

    def get_by_sha256(self, sha256: str) -> TachographFile | None:
        """Retourne le fichier portant cette empreinte, ou ``None``."""
        statement = select(TachographFile).where(TachographFile.sha256 == sha256.lower())
        return self._session.scalars(statement).first()

    def exists_sha256(self, sha256: str) -> bool:
        """Indique si un fichier de meme contenu a deja ete importe."""
        return self.get_by_sha256(sha256) is not None

    def list_recent(self, *, limit: int = 20) -> list[TachographFile]:
        """Retourne les derniers fichiers importes, du plus recent au plus ancien."""
        statement = (
            select(TachographFile)
            .order_by(TachographFile.imported_at.desc(), TachographFile.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(statement).all())

    def list_filtered(
        self,
        *,
        file_type: FileType | None = None,
        parsing_status: ParsingStatus | None = None,
        driver_id: int | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> list[TachographFile]:
        """Retourne les fichiers correspondant aux filtres de l'historique.

        Args:
            file_type: Restreint a un type de telechargement.
            parsing_status: Restreint a un etat de decodage.
            driver_id: Restreint a un conducteur.
            search: Fragment recherche dans le nom de fichier ou l'empreinte.
            limit: Nombre maximal de resultats.

        Returns:
            Les fichiers correspondants, du plus recent au plus ancien.
        """
        statement = select(TachographFile)
        if file_type is not None:
            statement = statement.where(TachographFile.file_type == file_type)
        if parsing_status is not None:
            statement = statement.where(TachographFile.parsing_status == parsing_status)
        if driver_id is not None:
            statement = statement.where(TachographFile.driver_id == driver_id)
        if search:
            pattern = f"%{search.strip()}%"
            statement = statement.where(
                TachographFile.filename.ilike(pattern) | TachographFile.sha256.ilike(pattern)
            )
        statement = statement.order_by(TachographFile.imported_at.desc(), TachographFile.id.desc())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement).all())

    def count_by_type(self, file_type: FileType) -> int:
        """Retourne le nombre de fichiers importes pour un type donne."""
        statement = (
            select(func.count())
            .select_from(TachographFile)
            .where(TachographFile.file_type == file_type)
        )
        return int(self._session.scalar(statement) or 0)

    def count_by_status(self, parsing_status: ParsingStatus) -> int:
        """Retourne le nombre de fichiers dans un etat de decodage donne."""
        statement = (
            select(func.count())
            .select_from(TachographFile)
            .where(TachographFile.parsing_status == parsing_status)
        )
        return int(self._session.scalar(statement) or 0)

    def last_import_datetime(self) -> datetime | None:
        """Retourne la date du dernier import, ou ``None`` si aucun import."""
        statement = select(func.max(TachographFile.imported_at))
        return self._session.scalar(statement)

    def list_pending_parsing(self, *, limit: int | None = None) -> list[TachographFile]:
        """Retourne les fichiers archives dont le decodage reste a faire."""
        statement = (
            select(TachographFile)
            .where(
                TachographFile.parsing_status.in_(
                    (ParsingStatus.PENDING, ParsingStatus.UNSUPPORTED)
                )
            )
            .order_by(TachographFile.imported_at)
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement).all())
