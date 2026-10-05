"""Fixtures propres aux tests du moteur d'analyse."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from app.analysis.models import ActivityInterval
from app.core.enums import ActivityType

JOUR = datetime(2026, 9, 15, tzinfo=UTC)  # mardi


@pytest.fixture
def jour() -> datetime:
    """Minuit UTC du mardi 15 septembre 2026."""
    return JOUR


@pytest.fixture
def interval_factory() -> Callable[..., ActivityInterval]:
    """Retourne une fabrique d'intervalles exprimes en heures depuis minuit."""

    def _make(
        activity_type: ActivityType,
        start_hour: float,
        end_hour: float,
        *,
        day: datetime = JOUR,
        activity_id: int | None = None,
        vehicle_id: int | None = None,
    ) -> ActivityInterval:
        return ActivityInterval(
            activity_type=activity_type,
            start=day + timedelta(hours=start_hour),
            end=day + timedelta(hours=end_hour),
            activity_id=activity_id,
            vehicle_id=vehicle_id,
        )

    return _make


@pytest.fixture
def journee_type(interval_factory: Callable[..., ActivityInterval]) -> tuple[ActivityInterval, ...]:
    """Journee de service complete et coherente.

    Composition : 06h00-07h00 travail, 07h00-10h45 conduite, 10h45-11h30 repos,
    11h30-15h30 conduite, 15h30-16h00 disponibilite, 16h00-17h00 travail.

    Conduite totale : 7h45. Blocs de conduite separes par la coupure de 45 minutes :
    3h45 puis 4h00.
    """
    return (
        interval_factory(ActivityType.WORK, 6, 7),
        interval_factory(ActivityType.DRIVING, 7, 10.75),
        interval_factory(ActivityType.REST, 10.75, 11.5),
        interval_factory(ActivityType.DRIVING, 11.5, 15.5),
        interval_factory(ActivityType.AVAILABILITY, 15.5, 16),
        interval_factory(ActivityType.WORK, 16, 17),
    )
