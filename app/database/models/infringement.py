"""Modele ``Infringement`` : anomalie ou depassement apparent detecte (ALERTE)."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum as SAEnum, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base
from app.database.models.enums import RuleStatus, Severity
from app.database.models.types import UTCDateTime

if TYPE_CHECKING:  # pragma: no cover - imports de typage uniquement
    from app.database.models.activity import Activity
    from app.database.models.analysis import Analysis
    from app.database.models.driver import Driver
    from app.database.models.tachograph_file import TachographFile

__all__ = ["Infringement"]


class Infringement(Base):
    """Ecart detecte entre une mesure et un seuil configure.

    Malgre son nom (conserve pour rester aligne avec le vocabulaire du domaine),
    cette table n'enregistre pas des infractions juridiquement etablies mais des
    **anomalies et depassements apparents** : seule une autorite de controle peut
    qualifier une infraction. L'interface et les rapports doivent donc employer les
    libelles de :class:`~app.database.models.enums.RuleStatus`.

    Les champs ``measured_value`` / ``allowed_value`` / ``unit`` rendent chaque
    alerte verifiable : l'utilisateur voit la valeur mesuree, le seuil applique, et
    ``rule_code`` permet de retrouver la regle et sa source reglementaire.
    """

    __tablename__ = "infringements"
    __table_args__ = (
        Index("ix_infringements_driver_date", "driver_id", "occurred_on"),
        Index("ix_infringements_rule", "rule_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    driver_id: Mapped[int] = mapped_column(
        ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"),
        index=True,
        doc="Activite concernee, lorsque l'ecart est rattachable a une periode precise.",
    )
    analysis_id: Mapped[int | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"),
        index=True,
        doc="Analyse ayant produit cette alerte.",
    )
    source_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("tachograph_files.id", ondelete="SET NULL"),
        index=True,
        doc="Fichier a l'origine des donnees analysees.",
    )

    occurred_on: Mapped[date] = mapped_column(
        Date, nullable=False, doc="Jour concerne par l'ecart (date de service)."
    )
    period_start: Mapped[datetime | None] = mapped_column(
        UTCDateTime, doc="Debut de la periode evaluee, si pertinent (UTC)."
    )
    period_end: Mapped[datetime | None] = mapped_column(
        UTCDateTime, doc="Fin de la periode evaluee, si pertinent (UTC)."
    )

    rule_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Code stable de la regle evaluee, par exemple DAILY_DRIVING_MAX.",
    )
    status: Mapped[RuleStatus] = mapped_column(
        SAEnum(RuleStatus, native_enum=False, length=16, validate_strings=True),
        nullable=False,
        default=RuleStatus.WARNING,
        server_default=RuleStatus.WARNING.value,
        index=True,
        doc="Resultat de la regle (WARNING : a verifier, VIOLATION : depassement apparent).",
    )
    severity: Mapped[Severity] = mapped_column(
        SAEnum(Severity, native_enum=False, length=16, validate_strings=True),
        nullable=False,
        default=Severity.MEDIUM,
        server_default=Severity.MEDIUM.value,
        index=True,
        doc="Criticite interne, utilisee pour le tri (non juridique).",
    )

    description: Mapped[str] = mapped_column(
        String(500), nullable=False, doc="Description lisible de l'ecart constate."
    )
    measured_value: Mapped[float | None] = mapped_column(Float, doc="Valeur mesuree.")
    allowed_value: Mapped[float | None] = mapped_column(Float, doc="Seuil configure applique.")
    unit: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="seconds",
        server_default="seconds",
        doc="Unite des valeurs mesuree et autorisee.",
    )

    regulation_reference: Mapped[str | None] = mapped_column(
        String(255),
        doc="Source reglementaire de la regle appliquee (obligatoire pour toute regle active).",
    )

    detected_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        doc="Date et heure de detection (UTC).",
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, doc="Date a laquelle l'exploitant a marque l'alerte comme verifiee."
    )

    driver: Mapped[Driver] = relationship(back_populates="infringements")
    activity: Mapped[Activity | None] = relationship(back_populates="infringements")
    analysis: Mapped[Analysis | None] = relationship(back_populates="infringements")
    source_file: Mapped[TachographFile | None] = relationship(back_populates="infringements")

    @property
    def is_acknowledged(self) -> bool:
        """Indique si l'alerte a deja ete verifiee par l'exploitant."""
        return self.acknowledged_at is not None
