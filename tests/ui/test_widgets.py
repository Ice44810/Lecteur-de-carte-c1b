"""Tests des widgets communs : tri des tableaux et identite des lignes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from PySide6.QtCore import Qt

from app.ui.common.formatting import format_local_datetime
from app.ui.common.widgets import ReadOnlyTable, sort_key


@pytest.mark.parametrize(
    ("avant", "apres"),
    [
        ("15/09/2026", "02/10/2026"),
        ("31/12/2025 23:59", "01/01/2026 00:00"),
        ("9", "10"),
        ("09h30", "100h00"),
        ("Durand", "martin"),
        ("10", "-"),
    ],
)
def test_les_valeurs_sont_triees_selon_leur_sens(avant: str, apres: str) -> None:
    assert sort_key(avant) < sort_key(apres)


def test_la_ligne_selectionnee_reste_identifiee_apres_un_tri(application) -> None:
    tableau = ReadOnlyTable(("Date", "Fichier"))
    tableau.set_rows(
        (("15/09/2026", "a.C1B"), ("02/10/2026", "b.C1B"), ("01/08/2026", "c.C1B")),
        keys=(11, 22, 33),
    )

    tableau.sortItems(0, Qt.SortOrder.AscendingOrder)
    tableau.selectRow(0)

    assert tableau.item(0, 1).text() == "c.C1B"
    assert tableau.selected_key() == 33


def test_un_nombre_de_cles_incoherent_est_refuse(application) -> None:
    with pytest.raises(ValueError):
        ReadOnlyTable(("A",)).set_rows((("x",),), keys=(1, 2))


def test_une_date_est_affichee_dans_le_fuseau_configure() -> None:
    hiver = datetime(2026, 1, 15, 8, 30, tzinfo=UTC)
    ete = datetime(2026, 7, 15, 8, 30, tzinfo=UTC)

    assert format_local_datetime(hiver, "Europe/Paris") == "15/01/2026 09:30"
    assert format_local_datetime(ete, "Europe/Paris") == "15/07/2026 10:30"
    assert format_local_datetime(None, "Europe/Paris") == "-"


def test_l_ordre_des_lignes_fournies_est_conserve(application) -> None:
    """Sans action de l'utilisateur, aucun tri automatique ne reordonne les lignes."""
    tableau = ReadOnlyTable(("Date", "Activite"))

    tableau.set_rows((("01/10/2025", "a"), ("02/10/2025", "b"), ("03/10/2025", "c")))

    assert [tableau.item(ligne, 1).text() for ligne in range(3)] == ["a", "b", "c"]


def test_un_tableau_structure_n_est_pas_triable(application) -> None:
    tableau = ReadOnlyTable(("Debut",), sortable=False)

    tableau.set_rows((("Total",), ("01/10/2025",)))

    assert tableau.isSortingEnabled() is False
    assert tableau.item(0, 0).text() == "Total"
