"""Modele de tableau de rapport, sans dependance.

Partage par les services (qui produisent des tableaux) et par les generateurs (qui
les ecrivent en Excel, PDF ou CSV), sans que l'un depende de l'autre.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["ReportTable"]


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
