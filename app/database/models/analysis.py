"""Modele ``Analysis`` : resultat agrege d'une analyse sur une periode."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base
from app.database.models.types import UTCDateTime

if TYPE_CHECKING:  # pragma: no cover - imports de typage uniquement
    from app.database.models.driver import Driver
    from app.database.models.infringement import Infringement

__all__ = ["Analysis"]


class Analysis(Base):
    """Synthese calculee pour un conducteur sur une periode donnee (ANALYSE).

    Une analyse est un cliche : elle enregistre le resultat d'un calcul a un
    instant donne, avec la version du jeu de regles utilise. Relancer une analyse
    cree un nouvel enregistrement plutot que d'ecraser le precedent, afin de
    conserver la tracabilite des controles effectues.
    """

    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="period_end_after_start"),
        CheckConstraint("driving_seconds >= 0", name="driving_non_negative"),
        CheckConstraint("work_seconds >= 0", name="work_non_negative"),
        CheckConstraint("availability_seconds >= 0", name="availability_non_negative"),
        CheckConstraint("rest_seconds >= 0", name="rest_non_negative"),
        CheckConstraint("warnings_count >= 0", name="warnings_non_negative"),
        CheckConstraint("infringements_count >= 0", name="infringements_non_negative"),
        Index("ix_analyses_driver_period", "driver_id", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    driver_id: Mapped[int] = mapped_column(
        ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    period_start: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, doc="Debut de la periode analysee (UTC, inclus)."
    )
    period_end: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, doc="Fin de la periode analysee (UTC, exclu)."
    )

    driving_seconds: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    work_seconds: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    availability_seconds: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    rest_seconds: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    unknown_seconds: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")

    warnings_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
        doc="Nombre de situations a verifier detectees sur la periode.",
    )
    infringements_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
        doc="Nombre de depassements apparents detectes sur la periode.",
    )

    ruleset_version: Mapped[str | None] = mapped_column(
        String(32), doc="Version du jeu de regles utilise pour ce calcul (tracabilite)."
    )

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.current_timestamp()
    )

    driver: Mapped[Driver] = relationship(back_populates="analyses")
    infringements: Mapped[list[Infringement]] = relationship(back_populates="analysis")

    @property
    def total_recorded_seconds(self) -> int:
        """Somme des durees enregistrees, tous types d'activite confondus."""
        return (
            self.driving_seconds
            + self.work_seconds
            + self.availability_seconds
            + self.rest_seconds
            + self.unknown_seconds
        )
