"""Tests des enumerations du domaine.

Point de vigilance reglementaire (section 11 du cahier des charges) : le vocabulaire
affiche ne doit jamais qualifier juridiquement une infraction.
"""

from __future__ import annotations

import pytest

from app.core.enums import ActivityType, FileType, ParsingStatus, RuleStatus, Severity

_MOTS_JURIDIQUES_INTERDITS = ("infraction", "delit", "sanction", "amende", "illegal")


@pytest.mark.parametrize("status", list(RuleStatus))
def test_les_libelles_de_regles_restent_prudents(status: RuleStatus) -> None:
    libelle = status.label.lower()

    for mot in _MOTS_JURIDIQUES_INTERDITS:
        assert mot not in libelle, f"le libelle « {status.label} » qualifie juridiquement"


def test_seuls_avertissement_et_depassement_sont_remontes() -> None:
    assert RuleStatus.WARNING.is_reportable
    assert RuleStatus.VIOLATION.is_reportable
    assert not RuleStatus.OK.is_reportable
    assert not RuleStatus.NOT_APPLICABLE.is_reportable


def test_le_depassement_est_presente_comme_apparent() -> None:
    assert RuleStatus.VIOLATION.label == "Depassement apparent"


@pytest.mark.parametrize(
    "enumeration", [FileType, ParsingStatus, ActivityType, RuleStatus, Severity]
)
def test_chaque_valeur_possede_un_libelle(enumeration: type) -> None:
    for member in enumeration:
        assert member.label.strip()


def test_file_type_expose_son_extension() -> None:
    assert FileType.C1B.extension == ".C1B"
    assert FileType.V1B.extension == ".V1B"


def test_les_valeurs_stockees_sont_les_noms_techniques() -> None:
    """Les valeurs en base restent stables et exploitables par une API REST."""
    assert FileType.C1B.value == "C1B"
    assert ActivityType.DRIVING.value == "DRIVING"
    assert ParsingStatus.PENDING.value == "PENDING"


def test_activity_type_couvre_les_quatre_modes_et_l_indetermine() -> None:
    assert set(ActivityType) == {
        ActivityType.DRIVING,
        ActivityType.WORK,
        ActivityType.AVAILABILITY,
        ActivityType.REST,
        ActivityType.UNKNOWN,
    }


def test_severite_est_ordonnee() -> None:
    rangs = [Severity.INFO.rank, Severity.LOW.rank, Severity.MEDIUM.rank, Severity.HIGH.rank]
    assert rangs == sorted(rangs)


def test_statut_de_decodage_terminal() -> None:
    assert ParsingStatus.SUCCESS.is_terminal
    assert ParsingStatus.FAILED.is_terminal
    assert not ParsingStatus.PENDING.is_terminal
    assert not ParsingStatus.PARTIAL.is_terminal
