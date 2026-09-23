"""Modele ``TachographFile`` : trace d'un fichier importe et archive."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Enum as SAEnum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base
from app.database.models.enums import FileType, ParsingStatus
from app.database.models.types import UTCDateTime

if TYPE_CHECKING:  # pragma: no cover - imports de typage uniquement
    from app.database.models.activity import Activity
    from app.database.models.driver import Driver
    from app.database.models.infringement import Infringement
    from app.database.models.vehicle import Vehicle

__all__ = ["TachographFile"]


class TachographFile(Base):
    """Enregistrement d'un fichier tachygraphique importe.

    Cette table est le journal des telechargements (section 14 du cahier des
    charges) et la garantie de tracabilite de l'application :

    * ``sha256`` est unique : un meme contenu ne peut pas etre importe deux fois ;
    * ``original_path`` designe la copie immuable conservee dans ``originals/`` ;
    * ``parsing_status`` et ``parsing_error`` conservent le resultat du decodage,
      y compris en cas d'echec (le fichier n'est jamais supprime pour autant).
    """

    __tablename__ = "tachograph_files"
    __table_args__ = (
        CheckConstraint("file_size >= 0", name="file_size_non_negative"),
        CheckConstraint("length(sha256) = 64", name="sha256_length"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    filename: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Nom du fichier tel que fourni par l'utilisateur."
    )
    file_type: Mapped[FileType] = mapped_column(
        SAEnum(FileType, native_enum=False, length=8, validate_strings=True),
        nullable=False,
        index=True,
        doc="Type de telechargement (C1B carte conducteur, V1B vehicule).",
    )
    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        doc="Empreinte SHA-256 du contenu, en hexadecimal minuscule.",
    )
    original_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        doc="Chemin de la copie originale archivee (jamais modifiee).",
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger, nullable=False, doc="Taille du fichier en octets."
    )
    imported_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        index=True,
        doc="Date et heure de l'import (UTC).",
    )
    parsed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, doc="Date et heure de la derniere tentative de decodage (UTC)."
    )

    parsing_status: Mapped[ParsingStatus] = mapped_column(
        SAEnum(ParsingStatus, native_enum=False, length=16, validate_strings=True),
        nullable=False,
        default=ParsingStatus.PENDING,
        server_default=ParsingStatus.PENDING.value,
        index=True,
        doc="Etat du decodage du fichier.",
    )
    parsing_error: Mapped[str | None] = mapped_column(
        String(2000), doc="Message d'erreur de decodage, conserve pour diagnostic."
    )

    driver_id: Mapped[int | None] = mapped_column(
        ForeignKey("drivers.id", ondelete="SET NULL"), index=True
    )
    vehicle_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="SET NULL"), index=True
    )

    driver: Mapped[Driver | None] = relationship(back_populates="files")
    vehicle: Mapped[Vehicle | None] = relationship(back_populates="files")
    activities: Mapped[list[Activity]] = relationship(back_populates="source_file")
    infringements: Mapped[list[Infringement]] = relationship(back_populates="source_file")

    @property
    def short_sha256(self) -> str:
        """Debut de l'empreinte, pour affichage compact dans les tableaux."""
        return f"{self.sha256[:12]}..."

    @property
    def human_size(self) -> str:
        """Taille lisible (Ko / Mo), arrondie."""
        size = float(self.file_size)
        for unit in ("o", "Ko", "Mo", "Go"):
            if size < 1024 or unit == "Go":
                return f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} Go"  # pragma: no cover - inatteignable
