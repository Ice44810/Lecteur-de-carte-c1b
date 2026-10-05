"""Tests des modeles de donnee decodee.

Ces modeles constituent le contrat entre le decodage et la couche metier. Deux
proprietes sont testees en priorite, parce qu'elles decoulent directement des
consignes du cahier des charges :

* **aucun champ n'est devine** : un champ non lu vaut ``None``, jamais une valeur par
  defaut plausible ;
* **tout doute est trace** : les diagnostics et les blocs non interpretes restent
  visibles, afin que l'utilisateur sache ce qui a ete lu et ce qui a ete ignore.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.core.enums import ActivityType, FileType
from app.parser.models import (
    DecodedActivityPeriod,
    DecodedDriverIdentification,
    DecodedEvent,
    DecodedTechnicalData,
    DecodedVehicleIdentification,
    DiagnosticLevel,
    ParseDiagnostic,
    ParseResult,
    RawBlock,
)

JOUR = datetime(2026, 9, 15, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("niveau", "libelle"),
    [
        (DiagnosticLevel.INFO, "Information"),
        (DiagnosticLevel.WARNING, "Avertissement"),
        (DiagnosticLevel.ERROR, "Erreur"),
    ],
)
def test_chaque_niveau_de_diagnostic_a_un_libelle(niveau: DiagnosticLevel, libelle: str) -> None:
    assert niveau.label == libelle


def test_un_diagnostic_porte_un_code_stable() -> None:
    diagnostic = ParseDiagnostic(
        level=DiagnosticLevel.WARNING,
        code="STRUCTURE_NOT_CONFIRMED",
        message="Structure non confirmee par une specification officielle.",
        offset=128,
    )

    assert diagnostic.code == "STRUCTURE_NOT_CONFIRMED"
    assert diagnostic.offset == 128


def test_un_diagnostic_sans_message_est_refuse() -> None:
    with pytest.raises(ValidationError):
        ParseDiagnostic(level=DiagnosticLevel.INFO, code="X", message="")


def test_un_diagnostic_est_immuable() -> None:
    diagnostic = ParseDiagnostic(level=DiagnosticLevel.INFO, code="LU", message="Bloc lu.")

    with pytest.raises(ValidationError):
        diagnostic.code = "AUTRE"  # type: ignore[misc]


def test_un_decalage_negatif_est_refuse() -> None:
    with pytest.raises(ValidationError):
        ParseDiagnostic(level=DiagnosticLevel.INFO, code="X", message="Message", offset=-1)


# --------------------------------------------------------------------------- #
# Blocs bruts
# --------------------------------------------------------------------------- #
def test_un_bloc_est_non_interprete_par_defaut() -> None:
    """Un bloc isole n'est pas repute compris : c'est le comportement prudent."""
    bloc = RawBlock(tag="0501", offset=0, length=32)

    assert bloc.interpreted is False


def test_une_longueur_negative_est_refusee() -> None:
    with pytest.raises(ValidationError):
        RawBlock(tag="0501", offset=0, length=-1)


# --------------------------------------------------------------------------- #
# Identification du conducteur
# --------------------------------------------------------------------------- #
def test_seul_le_numero_de_carte_est_obligatoire() -> None:
    identite = DecodedDriverIdentification(card_number="F1234567890123")

    assert identite.first_name is None
    assert identite.last_name is None
    assert identite.birth_date is None
    assert identite.card_expiry_date is None


def test_un_numero_de_carte_vide_est_refuse() -> None:
    with pytest.raises(ValidationError):
        DecodedDriverIdentification(card_number="")


def test_des_dates_de_carte_incoherentes_sont_refusees() -> None:
    """Mieux vaut refuser une lecture incoherente que l'enregistrer telle quelle."""
    with pytest.raises(ValidationError, match="expiration"):
        DecodedDriverIdentification(
            card_number="F1234567890123",
            card_issue_date=date(2026, 1, 1),
            card_expiry_date=date(2025, 1, 1),
        )


def test_des_dates_de_carte_coherentes_sont_acceptees() -> None:
    identite = DecodedDriverIdentification(
        card_number="F1234567890123",
        card_issue_date=date(2021, 1, 1),
        card_expiry_date=date(2026, 1, 1),
    )

    assert identite.card_expiry_date == date(2026, 1, 1)


def test_les_espaces_de_remplissage_sont_retires() -> None:
    identite = DecodedDriverIdentification(card_number="  F1234567890123  ", last_name="  DURAND  ")

    assert identite.card_number == "F1234567890123"
    assert identite.last_name == "DURAND"


# --------------------------------------------------------------------------- #
# Identification du vehicule
# --------------------------------------------------------------------------- #
def test_seule_l_immatriculation_est_obligatoire() -> None:
    vehicule = DecodedVehicleIdentification(registration="AA-123-BB")

    assert vehicule.vin is None
    assert vehicule.registration_country is None
    assert vehicule.tachograph_identifier is None


def test_une_immatriculation_vide_est_refusee() -> None:
    with pytest.raises(ValidationError):
        DecodedVehicleIdentification(registration="")


