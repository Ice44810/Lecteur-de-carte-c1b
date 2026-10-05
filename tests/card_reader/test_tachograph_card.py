"""Tests du telechargement d'une carte conducteur tachygraphique.

La carte est simulee par :class:`CarteSimulee`, qui repond aux commandes exactement
comme le decrit le reglement d'execution (UE) 2016/799, annexe I C, appendice 2
(TCS_37 a TCS_43, TCS_124, TCS_130). Le contenu des fichiers est volontairement
**quelconque** : ces tests verifient la sequence de commandes et l'assemblage du
fichier (appendice 7, DDP_035 a DDP_046), pas le decodage des donnees.

Deux garanties structurelles restent verifiees :

* aucune commande d'ecriture n'est jamais transmise a la carte ;
* si un point de specification de la carte repasse a l'etat ``OPEN``, aucune
  commande n'est transmise.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.card_reader import pcsc_diagnostics
from app.card_reader.apdu import APDUCommand
from app.card_reader.mock_reader import MockCardReader
from app.card_reader.pcsc_reader import diagnose_pcsc, pyscard_available
from app.card_reader.tachograph_card import AID_TACHOGRAPH_G2, CardDownload, TachographCard
from app.core.exceptions import CardCommunicationError, UnconfirmedStructureError
from app.parser import specification
from app.parser.specification import ConfirmationStatus, is_confirmed, is_referenced
from tests.card_reader.carte_simulee import (
    SIGNATURE_G1,
    SIGNATURE_G2,
    CarteSimulee,
    decouper,
    fichiers_g1,
    sw,
)


# --------------------------------------------------------------------------- #
# Telechargement complet
# --------------------------------------------------------------------------- #
def test_une_carte_de_2e_generation_est_telechargee_entierement() -> None:
    carte = CarteSimulee()

    telechargement = TachographCard(carte.lecteur()).download()

    objets = decouper(telechargement.payload)
    assert (0x0002, 0x00, carte.mf[0x0002]) in objets
    assert (0x0504, 0x00, carte.g1[0x0504]) in objets
    assert (0x0504, 0x02, carte.g2[0x0504]) in objets
    assert telechargement.has_generation_2
    assert telechargement.atr == "3B FE 96 00"


def test_chaque_fichier_signe_est_suivi_de_sa_signature() -> None:
    """DDP_046 : la signature suit immediatement les donnees du fichier."""
    objets = decouper(TachographCard(CarteSimulee().lecteur()).download().payload)

    for index, (fid, suffixe, _) in enumerate(objets):
        if suffixe in (0x01, 0x03):
            precedent = objets[index - 1]
            assert precedent[:2] == (fid, suffixe - 1)
    signatures = {(fid, suffixe): valeur for fid, suffixe, valeur in objets if suffixe % 2}
    assert signatures[(0x0520, 0x01)] == SIGNATURE_G1
    assert signatures[(0x0520, 0x03)] == SIGNATURE_G2


def test_les_certificats_ne_sont_pas_signes() -> None:
    objets = decouper(TachographCard(CarteSimulee().lecteur()).download().payload)
    etiquettes = {(fid, suffixe) for fid, suffixe, _ in objets}

    assert (0xC100, 0x00) in etiquettes
    assert (0xC100, 0x01) not in etiquettes
    assert (0xC101, 0x02) in etiquettes
    assert (0xC101, 0x03) not in etiquettes


def test_les_fichiers_exclus_par_la_specification_ne_sont_pas_lus() -> None:
    """DDP_035 exclut Card_Download ; DDP_037 ne retient pas CardMA_Certificate en G2."""
    carte = CarteSimulee()
    objets = decouper(TachographCard(carte.lecteur()).download().payload)
    etiquettes = {(fid, suffixe) for fid, suffixe, _ in objets}

    assert not any(fid == 0x050E for fid, _ in etiquettes)
    assert (0xC100, 0x02) not in etiquettes


def test_une_carte_de_1re_generation_ne_produit_aucun_objet_g2() -> None:
    carte = CarteSimulee(g2=None)

    telechargement = TachographCard(carte.lecteur()).download()

    assert not telechargement.has_generation_2
    assert all(suffixe in (0x00, 0x01) for _, suffixe, _ in decouper(telechargement.payload))


def test_les_fichiers_facultatifs_absents_sont_signales_sans_echec() -> None:
    telechargement = TachographCard(CarteSimulee().lecteur()).download()

    assert "G2:Border_Crossings" in telechargement.skipped
    assert "G2:Border_Crossings" not in telechargement.files


def test_un_fichier_volumineux_est_lu_en_plusieurs_blocs() -> None:
    carte = CarteSimulee()

    TachographCard(carte.lecteur()).download()

    lectures = [commande for commande in carte.commandes if commande.ins == 0xB0]
    assert max((commande.p1 << 8) | commande.p2 for commande in lectures) > 13_000
    assert all(commande.p1 & 0x80 == 0 for commande in lectures)


def test_une_fin_de_fichier_sans_longueur_indiquee_est_geree() -> None:
    carte = CarteSimulee(longueur_obscure=True)

    objets = decouper(TachographCard(carte.lecteur()).download().payload)

    assert (0x0504, 0x00, carte.g1[0x0504]) in objets


def test_une_signature_differee_est_recuperee_par_get_response() -> None:
    """Protocole T=0 : la carte annonce la signature par 61xx (TCS_32)."""
    carte = CarteSimulee(reponse_differee=True)

    objets = decouper(TachographCard(carte.lecteur()).download().payload)

    assert (0x0520, 0x01, SIGNATURE_G1) in objets


def test_aucune_commande_d_ecriture_n_est_transmise() -> None:
    """Le telechargement est en lecture seule : ni UPDATE BINARY, ni WRITE."""
    carte = CarteSimulee()

    TachographCard(carte.lecteur()).download()

    assert {commande.ins for commande in carte.commandes} <= {0xA4, 0xB0, 0x2A, 0xC0}


# --------------------------------------------------------------------------- #
# Refus
# --------------------------------------------------------------------------- #
def test_une_carte_qui_n_est_pas_une_carte_conducteur_est_refusee() -> None:
    carte = CarteSimulee(g1=fichiers_g1(type_carte=4))

    with pytest.raises(CardCommunicationError) as erreur:
        TachographCard(carte.lecteur()).download()

    assert "cartes conducteur" in erreur.value.message
    assert not any(commande.ins == 0x2A for commande in carte.commandes)


def test_un_fichier_obligatoire_absent_interrompt_le_telechargement() -> None:
    fichiers = fichiers_g1()
    del fichiers[0x0504]

    with pytest.raises(CardCommunicationError) as erreur:
        TachographCard(CarteSimulee(g1=fichiers).lecteur()).download()

    assert "Driver_Activity_Data" in erreur.value.cause


def test_une_carte_sans_application_tachygraphique_est_refusee() -> None:
    lecteur = MockCardReader(response_factory=lambda commande: sw(0x6A82))

    with pytest.raises(CardCommunicationError):
        TachographCard(lecteur).download()


def test_un_point_de_specification_ouvert_bloque_toute_commande(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garde-fou structurel : sans reference officielle, la carte n'est pas sollicitee."""
    questions = tuple(
        replace(question, status=ConfirmationStatus.OPEN)
        if question.code == "CARD_FILE_IDENTIFIERS"
        else question
        for question in specification.OPEN_QUESTIONS
    )
    monkeypatch.setattr(specification, "OPEN_QUESTIONS", questions)
    carte = CarteSimulee()

    with pytest.raises(UnconfirmedStructureError) as erreur:
        TachographCard(carte.lecteur()).download()

    assert "CARD_FILE_IDENTIFIERS" in (erreur.value.technical_detail or "")
    assert carte.commandes == []


