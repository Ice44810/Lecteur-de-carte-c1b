"""Tests des utilitaires de dates et de durees."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.timeutils import (
    day_bounds,
    ensure_utc,
    format_duration,
    seconds_between,
    utcnow,
    week_bounds,
)


def test_utcnow_est_conscient_du_fuseau() -> None:
    assert utcnow().tzinfo is not None


def test_ensure_utc_considere_un_datetime_naif_comme_utc() -> None:
    naive = datetime(2026, 9, 15, 8, 30)
    assert ensure_utc(naive) == datetime(2026, 9, 15, 8, 30, tzinfo=UTC)


def test_ensure_utc_convertit_un_autre_fuseau() -> None:
    paris = datetime(2026, 9, 15, 10, 0, tzinfo=timezone(timedelta(hours=2)))
    assert ensure_utc(paris) == datetime(2026, 9, 15, 8, 0, tzinfo=UTC)


def test_seconds_between_compte_les_secondes() -> None:
    start = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
    assert seconds_between(start, start + timedelta(hours=2, minutes=30)) == 9000


def test_seconds_between_refuse_un_intervalle_inverse() -> None:
    start = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="preceder"):
        seconds_between(start, start - timedelta(seconds=1))


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "00h00"), (60, "00h01"), (3600, "01h00"), (34_200, "09h30"), (86_400, "24h00")],
)
def test_format_duration(seconds: int, expected: str) -> None:
    assert format_duration(seconds) == expected


def test_format_duration_refuse_une_duree_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        format_duration(-1)


def test_day_bounds_encadre_la_journee_utc() -> None:
    start, end = day_bounds(datetime(2026, 9, 15, 23, 59, 59, tzinfo=UTC))
    assert start == datetime(2026, 9, 15, tzinfo=UTC)
    assert end == datetime(2026, 9, 16, tzinfo=UTC)


def test_week_bounds_commence_le_lundi() -> None:
    """La semaine debute le lundi (reglement (CE) no 561/2006, article 4, point i)."""
    start, end = week_bounds(datetime(2026, 9, 17, 14, 0, tzinfo=UTC))  # jeudi
    assert start == datetime(2026, 9, 14, tzinfo=UTC)  # lundi
    assert end == datetime(2026, 9, 21, tzinfo=UTC)
    assert start.weekday() == 0


def test_week_bounds_un_lundi_retourne_ce_lundi() -> None:
    start, _ = week_bounds(datetime(2026, 9, 14, 0, 0, tzinfo=UTC))
    assert start == datetime(2026, 9, 14, tzinfo=UTC)
