"""Utilitaires de dates et de durees.

Toutes les dates manipulees par l'application sont des ``datetime`` conscients du
fuseau (timezone-aware) exprimes en UTC. Les donnees tachygraphiques sont
enregistrees en UTC par les equipements embarques ; la conversion vers l'heure
locale est un probleme d'affichage, traite dans la couche interface uniquement.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

__all__ = [
    "utcnow",
    "ensure_utc",
    "format_duration",
    "seconds_between",
    "day_bounds",
    "week_bounds",
]


def utcnow() -> datetime:
    """Retourne l'instant courant en UTC (timezone-aware)."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Normalise un ``datetime`` en UTC.

    Un ``datetime`` naif est considere comme deja exprime en UTC : c'est la
    convention de stockage de l'application (SQLite ne conserve pas le fuseau).

    Args:
        value: Date a normaliser.

    Returns:
        Le meme instant, avec ``tzinfo`` positionne sur UTC.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def seconds_between(start: datetime, end: datetime) -> int:
    """Retourne le nombre de secondes entieres entre deux instants.

    Args:
        start: Debut de l'intervalle.
        end: Fin de l'intervalle.

    Returns:
        La duree en secondes, arrondie a l'entier inferieur.

    Raises:
        ValueError: ``end`` est anterieur a ``start``.
    """
    delta = ensure_utc(end) - ensure_utc(start)
    if delta < timedelta(0):
        raise ValueError("La fin d'un intervalle ne peut pas preceder son debut")
    return int(delta.total_seconds())


def format_duration(seconds: int) -> str:
    """Formate une duree en secondes sous la forme ``HHhMM``.

    Args:
        seconds: Duree en secondes (les valeurs negatives sont refusees).

    Returns:
        Une chaine de la forme ``"04h30"``.

    Raises:
        ValueError: ``seconds`` est negatif.
    """
    if seconds < 0:
        raise ValueError("Une duree ne peut pas etre negative")
    hours, remainder = divmod(int(seconds), 3600)
    minutes = remainder // 60
    return f"{hours:02d}h{minutes:02d}"


def day_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """Retourne les bornes [debut, fin[ du jour calendaire UTC contenant ``moment``."""
    reference = ensure_utc(moment)
    start = reference.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def week_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """Retourne les bornes [lundi 00:00, lundi suivant 00:00[ en UTC.

    La semaine debute le lundi a 00:00, conformement a la definition de la
    "semaine" du reglement (CE) no 561/2006, article 4, point i).
    """
    start_of_day, _ = day_bounds(moment)
    start = start_of_day - timedelta(days=start_of_day.weekday())
    return start, start + timedelta(days=7)
