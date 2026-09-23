"""Modele ``Activity`` : periode d'activite continue d'un conducteur."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum as SAEnum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base
from app.database.models.enums import ActivityType
from app.database.models.types import UTCDateTime

if TYPE_CHECKING:  # pragma: no cover - imports de typage uniquement
    from app.database.models.driver import Driver
    from app.database.models.infringement import Infringement
    from app.database.models.tachograph_file import TachographFile
    from app.database.models.vehicle import Vehicle

__all__ = ["Activity"]


class Activity(Base):
    """Periode d'activite homogene (DONNEE METIER).

    Une activite est toujours rattachee au fichier dont elle a ete extraite
    (``source_file_id``) : la tracabilite entre la donnee brute et la donnee metier
    est ainsi garantie de bout en bout.

    ``duration_seconds`` est stockee de maniere redondante avec les bornes afin de
    permettre des agregations SQL rapides sur le tableau de bord ; la coherence est
    assuree par :meth:`from_bounds` et verifiee par les tests.
    """

    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint("end_datetime >= start_datetime", name="end_after_start"),
        CheckConstraint("duration_seconds >= 0", name="duration_non_negative"),
        Index("ix_activities_driver_start", "driver_id", "start_datetime"),
        Index("ix_activities_type_start", "activity_type", "start_datetime"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    driver_id: Mapped[int] = mapped_column(
        ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vehicle_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="SET NULL"), index=True
    )
    source_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("tachograph_files.id", ondelete="SET NULL"),
        index=True,
        doc="Fichier d'origine de la donnee (tracabilite).",
    )

    activity_type: Mapped[ActivityType] = mapped_column(
        SAEnum(ActivityType, native_enum=False, length=16, validate_strings=True),
        nullable=False,
        doc="Nature de l'activite.",
    )
    start_datetime: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, doc="Debut de la periode (UTC)."
    )
    end_datetime: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, doc="Fin de la periode (UTC)."
    )
    duration_seconds: Mapped[int] = mapped_column(
        nullable=False, doc="Duree de la periode en secondes."
    )

    driver: Mapped[Driver] = relationship(back_populates="activities")
    vehicle: Mapped[Vehicle | None] = relationship(back_populates="activities")
    source_file: Mapped[TachographFile | None] = relationship(back_populates="activities")
    infringements: Mapped[list[Infringement]] = relationship(back_populates="activity")

    @classmethod
    def from_bounds(
        cls,
        *,
        driver_id: int,
        activity_type: ActivityType,
        start_datetime: datetime,
        end_datetime: datetime,
        vehicle_id: int | None = None,
        source_file_id: int | None = None,
    ) -> Activity:
        """Cree une activite en calculant la duree depuis ses bornes.

        C'est la seule maniere recommandee de creer une activite : elle garantit
        que ``duration_seconds`` reste coherent avec les bornes.

        Args:
            driver_id: Identifiant du conducteur.
            activity_type: Nature de l'activite.
            start_datetime: Debut de la periode.
            end_datetime: Fin de la periode.
            vehicle_id: Identifiant du vehicule, si connu.
            source_file_id: Identifiant du fichier d'origine.

        Returns:
            Une instance non encore persistee.

        Raises:
            ValueError: ``end_datetime`` precede ``start_datetime``.
        """
        from app.core.timeutils import seconds_between

        duration = seconds_between(start_datetime, end_datetime)
        return cls(
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            source_file_id=source_file_id,
            activity_type=activity_type,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            duration_seconds=duration,
        )
