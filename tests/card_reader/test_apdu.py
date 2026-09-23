"""Tests de la couche APDU.

Perimetre teste : uniquement ce que la norme ISO/IEC 7816-4 definit, c'est-a-dire la
**forme** des commandes et la signification des mots d'etat generiques. Aucun test ne
verifie un identifiant de fichier ou une sequence propre a la carte tachygraphique :
ces elements ne sont pas confirmes, et un test qui les figerait leur donnerait une
apparence de validite.
"""

from __future__ import annotations

import pytest

from app.card_reader.apdu import (
    CLA_ISO,
    INS_GET_RESPONSE,
    INS_READ_BINARY,
    INS_SELECT,
    APDUCommand,
    APDUResponse,
    StatusWord,
    get_response,
    read_binary,
    select_file_by_identifier,
)
from app.core.exceptions import CardCommunicationError


# --------------------------------------------------------------------------- #
# Serialisation des commandes
# --------------------------------------------------------------------------- #
def test_une_commande_sans_donnees_tient_sur_quatre_octets() -> None:
    commande = APDUCommand(cla=0x00, ins=0xA4, p1=0x04, p2=0x0C)

    assert commande.to_bytes() == b"\x00\xa4\x04\x0c"


def test_le_champ_lc_precede_les_donnees() -> None:
    commande = APDUCommand(cla=0x00, ins=0xA4, data=b"\x3f\x00")

    assert commande.to_bytes() == b"\x00\xa4\x00\x00\x02\x3f\x00"


def test_le_champ_le_est_ajoute_en_fin_de_commande() -> None:
    commande = APDUCommand(cla=0x00, ins=0xB0, expected_length=16)

    assert commande.to_bytes() == b"\x00\xb0\x00\x00\x10"


def test_une_longueur_de_256_est_codee_par_un_octet_nul() -> None:
    """Convention ISO/IEC 7816-4 : Le = 00 signifie 256 octets attendus."""
    commande = APDUCommand(cla=0x00, ins=0xB0, expected_length=256)

    assert commande.to_bytes()[-1] == 0x00


def test_la_serialisation_en_liste_correspond_aux_octets() -> None:
    commande = APDUCommand(cla=0x00, ins=0xB0, expected_length=8)

    assert commande.to_list() == list(commande.to_bytes())


@pytest.mark.parametrize("champ", ["cla", "ins", "p1", "p2"])
def test_un_champ_hors_borne_est_refuse(champ: str) -> None:
    arguments = {"cla": 0x00, "ins": 0xA4, "p1": 0x00, "p2": 0x00}
    arguments[champ] = 0x100

    with pytest.raises(ValueError, match=champ):
        APDUCommand(**arguments)  # type: ignore[arg-type]


def test_un_champ_de_donnees_trop_long_est_refuse() -> None:
    with pytest.raises(ValueError, match="255"):
        APDUCommand(cla=0x00, ins=0xA4, data=b"\x00" * 256)


def test_une_longueur_attendue_hors_borne_est_refusee() -> None:
    with pytest.raises(ValueError, match="expected_length"):
        APDUCommand(cla=0x00, ins=0xB0, expected_length=257)


def test_la_description_ne_journalise_pas_les_donnees() -> None:
    """Le champ de donnees peut porter des elements d'authentification."""
    commande = APDUCommand(cla=0x00, ins=0xA4, data=b"\xde\xad\xbe\xef")

    description = commande.describe()

    assert "Lc=4" in description
    assert "dead" not in description.lower()
    assert "DEADBEEF" not in description


def test_la_description_mentionne_la_longueur_attendue() -> None:
    assert "Le=16" in APDUCommand(cla=0x00, ins=0xB0, expected_length=16).describe()


# --------------------------------------------------------------------------- #
# Commandes generiques
# --------------------------------------------------------------------------- #
def test_select_file_utilise_la_forme_normalisee() -> None:
    commande = select_file_by_identifier(b"\x3f\x00")

    assert (commande.cla, commande.ins, commande.p1, commande.p2) == (
        CLA_ISO,
        INS_SELECT,
        0x00,
        0x0C,
    )
    assert commande.data == b"\x3f\x00"


def test_select_file_exige_un_identifiant_de_deux_octets() -> None:
    with pytest.raises(ValueError, match="2 octets"):
        select_file_by_identifier(b"\x3f")


