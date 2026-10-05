"""Depot des anomalies et depassements apparents."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.database.models import Infringement, RuleStatus, Severity
from app.database.repositories.base import BaseRepository

__all__ = ["InfringementRepository"]


class InfringementRepository(BaseRepository[Infringement]):
    """Acces aux alertes produites par le moteur de regles."""

    model = Infringement

    def list_recent(self, *, limit: int = 20) -> list[Infringement]:
        """Retourne les alertes les plus recentes."""
        statement = (
            select(Infringement)
            .order_by(Infringement.detected_at.desc(), Infringement.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(statement).all())

    def list_for_driver(
        self,
        driver_id: int,
        *,
        period_start: date | None = None,
        period_end: date | None = None,
        statuses: tuple[RuleStatus, ...] | None = None,
    ) -> list[Infringement]:
        """Retourne les alertes d'un conducteur, du jour le plus recent au plus ancien."""
        statement = select(Infringement).where(Infringement.driver_id == driver_id)
        if period_start is not None:
            statement = statement.where(Infringement.occurred_on >= period_start)
        if period_end is not None:
            statement = statement.where(Infringement.occurred_on <= period_end)
        if statuses:
            statement = statement.where(Infringement.status.in_(statuses))
        statement = statement.order_by(Infringement.occurred_on.desc(), Infringement.id.desc())
        return list(self._session.scalars(statement).all())

    def count_open(self) -> int:
        """Retourne le nombre d'alertes non encore verifiees par l'exploitant."""
        statement = (
            select(func.count())
            .select_from(Infringement)
            .where(
                Infringement.acknowledged_at.is_(None),
                Infringement.status.in_((RuleStatus.WARNING, RuleStatus.VIOLATION)),
            )
        )
        return int(self._session.scalar(statement) or 0)

    def count_by_status(self, status: RuleStatus) -> int:
        """Retourne le nombre d'alertes dans un etat donne."""
        statement = (
            select(func.count()).select_from(Infringement).where(Infringement.status == status)
        )
        return int(self._session.scalar(statement) or 0)

    def count_by_severity(self) -> dict[Severity, int]:
        """Retourne la repartition des alertes par criticite."""
        statement = (
            select(Infringement.severity, func.count())
            .group_by(Infringement.severity)
            .order_by(Infringement.severity)
        )
        return {severity: int(total) for severity, total in self._session.execute(statement).all()}

    def list_for_analysis(self, analysis_id: int) -> list[Infringement]:
        """Retourne les alertes produites par une analyse donnee."""
        statement = (
            select(Infringement)
            .where(Infringement.analysis_id == analysis_id)
            .order_by(Infringement.occurred_on, Infringement.id)
        )
        return list(self._session.scalars(statement).all())
