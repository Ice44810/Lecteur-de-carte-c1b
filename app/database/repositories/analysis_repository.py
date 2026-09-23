"""Depot des analyses enregistrees."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.database.models import Analysis
from app.database.repositories.base import BaseRepository

__all__ = ["AnalysisRepository"]


class AnalysisRepository(BaseRepository[Analysis]):
    """Acces aux cliches d'analyse.

    Les analyses ne sont jamais ecrasees : relancer un calcul ajoute une ligne, ce
    qui permet de retracer les controles effectues.
    """

    model = Analysis

    def latest_for_driver(self, driver_id: int) -> Analysis | None:
        """Retourne l'analyse la plus recente d'un conducteur."""
        statement = (
            select(Analysis)
            .where(Analysis.driver_id == driver_id)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .limit(1)
        )
        return self._session.scalars(statement).first()

    def list_for_driver(
        self,
        driver_id: int,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Analysis]:
        """Retourne les analyses d'un conducteur, de la plus recente a la plus ancienne."""
        statement = select(Analysis).where(Analysis.driver_id == driver_id)
        if period_start is not None:
            statement = statement.where(Analysis.period_end > period_start)
        if period_end is not None:
            statement = statement.where(Analysis.period_start < period_end)
        statement = statement.order_by(Analysis.period_start.desc(), Analysis.id.desc())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement).all())

    def list_recent(self, *, limit: int = 20) -> list[Analysis]:
        """Retourne les dernieres analyses calculees, tous conducteurs confondus."""
        statement = (
            select(Analysis)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(statement).all())
