"""Export CSV d'une rubrique de rapport.

Separateur point-virgule et encodage UTF-8 avec marque d'ordre des octets : c'est la
forme que les tableurs configures en francais ouvrent directement.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.reports.model import ReportTable

__all__ = ["write_csv"]


def write_csv(path: Path, table: ReportTable) -> Path:
    """Ecrit un tableau au format CSV.

    Args:
        path: Fichier de destination (``.csv``).
        table: Tableau a ecrire.

    Returns:
        Le chemin du fichier ecrit.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(table.headers)
        writer.writerows(table.rows)
    return path