def test_read_binary_repartit_le_decalage_sur_p1_et_p2() -> None:
    commande = read_binary(offset=0x0123, length=64)

    assert (commande.cla, commande.ins) == (CLA_ISO, INS_READ_BINARY)
    assert (commande.p1, commande.p2) == (0x01, 0x23)
    assert commande.expected_length == 64


def test_read_binary_refuse_un_decalage_hors_borne() -> None:
    with pytest.raises(ValueError, match="offset"):
        read_binary(offset=0x8000, length=1)


@pytest.mark.parametrize("longueur", [0, 257])
def test_read_binary_refuse_une_longueur_hors_borne(longueur: int) -> None:
    with pytest.raises(ValueError, match="length"):
        read_binary(offset=0, length=longueur)


def test_get_response_demande_la_longueur_indiquee() -> None:
    commande = get_response(120)

    assert (commande.cla, commande.ins) == (CLA_ISO, INS_GET_RESPONSE)
    assert commande.expected_length == 120


def test_get_response_refuse_une_longueur_nulle() -> None:
    with pytest.raises(ValueError, match="length"):
        get_response(0)


# --------------------------------------------------------------------------- #
# Mots d'etat
# --------------------------------------------------------------------------- #
def test_le_mot_d_etat_est_recompose_sur_seize_bits() -> None:
    reponse = APDUResponse(data=b"", sw1=0x90, sw2=0x00)

    assert reponse.status_word == 0x9000
    assert reponse.is_success


def test_une_reponse_61xx_annonce_des_donnees_supplementaires() -> None:
    reponse = APDUResponse(data=b"", sw1=0x61, sw2=0x20)

    assert reponse.has_more_data
    assert reponse.available_length == 32
    assert not reponse.is_success


def test_une_reponse_sans_suite_n_annonce_aucune_longueur() -> None:
    assert APDUResponse(data=b"", sw1=0x90, sw2=0x00).available_length is None


def test_la_construction_depuis_pyscard_convertit_les_octets() -> None:
    reponse = APDUResponse.from_pyscard([0x01, 0x02, 0x03], 0x90, 0x00)

    assert reponse.data == b"\x01\x02\x03"
    assert reponse.is_success


@pytest.mark.parametrize(
    ("mot", "fragment"),
    [
        (StatusWord.SUCCESS, "executee"),
        (StatusWord.FILE_NOT_FOUND, "introuvable"),
        (StatusWord.SECURITY_STATUS_NOT_SATISFIED, "autorise"),
        (StatusWord.INSTRUCTION_NOT_SUPPORTED, "prise en charge"),
    ],
)
def test_chaque_mot_d_etat_connu_a_un_libelle_francais(mot: StatusWord, fragment: str) -> None:
    assert fragment in mot.label


def test_un_mot_d_etat_inconnu_est_affiche_en_hexadecimal() -> None:
    """La carte peut retourner un mot d'etat qui lui est propre : il n'est pas devine."""
    libelle = APDUResponse(data=b"", sw1=0x6C, sw2=0x1F).status_label

    assert "6C1F" in libelle


def test_un_mot_d_etat_61xx_est_decrit_sans_erreur() -> None:
    assert "32" in APDUResponse(data=b"", sw1=0x61, sw2=0x20).status_label


# --------------------------------------------------------------------------- #
# Verification du mot d'etat
# --------------------------------------------------------------------------- #
def test_un_succes_traverse_la_verification() -> None:
    reponse = APDUResponse(data=b"\x00", sw1=0x90, sw2=0x00)

    assert reponse.raise_for_status(context="lecture de test") is reponse


def test_une_suite_de_donnees_traverse_la_verification() -> None:
    reponse = APDUResponse(data=b"", sw1=0x61, sw2=0x10)

    assert reponse.raise_for_status(context="lecture de test") is reponse


def test_un_refus_de_la_carte_produit_un_message_exploitable() -> None:
    reponse = APDUResponse(data=b"", sw1=0x69, sw2=0x82)

    with pytest.raises(CardCommunicationError) as erreur:
        reponse.raise_for_status(context="selection d'un fichier")

    message, cause, action = erreur.value.user_report()
    assert "selection d'un fichier" in message
    assert cause
    assert "carte" in action.lower()
    assert "Traceback" not in message


def test_le_mot_d_etat_refuse_est_journalise_en_detail_technique() -> None:
    with pytest.raises(CardCommunicationError) as erreur:
        APDUResponse(data=b"", sw1=0x6A, sw2=0x82).raise_for_status(context="lecture")

    assert "6A82" in (erreur.value.technical_detail or "")
