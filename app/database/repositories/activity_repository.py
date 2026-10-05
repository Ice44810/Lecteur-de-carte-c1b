"""Depot des activites de conducteurs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.database.models import Activity, ActivityType
from app.database.repositories.base import BaseRepository

__all__ = ["ActivityRepository"]


class ActivityRepository(BaseRepository[Activity]):
    """Acces aux periodes d'activite.

    Les methodes d'agregation sont deleguees a SQL : le tableau de bord doit
    rester rapide meme avec plusieurs annees d'historique, sans charger les
    activites en memoire.
    """

    model = Activity

    def list_for_driver(
        self,
        driver_id: int,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        activity_types: tuple[ActivityType, ...] | None = None,
        vehicle_id: int | None = None,
        limit: int | None = None,
    ) -> list[Activity]:
        """Retourne les activites d'un conducteur, triees chronologiquement.

        Une activite est retenue des lors qu'elle **chevauche** la periode
        demandee : une periode de repos commencee la veille reste donc visible sur
        la journee analysee.

        Args:
            driver_id: Identifiant du conducteur.
            period_start: Debut de la periode (inclus).
            period_end: Fin de la periode (exclu).
            activity_types: Restreint a certains types d'activite.
            vehicle_id: Restreint a un vehicule.
            limit: Nombre maximal de resultats.

        Returns:
            Les activites correspondantes.
        """
        statement = select(Activity).where(Activity.driver_id == driver_id)
        if period_start is not None:
            statement = statement.where(Activity.end_datetime > period_start)
        if period_end is not None:
            statement = statement.where(Activity.start_datetime < period_end)
        if activity_types:
            statement = statement.where(Activity.activity_type.in_(activity_types))
        if vehicle_id is not None:
            statement = statement.where(Activity.vehicle_id == vehicle_id)
        statement = statement.order_by(Activity.start_datetime, Activity.id)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement).all())

    def list_for_vehicle(
        self,
        vehicle_id: int,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> list[Activity]:
        """Retourne les activites enregistrees pour un vehicule."""
        statement = select(Activity).where(Activity.vehicle_id == vehicle_id)
        if period_start is not None:
            statement = statement.where(Activity.end_datetime > period_start)
        if period_end is not None:
            statement = statement.where(Activity.start_datetime < period_end)
        return list(
            self._session.scalars(statement.order_by(Activity.start_datetime, Activity.id)).all()
        )

    def list_for_file(self, source_file_id: int) -> list[Activity]:
        """Retourne les activites extraites d'un fichier donne (tracabilite)."""
        statement = (
            select(Activity)
            .where(Activity.source_file_id == source_file_id)
            .order_by(Activity.start_datetime, Activity.id)
        )
        return list(self._session.scalars(statement).all())

    def duration_by_type(
        self,
        driver_id: int,
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[ActivityType, int]:
        """Retourne la somme des durees par type d'activite sur une periode.

        Les durees sont celles des activites **entierement contenues** dans la
        periode. Le decoupage des activites a cheval sur les bornes est realise par
        le moteur d'analyse (``app.analysis``), qui seul sait comment traiter les
        chevauchements ; un simple ``SUM`` SQL ne doit pas produire un resultat
        approximatif.

        Args:
            driver_id: Identifiant du conducteur.
            period_start: Debut de la periode (inclus).
            period_end: Fin de la periode (exclu).

        Returns:
            Un dictionnaire ``type -> secondes``, limite aux types presents.
        """
        statement = (
            select(Activity.activity_type, func.sum(Activity.duration_seconds))
            .where(
                Activity.driver_id == driver_id,
                Activity.start_datetime >= period_start,
                Activity.end_datetime <= period_end,
            )
            .group_by(Activity.activity_type)
        )
        return {
            activity_type: int(total or 0)
            for activity_type, total in self._session.execute(statement).all()
        }

    def total_duration(
        self,
        *,
        activity_type: ActivityType,
        period_start: datetime,
        period_end: datetime,
        driver_id: int | None = None,
    ) -> int:
        """Retourne la duree totale d'un type d'activite sur une periode.

        Args:
            activity_type: Type d'activite agrege.
            period_start: Debut de la periode (inclus).
            period_end: Fin de la periode (exclu).
            driver_id: Restreint a un conducteur ; sinon, tous les conducteurs.

        Returns:
            La duree en secondes.
        """
        statement = select(func.coalesce(func.sum(Activity.duration_seconds), 0)).where(
            Activity.activity_type == activity_type,
            Activity.start_datetime >= period_start,
            Activity.end_datetime <= period_end,
        )
        if driver_id is not None:
            statement = statement.where(Activity.driver_id == driver_id)
        return int(self._session.scalar(statement) or 0)

    def latest_activity_datetime(self, driver_id: int | None = None) -> datetime | None:
        """Retourne la fin de la derniere activite connue."""
        statement = select(func.max(Activity.end_datetime))
        if driver_id is not None:
            statement = statement.where(Activity.driver_id == driver_id)
        return self._session.scalar(statement)

    def count_drivers_with_activity(self, *, period_start: datetime, period_end: datetime) -> int:
        """Retourne le nombre de conducteurs ayant une activite sur la periode."""
        statement = select(func.count(func.distinct(Activity.driver_id))).where(
            Activity.end_datetime > period_start,
            Activity.start_datetime < period_end,
        )
        return int(self._session.scalar(statement) or 0)
