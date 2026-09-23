"""Tests des parsers C1B et V1B.

Ces tests verifient une exigence centrale du cahier des charges : **aucune structure
binaire n'est devinee**. Le decodage doit refuser de produire une valeur tant que la
structure concernee n'a pas ete confirmee, tout en laissant le reste de l'application
fonctionner (archivage, empreinte, journal des imports).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.enums import FileType
from app.core.exceptions import (
    ParsingError,
    StorageError,
    UnconfirmedStructureError,
    UnsupportedFileTypeError,
)
from app.parser import C1BParser, V1BParser, detect_file_type, get_parser_for
from app.parser.base import MINIMUM_PLAUSIBLE_SIZE
from app.parser.models import DiagnosticLevel


# --------------------------------------------------------------------------- #
# Detection du type de fichier
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("nom", "attendu"),
    [
        ("carte.C1B", FileType.C1B),
        ("carte.c1b", FileType.C1B),
        ("vehicule.V1B", FileType.V1B),
        ("M_20260915_0830.v1b", FileType.V1B),
    ],
)
def test_detection_par_extension(nom: str, attendu: FileType) -> None:
    assert detect_file_type(nom) is attendu


@pytest.mark.parametrize("nom", ["document.pdf", "archive.zip", "sans_extension", "donnees.ddd"])
def test_extension_non_prise_en_charge(nom: str) -> None:
    with pytest.raises(UnsupportedFileTypeError) as exc_info:
        detect_file_type(nom)

    message, cause, action = exc_info.value.user_report()
    assert ".C1B" in cause
    assert ".V1B" in cause
    assert message and action


def test_fabrique_de_parser() -> None:
    assert get_parser_for(FileType.C1B) is C1BParser
    assert get_parser_for(FileType.V1B) is V1BParser


# --------------------------------------------------------------------------- #
# Validation independante du format
# --------------------------------------------------------------------------- #
def test_fichier_vide_refuse_avec_une_action_claire(empty_c1b_file: Path) -> None:
    parser = C1BParser.from_path(empty_c1b_file)

    with pytest.raises(ParsingError) as exc_info:
        parser.parse()

    message, cause, action = exc_info.value.user_report()
    assert "vide" in message.lower()
    assert "0 octet" in cause
    assert "telechargement" in action.lower()


def test_fichier_tronque_refuse(tmp_path: Path) -> None:
    path = tmp_path / "tronque.C1B"
    path.write_bytes(b"\x00" * (MINIMUM_PLAUSIBLE_SIZE - 1))
    parser = C1BParser.from_path(path)

    with pytest.raises(ParsingError) as exc_info:
        parser.parse()

    assert "petit" in exc_info.value.message.lower()
    assert exc_info.value.technical_detail is not None


def test_fichier_absent_signale_un_probleme_de_stockage(tmp_path: Path) -> None:
    with pytest.raises(StorageError):
        C1BParser.from_path(tmp_path / "absent.C1B")


def test_le_parser_ne_modifie_pas_le_fichier(opaque_c1b_file: Path) -> None:
    avant = opaque_c1b_file.read_bytes()

    C1BParser.from_path(opaque_c1b_file).parse()

    assert opaque_c1b_file.read_bytes() == avant


# --------------------------------------------------------------------------- #
# Decodage : incertitude assumee
# --------------------------------------------------------------------------- #
def test_le_decodage_c1b_n_est_pas_annonce_comme_disponible(opaque_c1b_file: Path) -> None:
    parser = C1BParser.from_path(opaque_c1b_file)

    assert parser.decoding_available is False
    assert parser.blocking_questions


def test_les_extractions_c1b_refusent_d_inventer(opaque_c1b_file: Path) -> None:
    parser = C1BParser.from_path(opaque_c1b_file)

    for extraction in (
        parser.extract_driver,
        parser.extract_activities,
        parser.extract_events,
        parser.extract_technical_data,
    ):
        with pytest.raises(UnconfirmedStructureError) as exc_info:
            extraction()
        assert "confirmer" in (exc_info.value.technical_detail or "")


def test_un_telechargement_de_carte_ne_porte_pas_de_vehicule(opaque_c1b_file: Path) -> None:
    """Cas ou l'absence de valeur est une certitude, non une incertitude."""
    assert C1BParser.from_path(opaque_c1b_file).extract_vehicle() is None


def test_un_telechargement_de_vehicule_ne_porte_pas_de_titulaire(opaque_v1b_file: Path) -> None:
    assert V1BParser.from_path(opaque_v1b_file).extract_driver() is None


def test_parse_retourne_un_resultat_partiel_documente(opaque_c1b_file: Path) -> None:
    resultat = C1BParser.from_path(opaque_c1b_file).parse()

    assert resultat.file_type is FileType.C1B
    assert resultat.is_complete is False
    assert resultat.has_warnings is True
    assert resultat.driver is None
    assert resultat.activities == ()
    codes = {diagnostic.code for diagnostic in resultat.diagnostics}
    assert codes == {"STRUCTURE_NOT_CONFIRMED"}
    assert all(diagnostic.level is DiagnosticLevel.WARNING for diagnostic in resultat.diagnostics)


def test_les_diagnostics_expliquent_pourquoi_rien_n_est_decode(opaque_c1b_file: Path) -> None:
    resultat = C1BParser.from_path(opaque_c1b_file).parse()

    for diagnostic in resultat.diagnostics:
        assert "structure" in diagnostic.message.lower()
        assert diagnostic.detail


def test_parse_v1b_retourne_aussi_un_resultat_partiel(opaque_v1b_file: Path) -> None:
    resultat = V1BParser.from_path(opaque_v1b_file).parse()

    assert resultat.file_type is FileType.V1B
    assert resultat.is_complete is False
    assert resultat.has_errors is False
    assert resultat.summary()


def test_le_parser_expose_le_nom_et_la_taille(opaque_c1b_file: Path) -> None:
    parser = C1BParser.from_path(opaque_c1b_file)

    assert parser.filename == "conducteur.C1B"
    assert parser.size == opaque_c1b_file.stat().st_size


def test_le_lecteur_binaire_porte_sur_le_contenu_du_fichier(opaque_c1b_file: Path) -> None:
    parser = C1BParser.from_path(opaque_c1b_file)

    reader = parser.reader()

    assert reader.size == parser.size
    assert reader.position == 0
