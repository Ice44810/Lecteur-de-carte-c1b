"""Construction de fichiers C1B synthetiques pour les tests.

Les fichiers sont codes selon le reglement d'execution (UE) 2016/799, annexe I C
(appendice 1 pour les types, appendice 7 pour le conteneur), avec des donnees
**fictives** : aucun telechargement reel, porteur de donnees personnelles, n'est
verse dans le depot. Le decodeur a par ailleurs ete valide sur un fichier reel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

ACTIVITES = {"REPOS": 0b00, "DISPO": 0b01, "TRAVAIL": 0b10, "CONDUITE": 0b11}


def tlv(fid: int, suffixe: int, valeur: bytes) -> bytes:
    """Objet TLV du conteneur (DDP_041 a DDP_046)."""
    return fid.to_bytes(2, "big") + bytes([suffixe]) + len(valeur).to_bytes(2, "big") + valeur


def time_real(moment: datetime | None) -> bytes:
    """TimeReal (2.162)."""
    return (int(moment.timestamp()) if moment else 0).to_bytes(4, "big")


def datef(jour: date | None) -> bytes:
    """Datef (2.57), BCD."""
    return bytes.fromhex(jour.strftime("%Y%m%d")) if jour else b"\x00" * 4


def name(texte: str, *, code_page: int = 1, encodage: str = "latin-1") -> bytes:
    """Name (2.99) : code page puis 35 octets."""
    return bytes([code_page]) + texte.encode(encodage).ljust(35, b" ")


def immatriculation(numero: str, pays: int = 0x11) -> bytes:
    """VehicleRegistrationIdentification (2.166) : pays, code page, 13 octets."""
    return bytes([pays, 1]) + numero.encode("ascii").ljust(13, b" ")


def mot_activite(
    minute: int,
    activite: str,
    *,
    retiree: bool = False,
    connue: bool = False,
    equipage: bool = False,
) -> int:
    """ActivityChangeInfo (2.1) : ``scpaattttttttttt``."""
    c = connue if retiree else equipage
    return (int(c) << 14) | (int(retiree) << 13) | (ACTIVITES[activite] << 11) | minute


@dataclass
class CarteSynthetique:
    """Contenu d'une carte conducteur fictive."""

    numero: str = "F1234567890123" + "01"
    nom: str = "DUPONT"
    prenom: str = "MARIE"
    naissance: date | None = date(1985, 3, 14)
    delivrance: datetime = datetime(2022, 1, 10, tzinfo=UTC)
    validite: datetime = datetime(2022, 2, 1, tzinfo=UTC)
    expiration: datetime = datetime(2027, 1, 31, 23, 59, 59, tzinfo=UTC)
    jours: list[tuple[date, list[int]]] = field(default_factory=list)
    vehicules: list[tuple[datetime, datetime, str, int, int]] = field(default_factory=list)
    lieux: list[tuple[datetime, int, int, int]] = field(default_factory=list)
    evenements: list[tuple[int, datetime, datetime, str]] = field(default_factory=list)
    conditions: list[tuple[datetime, int]] = field(default_factory=list)
    taille_activites: int = 2000
    debut_activites: int = 0
    avec_g2: bool = True

    def identification(self) -> bytes:
        """CardIdentification (2.24) + DriverCardHolderIdentification (2.62)."""
        carte = (
            bytes([0x11])
            + self.numero.encode("ascii").ljust(16)
            + name("AUTORITE DE TEST")
            + time_real(self.delivrance)
            + time_real(self.validite)
            + time_real(self.expiration)
        )
        titulaire = name(self.nom) + name(self.prenom) + datef(self.naissance) + b"fr"
        return carte + titulaire

    def permis(self) -> bytes:
        """CardDrivingLicenceInformation (2.18)."""
        return name("PREFECTURE DE TEST") + bytes([0x11]) + b"PERMIS0001".ljust(16)

    def activites(self) -> bytes:
        """CardDriverActivity (2.17), memoire circulaire."""
        tampon = bytearray(self.taille_activites)
        position = self.debut_activites
        precedente = 0
        derniere = position
        for jour, mots in self.jours:
            corps = b"".join(mot.to_bytes(2, "big") for mot in mots)
            longueur = 12 + len(corps)
            instant = datetime(jour.year, jour.month, jour.day, tzinfo=UTC)
            enregistrement = (
                precedente.to_bytes(2, "big")
                + longueur.to_bytes(2, "big")
                + time_real(instant)
                + bytes.fromhex("0001")
                + (100).to_bytes(2, "big")
                + corps
            )
            for index, octet in enumerate(enregistrement):
                tampon[(position + index) % len(tampon)] = octet
            derniere = position
            precedente = longueur
            position = (position + longueur) % len(tampon)
        return self.debut_activites.to_bytes(2, "big") + derniere.to_bytes(2, "big") + bytes(tampon)

    def vehicules_utilises(self) -> bytes:
        """CardVehiclesUsed (2.38) : pointeur puis enregistrements de 31 octets."""
        enregistrements = b"".join(
            debut_km.to_bytes(3, "big")
            + fin_km.to_bytes(3, "big")
            + time_real(debut)
            + time_real(fin)
            + immatriculation(numero)
            + b"\x00\x01"
            for debut, fin, numero, debut_km, fin_km in self.vehicules
        )
        vides = b"\x00" * 31 * 3
        return (max(len(self.vehicules) - 1, 0)).to_bytes(2, "big") + enregistrements + vides

    def places(self) -> bytes:
        """CardPlaceDailyWorkPeriod (2.27) : pointeur puis enregistrements de 10 octets."""
        enregistrements = b"".join(
            time_real(instant) + bytes([type_saisie, pays, 0]) + km.to_bytes(3, "big")
            for instant, type_saisie, pays, km in self.lieux
        )
        return bytes([max(len(self.lieux) - 1, 0)]) + enregistrements + b"\x00" * 20

    def evenements_cartes(self) -> bytes:
        """CardEventData (2.19) : 6 types de 2 enregistrements de 24 octets."""
        enregistrements = [
            bytes([code]) + time_real(debut) + time_real(fin) + immatriculation(numero)
            for code, debut, fin, numero in self.evenements
        ]
        contenu = b"".join(enregistrements)
        return contenu + b"\x00" * (6 * 2 * 24 - len(contenu))

    def conditions_particulieres(self) -> bytes:
        """SpecificConditionRecord (2.152)."""
        contenu = b"".join(time_real(instant) + bytes([code]) for instant, code in self.conditions)
        return contenu + b"\x00" * 10

    def fichier(self, *, signature: bytes = b"\xaa" * 128) -> bytes:
        """Fichier de telechargement complet (conteneur TLV)."""
        donnees = [
            (0x0501, b"\x01" + b"\x00" * 9),
            (0x0520, self.identification()),
            (0x0521, self.permis()),
            (0x0502, self.evenements_cartes()),
            (0x0503, b"\x00" * 2 * 24 * 24),
            (0x0504, self.activites()),
            (0x0505, self.vehicules_utilises()),
            (0x0506, self.places()),
            (0x0522, self.conditions_particulieres()),
        ]
        contenu = tlv(0x0002, 0, b"\x00" * 25) + tlv(0xC100, 0, b"\x00" * 194)
        for fid, valeur in donnees:
            contenu += tlv(fid, 0, valeur) + tlv(fid, 1, signature)
        if self.avec_g2:
            contenu += tlv(0x0501, 2, b"\x01" + b"\x00" * 16) + tlv(0x0501, 3, signature[:64])
        return contenu