def test_le_domaine_carte_est_reference_mais_pas_encore_confirme() -> None:
    """Valide sur materiel reel avant de passer a CONFIRMED (fichier de test requis)."""
    assert is_referenced("card") is True
    assert is_confirmed("card") is False


# --------------------------------------------------------------------------- #
# Operations elementaires
# --------------------------------------------------------------------------- #
def test_un_fichier_elementaire_se_lit_integralement() -> None:
    carte = CarteSimulee()
    lecteur = carte.lecteur()
    lecteur.connect()
    tachygraphe = TachographCard(lecteur)

    assert tachygraphe.select_application() is True
    assert tachygraphe.read_elementary_file(b"\x05\x04") == carte.g1[0x0504]


def test_une_application_absente_est_signalee_sans_exception() -> None:
    lecteur = CarteSimulee(g2=None).lecteur()
    lecteur.connect()

    assert TachographCard(lecteur).select_application(AID_TACHOGRAPH_G2) is False


def test_l_etat_du_lecteur_reste_consultable() -> None:
    lecteur = MockCardReader(atr="3B 7F")

    etat = TachographCard(lecteur).presence()

    assert etat.card_present is True
    assert etat.atr == "3B 7F"


def test_une_commande_brute_exige_une_connexion() -> None:
    carte = TachographCard(MockCardReader())

    with pytest.raises(CardCommunicationError) as erreur:
        carte.transmit(APDUCommand(cla=0x00, ins=0xA4))

    _, _, action = erreur.value.user_report()
    assert "Connectez la carte" in action


