"""Construction et interpretation des commandes APDU (ISO/IEC 7816-4).

Perimetre volontairement limite : ce module ne contient que la **forme** des
commandes et la signification des mots d'etat, telles que definies par la norme
ISO/IEC 7816-4 et, pour les deux commandes de securite utilisees lors d'un
telechargement, par le reglement d'execution (UE) 2016/799, annexe I C, appendice 2
(TCS_124 et TCS_130). Il ne contient aucun identifiant de fichier ni aucune
sequence : ceux-ci sont dans :mod:`app.card_reader.tachograph_card`, avec leur source.

Cette separation est le garde-fou demande en section 15 du cahier des charges : une
carte tachygraphique ne doit pas etre supposee se comporter comme une carte a puce
quelconque.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from app.core.exceptions import CardCommunicationError

__all__ = [
    "APDUCommand",
    "APDUResponse",
    "StatusWord",
    "select_application",
    "select_file_by_identifier",
    "read_binary",
    "get_response",
    "perform_hash_of_file",
    "compute_digital_signature",
]


class StatusWord(IntEnum):
    """Mots d'etat ISO/IEC 7816-4 utilises par l'application.

    Seuls les mots d'etat generiques et sans ambiguite de la norme sont declares.
    Les mots d'etat propres a la carte tachygraphique devront etre ajoutes apres
    lecture de l'annexe I C, appendice 2.
    """

    SUCCESS = 0x9000
    WRONG_LENGTH = 0x6700
    SECURITY_STATUS_NOT_SATISFIED = 0x6982
    AUTHENTICATION_METHOD_BLOCKED = 0x6983
    CONDITIONS_OF_USE_NOT_SATISFIED = 0x6985
    INCORRECT_PARAMETERS = 0x6A80
    FILE_NOT_FOUND = 0x6A82
    RECORD_NOT_FOUND = 0x6A83
    WRONG_PARAMETERS = 0x6B00
    INSTRUCTION_NOT_SUPPORTED = 0x6D00
    CLASS_NOT_SUPPORTED = 0x6E00
    NO_PRECISE_DIAGNOSIS = 0x6F00

    @property
    def label(self) -> str:
        """Libelle francais du mot d'etat, destine aux messages d'erreur."""
        return {
            StatusWord.SUCCESS: "Commande executee",
            StatusWord.WRONG_LENGTH: "Longueur de commande incorrecte",
            StatusWord.SECURITY_STATUS_NOT_SATISFIED: "Acces non autorise par la carte",
            StatusWord.AUTHENTICATION_METHOD_BLOCKED: "Methode d'authentification bloquee",
            StatusWord.CONDITIONS_OF_USE_NOT_SATISFIED: "Conditions d'utilisation non remplies",
            StatusWord.INCORRECT_PARAMETERS: "Parametres de commande incorrects",
            StatusWord.FILE_NOT_FOUND: "Fichier introuvable sur la carte",
            StatusWord.RECORD_NOT_FOUND: "Enregistrement introuvable",
            StatusWord.WRONG_PARAMETERS: "Parametres incorrects",
            StatusWord.INSTRUCTION_NOT_SUPPORTED: "Commande non prise en charge",
            StatusWord.CLASS_NOT_SUPPORTED: "Classe de commande non prise en charge",
            StatusWord.NO_PRECISE_DIAGNOSIS: "Erreur non precisee par la carte",
        }[self]


@dataclass(frozen=True, slots=True)
class APDUCommand:
    """Commande APDU au format court (ISO/IEC 7816-4).

    Attributes:
        cla: Classe de la commande.
        ins: Code d'instruction.
        p1: Premier parametre.
        p2: Second parametre.
        data: Donnees envoyees (champ ``Lc``), vides par defaut.
        expected_length: Longueur de reponse attendue (champ ``Le``), ``None`` si absent.
    """

    cla: int
    ins: int
    p1: int = 0x00
    p2: int = 0x00
    data: bytes = b""
    expected_length: int | None = None

    def __post_init__(self) -> None:
        """Verifie les bornes des champs de la commande."""
        for name, value in (("cla", self.cla), ("ins", self.ins), ("p1", self.p1), ("p2", self.p2)):
            if not 0x00 <= value <= 0xFF:
                raise ValueError(f"{name} doit tenir sur un octet (recu {value})")
        if len(self.data) > 255:
            raise ValueError("APDU court : le champ de donnees est limite a 255 octets")
        if self.expected_length is not None and not 0 <= self.expected_length <= 256:
            raise ValueError("expected_length doit etre compris entre 0 et 256")

    def to_bytes(self) -> bytes:
        """Serialise la commande.

        Returns:
            La suite d'octets a transmettre au lecteur.
        """
        payload = bytearray([self.cla, self.ins, self.p1, self.p2])
        if self.data:
            payload.append(len(self.data))
            payload.extend(self.data)
        if self.expected_length is not None:
            payload.append(0x00 if self.expected_length == 256 else self.expected_length)
        return bytes(payload)

    def to_list(self) -> list[int]:
        """Serialise la commande sous la forme attendue par pyscard."""
        return list(self.to_bytes())

    def describe(self) -> str:
        """Retourne une description hexadecimale, utilisable dans les journaux.

        Le champ de donnees n'est pas journalise : il peut contenir des elements
        d'authentification.
        """
        suffix = f" Lc={len(self.data)}" if self.data else ""
        expected = f" Le={self.expected_length}" if self.expected_length is not None else ""
        entete = f"CLA={self.cla:02X} INS={self.ins:02X}"
        parametres = f"P1={self.p1:02X} P2={self.p2:02X}"
        return f"{entete} {parametres}{suffix}{expected}"


@dataclass(frozen=True, slots=True)
class APDUResponse:
    """Reponse APDU : donnees suivies du mot d'etat.

    Attributes:
        data: Donnees retournees par la carte.
        sw1: Premier octet du mot d'etat.
        sw2: Second octet du mot d'etat.
    """

    data: bytes
    sw1: int
    sw2: int

    @classmethod
    def from_pyscard(cls, data: list[int], sw1: int, sw2: int) -> APDUResponse:
        """Construit une reponse depuis le triplet retourne par pyscard."""
        return cls(data=bytes(data), sw1=sw1, sw2=sw2)

    @property
    def status_word(self) -> int:
        """Mot d'etat complet, sur 16 bits."""
        return (self.sw1 << 8) | self.sw2

    @property
    def is_success(self) -> bool:
        """Indique que la carte a accepte la commande (``9000``)."""
        return self.status_word == StatusWord.SUCCESS

    @property
    def has_more_data(self) -> bool:
        """Indique que la carte propose des donnees supplementaires (``61xx``)."""
        return self.sw1 == 0x61

    @property
    def available_length(self) -> int | None:
        """Nombre d'octets encore disponibles, si la carte l'a indique (``61xx``)."""
        return self.sw2 if self.has_more_data else None

    @property
    def status_label(self) -> str:
        """Libelle du mot d'etat, ou sa valeur hexadecimale si elle est inconnue."""
        try:
            return StatusWord(self.status_word).label
        except ValueError:
            if self.has_more_data:
                return f"Donnees supplementaires disponibles ({self.sw2} octets)"
            return f"Mot d'etat inconnu {self.status_word:04X}"

    def raise_for_status(self, *, context: str) -> APDUResponse:
        """Verifie le mot d'etat et retourne la reponse.

        Args:
            context: Description de l'operation, pour le message d'erreur.

        Returns:
            La reponse elle-meme, pour permettre l'enchainement.

        Raises:
            CardCommunicationError: La carte a refuse la commande.
        """
        if self.is_success or self.has_more_data:
            return self
        raise CardCommunicationError(
            f"La carte a refuse l'operation : {context}.",
            cause=self.status_label,
            action=(
                "Retirez puis reinserez la carte sans la deplacer pendant la lecture. "
                "Si le probleme persiste, la carte n'est peut-etre pas prise en charge."
            ),
            technical_detail=f"SW={self.status_word:04X} ({context})",
        )


