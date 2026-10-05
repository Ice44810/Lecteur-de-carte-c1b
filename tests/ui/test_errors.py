"""Tests de la presentation des erreurs a l'utilisateur.

Exigence explicite du cahier des charges : ne jamais afficher une stack trace. Une
erreur se presente en trois temps, message puis cause puis action, et le detail
technique reste disponible pour le developpeur sans encombrer le message.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from app.core.exceptions import (
    DuplicateFileError,
    PCSCUnavailableError,
    StorageError,
    UnconfirmedStructureError,
    UnsupportedFileTypeError,
)
from app.ui.common.errors import confirm, format_error, show_error, show_information
from tests.ui.conftest import DialogRecorder

pytestmark = pytest.mark.ui


# --------------------------------------------------------------------------- #
# Traduction d'une exception
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "erreur",
    [
        PCSCUnavailableError(),
        UnsupportedFileTypeError(),
        UnconfirmedStructureError(),
        StorageError(),
    ],
)
def test_toute_erreur_applicative_produit_les_trois_elements(erreur: Exception) -> None:
    message, cause, action, _ = format_error(erreur)

    assert message.strip()
    assert cause.strip()
    assert action.strip()


@pytest.mark.parametrize(
    "erreur",
    [PCSCUnavailableError(), UnsupportedFileTypeError(), StorageError()],
)
def test_aucun_element_affiche_ne_contient_de_trace_technique(erreur: Exception) -> None:
    message, cause, action, _ = format_error(erreur)

    for texte in (message, cause, action):
        assert "Traceback" not in texte
        assert 'File "' not in texte


def test_le_detail_technique_est_separe_du_message() -> None:
    erreur = StorageError(technical_detail="PermissionError: /var/data")

    message, _, _, detail = format_error(erreur)

    assert detail == "PermissionError: /var/data"
    assert "PermissionError" not in message


def test_une_erreur_de_doublon_conserve_ses_informations() -> None:
    erreur = DuplicateFileError(existing_file_id=12, sha256="a" * 64)

    message, cause, action, _ = format_error(erreur)

    assert message.strip()
    assert cause.strip()
    assert action.strip()


# --------------------------------------------------------------------------- #
# Fonctionnalites non livrees
# --------------------------------------------------------------------------- #
def test_une_fonctionnalite_non_livree_est_annoncee_clairement() -> None:
    erreur = NotImplementedError("La production des rapports est prevue en phase 9.")

    message, cause, action, detail = format_error(erreur)

    assert message == "Cette fonctionnalite n'est pas encore disponible."
    assert "phase 9" in cause
    assert "README" in action
    assert detail is None


def test_une_fonctionnalite_non_livree_sans_message_reste_expliquee() -> None:
    _, cause, _, _ = format_error(NotImplementedError())

    assert cause.strip()


# --------------------------------------------------------------------------- #
# Erreur inattendue
# --------------------------------------------------------------------------- #
def test_une_erreur_inattendue_recoit_un_message_comprehensible() -> None:
    """L'utilisateur n'a pas a decoder un message d'erreur Python."""
    message, cause, action, detail = format_error(ValueError("index out of range"))

    assert message == "Une erreur inattendue est survenue."
    assert "index out of range" not in message
    assert "index out of range" not in cause
    assert detail == "ValueError: index out of range"


def test_une_erreur_inattendue_rassure_sur_les_donnees() -> None:
    _, _, action, _ = format_error(RuntimeError("echec interne"))

    assert "Aucune donnee n'a ete supprimee" in action
    assert "journal" in action.lower()


# --------------------------------------------------------------------------- #
# Affichage
# --------------------------------------------------------------------------- #
def test_l_affichage_d_une_erreur_reprend_le_message_et_la_cause(
    application, dialogs: DialogRecorder
) -> None:
    parent = QWidget()

    show_error(parent, PCSCUnavailableError(), title="Lecteur de carte")

    assert dialogs.count == 1
    titre, message, informations = dialogs.shown[0]
    assert titre == "Lecteur de carte"
    assert message == "Le service PC/SC n'est pas disponible."
    assert "Cause :" in informations
    assert "Action :" in informations


def test_l_affichage_d_une_information_n_evoque_aucune_cause(
    application, dialogs: DialogRecorder
) -> None:
    show_information(None, "Le fichier a ete archive.")

    assert dialogs.count == 1
    _, message, informations = dialogs.shown[0]
    assert message == "Le fichier a ete archive."
    assert informations == ""


def test_une_confirmation_refusee_par_defaut_retourne_faux(
    application, dialogs: DialogRecorder
) -> None:
    """La boite interceptee retourne « Ok » : aucune suppression ne peut etre confirmee."""
    assert confirm(None, "Supprimer cet import ?") is False
    assert dialogs.count == 1