# --------------------------------------------------------------------------- #
# Periodes d'activite
# --------------------------------------------------------------------------- #
def test_une_periode_calcule_sa_duree() -> None:
    periode = DecodedActivityPeriod(
        activity_type=ActivityType.DRIVING,
        start=JOUR,
        end=JOUR.replace(hour=4, minute=30),
    )

    assert periode.duration_seconds == 16200


def test_une_periode_inversee_est_refusee() -> None:
    with pytest.raises(ValidationError, match="preceder"):
        DecodedActivityPeriod(
            activity_type=ActivityType.DRIVING,
            start=JOUR.replace(hour=10),
            end=JOUR.replace(hour=8),
        )


@pytest.mark.parametrize("emplacement", [0, 3])
def test_un_emplacement_de_carte_invalide_est_refuse(emplacement: int) -> None:
    with pytest.raises(ValidationError):
        DecodedActivityPeriod(
            activity_type=ActivityType.DRIVING,
            start=JOUR,
            end=JOUR.replace(hour=1),
            card_slot=emplacement,
        )


# --------------------------------------------------------------------------- #
# Evenements et donnees techniques
# --------------------------------------------------------------------------- #
def test_le_code_d_evenement_est_conserve_sans_traduction() -> None:
    """La table des types d'evenements n'est pas confirmee : rien n'est traduit."""
    evenement = DecodedEvent(event_type_code="0A", begin=JOUR)

    assert evenement.event_type_code == "0A"
    assert evenement.description is None
    assert evenement.end is None


def test_les_donnees_techniques_sont_toutes_optionnelles() -> None:
    technique = DecodedTechnicalData()

    assert technique.card_number is None
    assert technique.download_datetime is None
    assert technique.generation is None
    assert technique.raw_blocks == ()


# --------------------------------------------------------------------------- #
# Resultat de decodage
# --------------------------------------------------------------------------- #
def test_un_resultat_vide_n_est_pas_declare_complet() -> None:
    resultat = ParseResult(file_type=FileType.C1B)

    assert resultat.is_complete is False
    assert resultat.driver is None
    assert resultat.activities == ()


def test_les_activites_sont_triees_chronologiquement() -> None:
    tardive = DecodedActivityPeriod(
        activity_type=ActivityType.DRIVING,
        start=JOUR.replace(hour=10),
        end=JOUR.replace(hour=12),
    )
    matinale = DecodedActivityPeriod(
        activity_type=ActivityType.WORK,
        start=JOUR.replace(hour=6),
        end=JOUR.replace(hour=7),
    )

    resultat = ParseResult(file_type=FileType.C1B, activities=(tardive, matinale))

    assert resultat.activities[0] is matinale


def test_les_diagnostics_sont_classes_par_gravite() -> None:
    resultat = ParseResult(
        file_type=FileType.C1B,
        diagnostics=(
            ParseDiagnostic(level=DiagnosticLevel.WARNING, code="A", message="Bloc ignore."),
            ParseDiagnostic(level=DiagnosticLevel.ERROR, code="B", message="Decodage interrompu."),
        ),
    )

    assert resultat.has_warnings is True
    assert resultat.has_errors is True


def test_un_resultat_sans_diagnostic_ne_signale_rien() -> None:
    resultat = ParseResult(file_type=FileType.V1B)

    assert resultat.has_errors is False
    assert resultat.has_warnings is False


def test_les_blocs_non_interpretes_restent_visibles() -> None:
    """Ce qui n'a pas ete compris doit pouvoir etre montre, pas masque."""
    resultat = ParseResult(
        file_type=FileType.C1B,
        raw_blocks=(
            RawBlock(tag="0501", offset=0, length=16, interpreted=True),
            RawBlock(tag="0502", offset=16, length=32),
        ),
    )

    assert len(resultat.uninterpreted_blocks) == 1
    assert resultat.uninterpreted_blocks[0].tag == "0502"


def test_le_resume_enumere_ce_qui_a_ete_lu() -> None:
    resultat = ParseResult(
        file_type=FileType.C1B,
        driver=DecodedDriverIdentification(card_number="F1234567890123"),
        vehicle=DecodedVehicleIdentification(registration="AA-123-BB"),
        activities=(
            DecodedActivityPeriod(
                activity_type=ActivityType.DRIVING,
                start=JOUR,
                end=JOUR.replace(hour=2),
            ),
        ),
        events=(DecodedEvent(event_type_code="0A", begin=JOUR),),
        raw_blocks=(RawBlock(tag="0502", offset=0, length=8),),
    )

    resume = resultat.summary()

    assert "1 periode(s) d'activite" in resume
    assert "conducteur identifie" in resume
    assert "vehicule identifie" in resume
    assert "1 evenement(s)" in resume
    assert "1 bloc(s) non interprete(s)" in resume


def test_le_resume_d_un_resultat_vide_reste_exploitable() -> None:
    assert ParseResult(file_type=FileType.C1B).summary() == "0 periode(s) d'activite"
