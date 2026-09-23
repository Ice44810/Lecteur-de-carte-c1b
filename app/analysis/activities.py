"""Normalisation des suites d'activites.

Toutes les fonctions de calcul de temps partent du principe que la suite
d'intervalles qu'elles recoivent est **normalisee** : triee, sans chevauchement et
sans intervalle de duree nulle. C'est le role de ce module.

Regle de prudence : aucun trou dans les donnees n'est comble automatiquement. Une
periode sans enregistrement reste une periode sans enregistrement, signalee par
:func:`find_gaps`. Deduire un mode d'activite absent serait inventer une donnee.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta

from app.analysis.models import ActivityInterval, DaySummary, PeriodTotals
from app.core.enums import ActivityType
from app.core.exceptions import AnalysisError
from app.core.timeutils import day_bounds, ensure_utc

__all__ = [
    "to_intervals",
    "normalize_intervals",
    "merge_adjacent",
    "clip_to_period",
    "find_gaps",
    "find_overlaps",
    "split_by_day",
    "summarize_days",
]


def to_intervals(activities: Iterable[object]) -> tuple[ActivityInterval, ...]:
    """Convertit des activites ORM en intervalles d'analyse.

    Cette fonction est le seul point de contact entre la couche de persistance et
    le moteur d'analyse. Elle accepte tout objet exposant les attributs
    ``activity_type``, ``start_datetime`` et ``end_datetime``.

    Args:
        activities: Activites a convertir.

    Returns:
        Les intervalles correspondants, dans l'ordre fourni.

    Raises:
        AnalysisError: Un objet ne presente pas les attributs attendus.
    """
    intervals: list[ActivityInterval] = []
    for activity in activities:
        try:
            intervals.append(
                ActivityInterval(
                    activity_type=activity.activity_type,  # type: ignore[attr-defined]
                    start=activity.start_datetime,  # type: ignore[attr-defined]
                    end=activity.end_datetime,  # type: ignore[attr-defined]
                    activity_id=getattr(activity, "id", None),
                    vehicle_id=getattr(activity, "vehicle_id", None),
                    source_file_id=getattr(activity, "source_file_id", None),
                )
            )
        except AttributeError as exc:
            raise AnalysisError(
                "Une activite n'a pas pu etre analysee.",
                cause="Un enregistrement d'activite est incomplet.",
                action="Relancez l'import du fichier concerne.",
                technical_detail=str(exc),
            ) from exc
    return tuple(intervals)


def find_overlaps(
    intervals: Sequence[ActivityInterval],
) -> tuple[tuple[ActivityInterval, ActivityInterval], ...]:
    """Detecte les chevauchements dans une suite d'intervalles.

    Un chevauchement traduit une incoherence des donnees sources (par exemple deux
    fichiers couvrant la meme periode). Il est signale, jamais corrige en silence.

    Args:
        intervals: Intervalles a examiner (l'ordre n'importe pas).

    Returns:
        Les couples d'intervalles qui se chevauchent.
    """
    ordered = sorted(intervals, key=lambda item: (item.start, item.end))
    conflicts: list[tuple[ActivityInterval, ActivityInterval]] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous.overlaps(current):
            conflicts.append((previous, current))
    return tuple(conflicts)


def normalize_intervals(
    intervals: Iterable[ActivityInterval],
    *,
    drop_empty: bool = True,
    on_overlap: str = "error",
) -> tuple[ActivityInterval, ...]:
    """Trie et verifie une suite d'intervalles.

    Args:
        intervals: Intervalles a normaliser.
        drop_empty: Supprime les intervalles de duree nulle.
        on_overlap: Comportement en cas de chevauchement :

            * ``"error"`` : leve une :class:`AnalysisError` (defaut) ;
            * ``"truncate"`` : tronque l'intervalle precedent a la date de debut du
              suivant, en conservant l'ordre chronologique ;
            * ``"keep"`` : conserve les intervalles tels quels.

    Returns:
        Les intervalles tries chronologiquement.

    Raises:
        AnalysisError: Un chevauchement a ete detecte alors que ``on_overlap`` vaut
            ``"error"``, ou la valeur de ``on_overlap`` est inconnue.
    """
    if on_overlap not in {"error", "truncate", "keep"}:
        raise AnalysisError(
            "Parametre d'analyse invalide.",
            technical_detail=f"on_overlap='{on_overlap}' inconnu",
        )

    ordered = sorted(intervals, key=lambda item: (item.start, item.end))
    if drop_empty:
        ordered = [item for item in ordered if not item.is_empty]

    if on_overlap == "keep":
        return tuple(ordered)

    conflicts = find_overlaps(ordered)
    if conflicts and on_overlap == "error":
        first, second = conflicts[0]
        raise AnalysisError(
            "Les periodes d'activite se chevauchent.",
            cause=(
                "Deux enregistrements couvrent la meme plage horaire, ce qui empeche "
                "un calcul fiable des temps."
            ),
            action=(
                "Verifiez les fichiers importes pour ce conducteur : un meme "
                "telechargement a peut-etre ete enregistre depuis deux sources."
            ),
            technical_detail=(
                f"{len(conflicts)} chevauchement(s), premier entre "
                f"{first.start.isoformat()}-{first.end.isoformat()} et "
                f"{second.start.isoformat()}-{second.end.isoformat()}"
            ),
        )

    result: list[ActivityInterval] = []
    for interval in ordered:
        if result and interval.start < result[-1].end:
            previous = result[-1]
            if interval.start <= previous.start:
                # L'intervalle precedent est entierement recouvert : il disparait.
                result.pop()
            else:
                result[-1] = previous.with_bounds(previous.start, interval.start)
        result.append(interval)
    return tuple(item for item in result if not (drop_empty and item.is_empty))


def merge_adjacent(
    intervals: Sequence[ActivityInterval], *, tolerance_seconds: int = 0
) -> tuple[ActivityInterval, ...]:
    """Fusionne les intervalles consecutifs de meme type.

    Un tachygraphe enregistre un changement d'activite par minute : une meme
    periode de conduite peut donc apparaitre decoupee en plusieurs enregistrements
    contigus. Les fusionner est necessaire pour raisonner sur des periodes reelles.

    Args:
        intervals: Intervalles normalises et tries.
        tolerance_seconds: Ecart maximal tolere entre deux intervalles pour les
            considerer contigus. ``0`` exige une continuite exacte.

    Returns:
        Les intervalles fusionnes.

    Raises:
        ValueError: ``tolerance_seconds`` est negatif.
    """
    if tolerance_seconds < 0:
        raise ValueError("tolerance_seconds ne peut pas etre negatif")
    if not intervals:
        return ()

    tolerance = timedelta(seconds=tolerance_seconds)
    merged: list[ActivityInterval] = [intervals[0]]
    for interval in intervals[1:]:
        current = merged[-1]
        same_type = interval.activity_type is current.activity_type
        contiguous = interval.start - current.end <= tolerance
        if same_type and contiguous:
            merged[-1] = current.with_bounds(current.start, max(current.end, interval.end))
        else:
            merged.append(interval)
    return tuple(merged)


def clip_to_period(
    intervals: Iterable[ActivityInterval],
    period_start: datetime,
    period_end: datetime,
) -> tuple[ActivityInterval, ...]:
    """Borne une suite d'intervalles a une periode.

    Une activite a cheval sur les bornes est decoupee : seule sa partie interne a la
    periode est conservee. C'est indispensable pour des totaux journaliers exacts.

    Args:
        intervals: Intervalles a borner.
        period_start: Debut de la periode (inclus).
        period_end: Fin de la periode (exclu).

    Returns:
        Les portions d'intervalles contenues dans la periode, triees.

    Raises:
        AnalysisError: La periode est invalide (fin avant debut).
    """
    start = ensure_utc(period_start)
    end = ensure_utc(period_end)
    if end < start:
        raise AnalysisError(
            "La periode d'analyse est invalide.",
            cause="La date de fin precede la date de debut.",
            action="Corrigez la periode selectionnee.",
        )
    clipped = [item for interval in intervals if (item := interval.clip(start, end)) is not None]
    return tuple(sorted(clipped, key=lambda item: (item.start, item.end)))


def find_gaps(
    intervals: Sequence[ActivityInterval],
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    minimum_seconds: int = 60,
) -> tuple[tuple[datetime, datetime], ...]:
    """Identifie les periodes sans enregistrement.

    Args:
        intervals: Intervalles normalises et tries.
        period_start: Si fourni, detecte aussi un trou avant le premier intervalle.
        period_end: Si fourni, detecte aussi un trou apres le dernier intervalle.
        minimum_seconds: Duree minimale d'un trou pour etre signale.

    Returns:
        Les couples ``(debut, fin)`` des periodes non couvertes.
    """
    minimum = timedelta(seconds=max(minimum_seconds, 0))
    gaps: list[tuple[datetime, datetime]] = []

    if period_start is not None and intervals:
        start = ensure_utc(period_start)
        if intervals[0].start - start >= minimum:
            gaps.append((start, intervals[0].start))

    for previous, current in zip(intervals, intervals[1:], strict=False):
        if current.start - previous.end >= minimum:
            gaps.append((previous.end, current.start))

    if period_end is not None and intervals:
        end = ensure_utc(period_end)
        if end - intervals[-1].end >= minimum:
            gaps.append((intervals[-1].end, end))

    if period_start is not None and period_end is not None and not intervals:
        start, end = ensure_utc(period_start), ensure_utc(period_end)
        if end - start >= minimum:
            gaps.append((start, end))

    return tuple(gaps)


def split_by_day(
    intervals: Iterable[ActivityInterval],
) -> dict[date, tuple[ActivityInterval, ...]]:
    """Repartit des intervalles par jour calendaire UTC.

    Un intervalle a cheval sur minuit est decoupe : chaque journee recoit la portion
    qui lui appartient, afin que les totaux journaliers soient exacts.

    Args:
        intervals: Intervalles a repartir.

    Returns:
        Un dictionnaire ``jour -> intervalles``, trie par jour croissant.
    """
    by_day: dict[date, list[ActivityInterval]] = {}
    for interval in intervals:
        cursor = interval.start
        while cursor < interval.end:
            day_start, day_end = day_bounds(cursor)
            portion = interval.clip(day_start, min(day_end, interval.end))
            if portion is not None:
                by_day.setdefault(day_start.date(), []).append(portion)
            cursor = day_end
    return {
        day: tuple(sorted(items, key=lambda item: (item.start, item.end)))
        for day, items in sorted(by_day.items())
    }


def summarize_days(intervals: Iterable[ActivityInterval]) -> tuple[DaySummary, ...]:
    """Produit une synthese par journee.

    Args:
        intervals: Intervalles normalises.

    Returns:
        Une synthese par jour comportant au moins une activite, par jour croissant.
    """
    return tuple(
        DaySummary(day=day, totals=PeriodTotals.from_intervals(items), intervals=items)
        for day, items in split_by_day(intervals).items()
    )


def filter_by_type(
    intervals: Iterable[ActivityInterval], *types: ActivityType
) -> tuple[ActivityInterval, ...]:
    """Retourne les intervalles correspondant aux types demandes."""
    wanted = set(types)
    return tuple(interval for interval in intervals if interval.activity_type in wanted)
