"""Mise en forme des dates pour l'affichage.

Les dates sont stockees et calculees en UTC (convention des equipements
tachygraphiques). Les horodatages administratifs, comme la date d'un import, sont
en revanche lus par l'exploitant comme une heure de sa journee : ils sont donc
convertis dans le fuseau d'affichage configure (``TACHY_TIMEZONE_DISPLAY``).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.timeutils import ensure_utc

__all__ = ["format_local_datetime"]


def format_local_datetime(
    value: datetime | None, timezone_name: str, *, pattern: str = "%d/%m/%Y %H:%M"
) -> str:
    """Formate un instant dans le fuseau d'affichage.

    Args:
        value: Instant a formater (UTC, ou naif considere comme UTC).
        timezone_name: Fuseau IANA d'affichage, par exemple ``"Europe/Paris"``.
        pattern: Format ``strftime`` a appliquer.

    Returns:
        La date formatee, ou ``"-"`` si ``value`` est absent.
    """
    if value is None:
        return "-"
    return ensure_utc(value).astimezone(ZoneInfo(timezone_name)).strftime(pattern)
