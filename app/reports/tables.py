"""Mise en tableaux d'un rapport de carte.

Ces tableaux sont la source unique de l'affichage a l'ecran et des exports Excel, PDF
et CSV : un meme chiffre ne peut donc pas differer d'un support a l'autre. Ils ne
calculent rien ; ils mettent en forme un :class:`~app.services.card_report_service.CardReport`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.core.timeutils import format_duration
from app.services.card_report_service import CardReport

__all__ = ["ReportTable", "card_report_tables", "summary_table"]


@dataclass(frozen=True, slots=True)
class ReportTable:
    """Tableau d'une rubrique de rapport.

    Attributes:
        title: Intitule de la rubrique (et nom de la feuille Excel).
        headers: Intitules des colonnes.
        rows: Lignes, chacune de la longueur de ``headers``.
        emphasized: Indices des lignes a mettre en valeur (interruptions, totaux).
        note: Precision affichee sous le tableau.
    """

    title: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    emphasized: frozenset[int] = field(default_factory=frozenset)
    note: str = ""


def _date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "-"


def _text(value: object) -> str:
    return "-" if value in (None, "") else str(value)


def _duration(seconds: int | None) -> str:
    return "-" if seconds is None else format_duration(seconds)


def card_report_tables(report: CardReport) -> tuple[ReportTable, ...]:
    """Met en tableaux les six rubriques d'un rapport de carte.

    Args:
        report: Rapport calcule.

    Returns:
        Les tableaux : informations de la carte, evenements, periodes de travail,
        activites, vehicules, pays.
    """
    return (
        _info_table(report),
        _events_table(report),
        _work_periods_table(report),
        _activities_table(report),
        _vehicles_table(report),
        _places_table(report),
    )


def _week(moment: datetime) -> str:
    return str(moment.isocalendar().week)


def _info_table(report: CardReport) -> ReportTable:
    driver = report.driver
    rows = (
        ("Titulaire de la carte", ""),
        ("Nom", _text(driver.last_name)),
        ("Prenom", _text(driver.first_name)),
        ("Date de naissance", _date(driver.birth_date)),
        ("Langue", _text(driver.preferred_language)),
        ("Carte de conducteur", ""),
        ("Numero", driver.card_number),
        ("Delivree par", _text(driver.card_issuing_authority)),
        ("Pays", _text(driver.card_issuing_country)),
        ("Date de delivrance", _date(driver.card_issue_date)),
        ("Valable depuis", _date(driver.card_validity_begin)),
        ("Valable jusqu'au", _date(driver.card_expiry_date)),
        ("Permis de conduire", ""),
        ("Numero", _text(driver.licence_number)),
        ("Delivre par", _text(driver.licence_issuing_authority)),
        ("Pays", _text(driver.licence_issuing_country)),
    )
    return ReportTable(
        title="Info carte de conducteur",
        headers=("Rubrique", "Valeur"),
        rows=rows,
        emphasized=frozenset({0, 5, 12}),
        note=f"{report.files_count} telechargement(s) de carte archive(s) pour ce conducteur.",
    )


def _events_table(report: CardReport) -> ReportTable:
    rows = []
    for event in report.events:
        begin = report.local(event.begin)
        end = report.local(event.end) if event.end else None
        rows.append(
            (
                _week(begin),
                begin.strftime("%d/%m/%Y"),
                f"{begin:%H:%M}" + (f" - {end:%d/%m %H:%M}" if end else ""),
                _duration(event.duration_seconds),
                _text(event.vehicle),
                event.kind,
                event.description,
            )
        )
    return ReportTable(
        title="Evenements",
        headers=("Sem", "Date", "Periode", "Duree", "Vehicule", "Type", "Description"),
        rows=tuple(rows),
        note="" if rows else "Aucun evenement ni anomalie enregistre sur la periode.",
    )


def _work_periods_table(report: CardReport) -> ReportTable:
    headers = (
        "Debut",
        "Fin",
        "Duree",
        "Vehicules",
        "Activites",
        "Conduite",
        "Travail",
        "Disponibilite",
        "Repos",
        "Inconnu",
        "Conduite + travail",
        "Conduite + travail + dispo.",
    )
    rows: list[tuple[str, ...]] = []
    emphasized: set[int] = set()
    for period in report.work_periods:
        totals = period.totals
        rows.append(
            (
                report.local(period.start).strftime("%d/%m/%Y %H:%M"),
                report.local(period.end).strftime("%d/%m/%Y %H:%M"),
                _duration(period.span_seconds),
                ", ".join(period.vehicles) or "-",
                str(period.activities_count),
                _duration(totals.driving),
                _duration(totals.work),
                _duration(totals.availability),
                _duration(totals.rest),
                _duration(totals.unknown),
                _duration(totals.driving + totals.work),
                _duration(totals.driving + totals.work + totals.availability),
            )
        )
        if period.rest_label is not None:
            label = "Repos hebdomadaire" if period.weekly_rest else "Interruption"
            emphasized.add(len(rows))
            rows.append((f"{label} : {period.rest_label}",) + ("",) * (len(headers) - 1))
    if report.work_periods:
        totals = report.totals
        first, last = report.work_periods[0], report.work_periods[-1]
        emphasized.add(len(rows))
        rows.append(
            (
                report.local(first.start).strftime("%d/%m/%Y %H:%M"),
                report.local(last.end).strftime("%d/%m/%Y %H:%M"),
                _duration(sum(item.span_seconds for item in report.work_periods)),
                "",
                str(sum(item.activities_count for item in report.work_periods)),
                _duration(totals.driving),
                _duration(totals.work),
                _duration(totals.availability),
                _duration(totals.rest),
                _duration(totals.unknown),
                _duration(totals.driving + totals.work),
                _duration(totals.driving + totals.work + totals.availability),
            )
        )
    return ReportTable(
        title="Periodes de travail journalieres",
        headers=headers,
        rows=tuple(rows),
        emphasized=frozenset(emphasized),
        note=(
            "Deux periodes sont separees par une interruption d'au moins 9 heures. "
            "Entre parentheses : part de l'interruption comprise dans les 24 heures "
            "suivant le debut de la periode (reglement (CE) no 561/2006, art. 8 §2). "
            "Mesures indicatives, sans appreciation de conformite."
        ),
    )


def _activities_table(report: CardReport) -> ReportTable:
    rows: list[tuple[str, ...]] = []
    emphasized: set[int] = set()
    previous_end: datetime | None = None
    for line in report.activities:
        if previous_end is not None and line.start > previous_end:
            start = report.local(previous_end)
            emphasized.add(len(rows))
            rows.append(
                (
                    _week(start),
                    start.strftime("%d/%m/%Y"),
                    f"{start:%H:%M} - {report.local(line.start):%d/%m %H:%M}",
                    _duration(int((line.start - previous_end).total_seconds())),
                    "Aucun enregistrement",
                    "-",
                    "-",
                    "-",
                )
            )
        start = report.local(line.start)
        rows.append(
            (
                _week(start),
                start.strftime("%d/%m/%Y"),
                f"{start:%H:%M} - {report.local(line.end):%H:%M}",
                _duration(line.duration_seconds),
                line.activity_label,
                _text(line.vehicle),
                line.driving_status_label,
                line.card_status_label,
            )
        )
        previous_end = line.end
    return ReportTable(
        title="Activites",
        headers=(
            "Sem",
            "Date",
            "Periode",
            "Duree",
            "Activite",
            "Vehicule",
            "Statut de conduite",
            "Statut",
        ),
        rows=tuple(rows),
        emphasized=frozenset(emphasized),
        note=f"Heures exprimees dans le fuseau {report.timezone}.",
    )


def _vehicles_table(report: CardReport) -> ReportTable:
    rows = []
    for vehicle in report.vehicles:
        first = report.local(vehicle.first_use)
        last = report.local(vehicle.last_use) if vehicle.last_use else None
        rows.append(
            (
                _week(first),
                first.strftime("%d/%m/%Y"),
                f"{first:%H:%M} - {last:%H:%M}" if last else f"{first:%H:%M}",
                _duration(vehicle.duration_seconds),
                vehicle.registration,
                _text(vehicle.odometer_begin),
                _text(vehicle.odometer_end),
                _text(vehicle.distance),
            )
        )
    return ReportTable(
        title="Vehicules",
        headers=(
            "Sem",
            "Date",
            "Periode",
            "Duree",
            "Vehicule",
            "Kilometrage debut",
            "Kilometrage fin",
            "Distance",
        ),
        rows=tuple(rows),
    )


def _places_table(report: CardReport) -> ReportTable:
    rows = []
    for place in report.places:
        moment = report.local(place.entry_time)
        rows.append(
            (
                _week(moment),
                moment.strftime("%d/%m/%Y %H:%M"),
                place.country,
                _text(place.odometer),
                place.entry_label,
            )
        )
    return ReportTable(
        title="Pays",
        headers=("Sem", "Date", "Pays", "Kilometrage", "Type d'enregistrement"),
        rows=tuple(rows),
        note=(
            "La carte conserve un nombre limite de lieux : les plus anciens sont "
            "remplaces par les plus recents."
        ),
    )


def summary_table(reports: tuple[CardReport, ...]) -> ReportTable:
    """Tableau de synthese entreprise : un conducteur par ligne."""
    rows = []
    for report in reports:
        totals = report.totals
        rows.append(
            (
                report.driver.display_name,
                report.driver.card_number,
                str(len(report.work_periods)),
                _duration(totals.driving),
                _duration(totals.work),
                _duration(totals.availability),
                _duration(totals.rest),
                _duration(totals.unknown),
            )
        )
    return ReportTable(
        title="Synthese",
        headers=(
            "Conducteur",
            "Carte",
            "Periodes de travail",
            "Conduite",
            "Travail",
            "Disponibilite",
            "Repos",
            "Inconnu",
        ),
        rows=tuple(rows),
    )
