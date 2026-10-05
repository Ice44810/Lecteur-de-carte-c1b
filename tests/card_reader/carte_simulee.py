"""Carte conducteur simulee pour les tests.

:class:`CarteSimulee` repond aux commandes exactement comme le decrit le reglement
d'execution (UE) 2016/799, annexe I C, appendice 2 (TCS_37 a TCS_43, TCS_124,
TCS_130). Le contenu des fichiers est volontairement **quelconque** : il ne pretend
reproduire aucune donnee tachygraphique reelle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.card_reader.apdu import APDUCommand, APDUResponse
from app.card_reader.mock_reader import MockCardReader
from app.card_reader.tachograph_card import (
    AID_TACHOGRAPH_G1,
    AID_TACHOGRAPH_G2,
    G1_FILES,
    G2_FILES,
)

SIGNATURE_G1 = bytes(range(128))
SIGNATURE_G2 = bytes(range(64))
"""Signature de 2e generation d'une carte a courbe de 256 bits (r || s)."""


def ok(data: bytes = b"") -> APDUResponse:
    return APDUResponse(data=data, sw1=0x90, sw2=0x00)


def sw(value: int, data: bytes = b"") -> APDUResponse:
    return APDUResponse(data=data, sw1=value >> 8, sw2=value & 0xFF)


def contenu(fid: int, taille: int) -> bytes:
    """Contenu quelconque mais reconnaissable d'un fichier."""
    return bytes((fid + index) & 0xFF for index in range(taille))


def fichiers_g1(type_carte: int = 1) -> dict[int, bytes]:
    fichiers = {item.fid: contenu(item.fid, 40) for item in G1_FILES}
    fichiers[0x0501] = bytes([type_carte]) + contenu(0x0501, 9)
    fichiers[0x0504] = contenu(0x0504, 13_780)
    fichiers[0x050E] = contenu(0x050E, 4)
    return fichiers


def fichiers_g2() -> dict[int, bytes]:
    fichiers = {item.fid: contenu(item.fid, 50) for item in G2_FILES if item.mandatory}
    fichiers[0x0501] = bytes([1]) + contenu(0x0501, 16)
    fichiers[0x050E] = contenu(0x050E, 4)
    fichiers[0xC100] = contenu(0xC100, 200)
    return fichiers


@dataclass
class CarteSimulee:
    """Carte conducteur simulee, conforme aux reponses decrites par l'appendice 2.

    Attributes:
        mf: Fichiers du MF.
        g1: Fichiers du DF Tachograph.
        g2: Fichiers du DF Tachograph_G2 (``None`` pour une carte de 1re generation).
        commandes: Commandes recues, dans l'ordre.
        longueur_obscure: Repond ``6700`` sans indication de longueur en fin de fichier.
        reponse_differee: Repond ``61xx`` aux signatures (protocole T=0).
        signature_g2: Signature renvoyee par l'application de 2e generation.
        oublie_empreinte: Efface l'empreinte apres une signature refusee.

    Comme une carte reelle, elle refuse par ``6700`` une signature demandee avec une
    longueur ``Le`` differente de la longueur exacte (TCS_130).
    """

    mf: dict[int, bytes] = field(
        default_factory=lambda: {0x0002: contenu(2, 25), 0x0005: contenu(5, 8)}
    )
    g1: dict[int, bytes] = field(default_factory=fichiers_g1)
    g2: dict[int, bytes] | None = field(default_factory=fichiers_g2)
    commandes: list[APDUCommand] = field(default_factory=list)
    longueur_obscure: bool = False
    reponse_differee: bool = False
    signature_g2: bytes = SIGNATURE_G2
    oublie_empreinte: bool = True
    _df: str = "MF"
    _ef: int | None = None
    _empreinte: bool = False
    _en_attente: bytes = b""

    def repondre(self, commande: APDUCommand) -> APDUResponse:
        self.commandes.append(commande)
        entete = (commande.cla, commande.ins, commande.p1, commande.p2)
        if entete == (0x00, 0xA4, 0x04, 0x0C):
            return self._selectionner_application(commande.data)
        if entete == (0x00, 0xA4, 0x02, 0x0C):
            return self._selectionner_fichier(int.from_bytes(commande.data, "big"))
        if (commande.cla, commande.ins) == (0x00, 0xB0):
            return self._lire(commande)
        if entete == (0x80, 0x2A, 0x90, 0x00):
            if self._ef is None or self._df == "MF":
                return sw(0x6986)
            self._empreinte = True
            return ok()
        if entete == (0x00, 0x2A, 0x9E, 0x9A):
            if not self._empreinte:
                return sw(0x6985)
            signature = SIGNATURE_G1 if self._df == "G1" else self.signature_g2
            if commande.expected_length != len(signature):
                if self.oublie_empreinte:
                    self._empreinte = False
                return sw(0x6700)
            self._empreinte = False
            if self.reponse_differee:
                self._en_attente = signature
                return sw(0x6100 | len(signature))
            return ok(signature)
        if (commande.cla, commande.ins) == (0x00, 0xC0):
            donnees, self._en_attente = self._en_attente, b""
            return ok(donnees)
        return sw(0x6D00)

    def _selectionner_application(self, aid: bytes) -> APDUResponse:
        self._ef, self._empreinte = None, False
        if aid == AID_TACHOGRAPH_G1:
            self._df = "G1"
            return ok()
        if aid == AID_TACHOGRAPH_G2 and self.g2 is not None:
            self._df = "G2"
            return ok()
        return sw(0x6A82)

    def _selectionner_fichier(self, fid: int) -> APDUResponse:
        self._empreinte = False
        if fid not in self._fichiers_courants():
            return sw(0x6A82)
        self._ef = fid
        return ok()

    def _lire(self, commande: APDUCommand) -> APDUResponse:
        if self._ef is None:
            return sw(0x6986)
        donnees = self._fichiers_courants()[self._ef]
        decalage = (commande.p1 << 8) | commande.p2
        demande = commande.expected_length or 256
        if decalage > len(donnees):
            return sw(0x6B00)
        if decalage + demande > len(donnees):
            if self.longueur_obscure:
                return sw(0x6700)
            return sw(0x6C00 | (len(donnees) - decalage))
        return ok(donnees[decalage : decalage + demande])

    def _fichiers_courants(self) -> dict[int, bytes]:
        if self._df == "G2":
            return self.g2 or {}
        return self.g1 if self._df == "G1" else self.mf

    def lecteur(self) -> MockCardReader:
        return MockCardReader(atr="3B FE 96 00", response_factory=self.repondre)


def decouper(payload: bytes) -> list[tuple[int, int, bytes]]:
    """Decoupe un fichier de telechargement en objets (FID, suffixe, valeur)."""
    objets: list[tuple[int, int, bytes]] = []
    position = 0
    while position < len(payload):
        fid = int.from_bytes(payload[position : position + 2], "big")
        suffixe = payload[position + 2]
        longueur = int.from_bytes(payload[position + 3 : position + 5], "big")
        objets.append((fid, suffixe, payload[position + 5 : position + 5 + longueur]))
        position += 5 + longueur
    assert position == len(payload)
    return objets