# --------------------------------------------------------------------------- #
# Commandes generiques ISO/IEC 7816-4
# --------------------------------------------------------------------------- #
CLA_ISO = 0x00
CLA_PROPRIETARY = 0x80
INS_SELECT = 0xA4
INS_READ_BINARY = 0xB0
INS_GET_RESPONSE = 0xC0
INS_PERFORM_SECURITY_OPERATION = 0x2A


def select_application(application_identifier: bytes) -> APDUCommand:
    """Construit une commande SELECT par nom d'application (AID).

    Source : reglement (UE) 2016/799, annexe I C, appendice 2, TCS_37
    (``00 A4 04 0C`` suivi de l'AID, sans reponse attendue).

    Args:
        application_identifier: Identifiant d'application (1 a 16 octets).

    Returns:
        La commande correspondante.

    Raises:
        ValueError: L'identifiant est vide ou trop long.
    """
    if not 1 <= len(application_identifier) <= 16:
        raise ValueError("un identifiant d'application fait de 1 a 16 octets")
    return APDUCommand(cla=CLA_ISO, ins=INS_SELECT, p1=0x04, p2=0x0C, data=application_identifier)


def perform_hash_of_file() -> APDUCommand:
    """Construit la commande PERFORM HASH OF FILE.

    Calcule, dans la carte, l'empreinte du fichier elementaire courant ; elle est
    conservee par la carte pour la commande :func:`compute_digital_signature`.

    Source : reglement (UE) 2016/799, annexe I C, appendice 2, TCS_124
    (``80 2A 90 00``, commande proprietaire sans donnees).
    """
    return APDUCommand(cla=CLA_PROPRIETARY, ins=INS_PERFORM_SECURITY_OPERATION, p1=0x90, p2=0x00)