def test_la_carte_expose_son_lecteur() -> None:
    lecteur = MockCardReader()

    assert TachographCard(lecteur).reader is lecteur


def test_le_resultat_de_telechargement_mesure_les_octets_recus() -> None:
    telechargement = CardDownload(payload=b"\x00" * 128, atr="3B 7F", reader_name="Lecteur A")

    assert telechargement.size == 128
    assert telechargement.reader_name == "Lecteur A"


# --------------------------------------------------------------------------- #
# Diagnostic de la pile PC/SC
# --------------------------------------------------------------------------- #
def test_le_diagnostic_retourne_toujours_un_triplet_exploitable() -> None:
    disponible, cause, action = diagnose_pcsc()

    assert isinstance(disponible, bool)
    assert cause.strip()
    assert isinstance(action, str)


def test_le_diagnostic_est_expose_par_le_paquet() -> None:
    assert pcsc_diagnostics() == diagnose_pcsc()


def test_la_disponibilite_de_pyscard_est_un_booleen() -> None:
    """L'absence de pyscard est un cas normal, pas une erreur."""
    assert isinstance(pyscard_available(), bool)


# --------------------------------------------------------------------------- #
# Longueur des signatures (TCS_130)
# --------------------------------------------------------------------------- #
def test_la_signature_g1_est_demandee_avec_sa_longueur_exacte() -> None:
    carte = CarteSimulee()

    TachographCard(carte.lecteur()).download()

    signatures = [commande for commande in carte.commandes if commande.p1 == 0x9E]
    assert all(commande.expected_length in (128, 64) for commande in signatures)
    assert not any(commande.expected_length == 256 for commande in signatures)


@pytest.mark.parametrize("taille", [64, 96, 128, 132])
def test_la_longueur_de_signature_g2_depend_de_la_courbe(taille: int) -> None:
    signature = bytes(range(taille))
    carte = CarteSimulee(signature_g2=signature)

    objets = decouper(TachographCard(carte.lecteur()).download().payload)

    assert (0x0520, 0x03, signature) in objets


def test_la_longueur_acceptee_est_reutilisee_pour_les_fichiers_suivants() -> None:
    carte = CarteSimulee(signature_g2=bytes(132))

    TachographCard(carte.lecteur()).download()

    refus = [
        commande
        for commande in carte.commandes
        if commande.p1 == 0x9E and commande.expected_length not in (128, 132)
    ]
    # 64 et 96 ne sont essayes qu'une fois, pour le premier fichier signe en G2.
    assert len(refus) == 2