def compute_digital_signature(expected_length: int) -> APDUCommand:
    """Construit la commande PSO: COMPUTE DIGITAL SIGNATURE.

    La carte signe l'empreinte calculee par :func:`perform_hash_of_file` avec sa
    cle privee, qu'elle ne divulgue jamais.

    Source : reglement (UE) 2016/799, annexe I C, appendice 2, TCS_130
    (``00 2A 9E 9A`` suivi de ``Le``).

    Args:
        expected_length: Longueur exacte de la signature attendue (1 a 256). Une
            carte tachygraphique repond ``6700`` si elle ne correspond pas.
    """
    if not 1 <= expected_length <= 256:
        raise ValueError("expected_length doit etre compris entre 1 et 256")
    return APDUCommand(
        cla=CLA_ISO,
        ins=INS_PERFORM_SECURITY_OPERATION,
        p1=0x9E,
        p2=0x9A,
        expected_length=expected_length,
    )


def select_file_by_identifier(file_identifier: bytes) -> APDUCommand:
    """Construit une commande SELECT d'un fichier elementaire du DF courant.

    Source : reglement (UE) 2016/799, annexe I C, appendice 2, TCS_39
    (``00 A4 02 0C`` suivi de l'identifiant, sans reponse attendue). Le fichier est
    cherche sous le repertoire (DF) courant : le meme identifiant designe donc un
    fichier different selon l'application tachygraphique selectionnee.

    Args:
        file_identifier: Identifiant de fichier sur 2 octets.

    Returns:
        La commande correspondante.

    Raises:
        ValueError: L'identifiant ne fait pas exactement 2 octets.
    """
    if len(file_identifier) != 2:
        raise ValueError("un identifiant de fichier ISO 7816 fait 2 octets")
    return APDUCommand(cla=CLA_ISO, ins=INS_SELECT, p1=0x02, p2=0x0C, data=file_identifier)


def read_binary(*, offset: int, length: int) -> APDUCommand:
    """Construit une commande READ BINARY.

    Args:
        offset: Decalage de lecture dans le fichier courant (0 a 32767).
        length: Nombre d'octets demandes (1 a 256).

    Returns:
        La commande correspondante.

    Raises:
        ValueError: Les bornes ne sont pas respectees.
    """
    if not 0 <= offset <= 0x7FFF:
        raise ValueError("offset doit etre compris entre 0 et 32767")
    if not 1 <= length <= 256:
        raise ValueError("length doit etre compris entre 1 et 256")
    return APDUCommand(
        cla=CLA_ISO,
        ins=INS_READ_BINARY,
        p1=(offset >> 8) & 0x7F,
        p2=offset & 0xFF,
        expected_length=length,
    )


def get_response(length: int) -> APDUCommand:
    """Construit une commande GET RESPONSE.

    Args:
        length: Nombre d'octets a recuperer (1 a 256).

    Returns:
        La commande correspondante.

    Raises:
        ValueError: ``length`` est hors bornes.
    """
    if not 1 <= length <= 256:
        raise ValueError("length doit etre compris entre 1 et 256")
    return APDUCommand(cla=CLA_ISO, ins=INS_GET_RESPONSE, expected_length=length)
