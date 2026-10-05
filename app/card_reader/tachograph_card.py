"""Telechargement d'une carte conducteur tachygraphique.

Ce module est le seul endroit ou la connaissance specifique de la carte
tachygraphique apparait : identifiants d'application, identifiants de fichiers
elementaires, ordre de lecture et assemblage du fichier de telechargement. Chaque
valeur cite sa source dans le reglement d'execution (UE) 2016/799, annexe I C
(version consolidee) :

* appendice 2, TCS_142 / TCS_148 / TCS_152 : structure de fichiers de la carte ;
* appendice 2, TCS_37, TCS_39, TCS_42-43, TCS_124, TCS_130 : commandes ;
* appendice 7, DDP_035 a DDP_046 : procedure et format du telechargement ;
* appendice 1, types ``DriverCardApplicationIdentification`` et ``EquipmentType``.

Le telechargement est **en lecture seule** : aucune commande d'ecriture n'est
transmise. En particulier, la date ``LastCardDownload`` du fichier ``Card_Download``
n'est pas mise a jour (DDP_035), afin de ne jamais modifier la carte tant que la
sequence n'a pas ete validee sur cartes reelles (statut ``IN_REVIEW`` des points
``card`` de :mod:`app.parser.specification`).

Chaine :

.. code-block:: text

    PCSCReader -> TachographCard.download() -> CardDownload (octets .C1B)
               -> ImportService (archivage, journal) -> analyse
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.card_reader.apdu import (
    APDUCommand,
    APDUResponse,
    StatusWord,
    compute_digital_signature,
    get_response,
    perform_hash_of_file,
    read_binary,
    select_application,
    select_file_by_identifier,
)
from app.card_reader.interface import CardPresence, CardReaderInterface
from app.config.logging_config import get_logger
from app.core.exceptions import CardCommunicationError, UnconfirmedStructureError
from app.parser.specification import is_referenced, questions_for

__all__ = [
    "AID_TACHOGRAPH_G1",
    "AID_TACHOGRAPH_G2",
    "CardDownload",
    "CardFile",
    "TachographCard",
]

logger = get_logger(__name__)

AID_TACHOGRAPH_G1 = bytes.fromhex("FF544143484F")
"""Application tachygraphique de 1re generation (appendice 2, TCS_37 et TCS_145)."""

AID_TACHOGRAPH_G2 = bytes.fromhex("FF534D524454")
"""Application tachygraphique de 2e generation (appendice 2, TCS_37 et TCS_145)."""

EQUIPMENT_TYPE_DRIVER_CARD = 1
"""Valeur de ``typeOfTachographCardId`` d'une carte conducteur (appendice 1, EquipmentType)."""

SIGNATURE_LENGTHS_G1: tuple[int, ...] = (128,)
"""Longueur d'une signature RSA de 1re generation : module de 1 024 bits (appendice 11,
CSM_014 ; appendice 2, TCS_131)."""

SIGNATURE_LENGTHS_G2: tuple[int, ...] = (64, 96, 128, 132)
"""Longueurs possibles d'une signature ECDSA de 2e generation au format « plain »
(r || s, appendice 11, CSM_150) pour les tailles de cle 256, 384, 512 et 521 bits
(appendice 11, CSM_45 et table 1)."""

READ_CHUNK = 0xFF
"""Nombre d'octets demandes par READ BINARY (``Le`` sur un octet, TCS_42)."""

MAX_SHORT_OFFSET = 0x7FFF
"""Decalage maximal d'un READ BINARY avec decalage dans P1-P2 (bit 8 de P1 a 0, TCS_42)."""

TAG_DATA_G1 = 0x00
TAG_SIGNATURE_G1 = 0x01
TAG_DATA_G2 = 0x02
TAG_SIGNATURE_G2 = 0x03
"""Suffixes d'etiquette du format de telechargement (appendice 7, DDP_042, DDP_043, DDP_046)."""


@dataclass(frozen=True, slots=True)
class CardFile:
    """Fichier elementaire de la carte a telecharger.

    Attributes:
        name: Nom du fichier dans la specification.
        fid: Identifiant de fichier (2 octets).
        signed: Le fichier est telecharge avec sa signature (DDP_038).
        mandatory: Son absence interrompt le telechargement (DDP_035).
    """

    name: str
    fid: int
    signed: bool = True
    mandatory: bool = True

    @property
    def identifier(self) -> bytes:
        """Identifiant sur deux octets, tel que transmis a la carte."""
        return self.fid.to_bytes(2, "big")


MF_FILES: tuple[CardFile, ...] = (
    CardFile("ICC", 0x0002, signed=False, mandatory=False),
    CardFile("IC", 0x0005, signed=False, mandatory=False),
)
"""Informations communes du MF, facultatives et non signees (TCS_142, DDP_035)."""

G1_FILES: tuple[CardFile, ...] = (
    CardFile("Card_Certificate", 0xC100, signed=False),
    CardFile("CA_Certificate", 0xC108, signed=False),
    CardFile("Application_Identification", 0x0501),
    CardFile("Identification", 0x0520),
    CardFile("Driving_Licence_Info", 0x0521, mandatory=False),
    CardFile("Events_Data", 0x0502),
    CardFile("Faults_Data", 0x0503),
    CardFile("Driver_Activity_Data", 0x0504),
    CardFile("Vehicles_Used", 0x0505),
    CardFile("Places", 0x0506),
    CardFile("Current_Usage", 0x0507, mandatory=False),
    CardFile("Control_Activity_Data", 0x0508),
    CardFile("Specific_Conditions", 0x0522),
)
"""Fichiers du DF Tachograph d'une carte conducteur (TCS_148, DDP_035).

``Card_Download`` (``050E``) est volontairement absent : DDP_035 l'exclut du
telechargement.
"""

G2_FILES: tuple[CardFile, ...] = (
    CardFile("CardSignCertificate", 0xC101, signed=False),
    CardFile("CA_Certificate", 0xC108, signed=False),
    CardFile("Link_Certificate", 0xC109, signed=False, mandatory=False),
    CardFile("Application_Identification", 0x0501),
    CardFile("Application_Identification_V2", 0x0525, mandatory=False),
    CardFile("Identification", 0x0520),
    CardFile("Driving_Licence_Info", 0x0521, mandatory=False),
    CardFile("Events_Data", 0x0502),
    CardFile("Faults_Data", 0x0503),
    CardFile("Driver_Activity_Data", 0x0504),
    CardFile("Vehicles_Used", 0x0505),
    CardFile("Places", 0x0506),
    CardFile("Current_Usage", 0x0507, mandatory=False),
    CardFile("Control_Activity_Data", 0x0508),
    CardFile("Specific_Conditions", 0x0522),
    CardFile("VehicleUnits_Used", 0x0523),
    CardFile("GNSS_Places", 0x0524),
    CardFile("Places_Authentication", 0x0526, mandatory=False),
    CardFile("GNSS_Places_Authentication", 0x0527, mandatory=False),
    CardFile("Border_Crossings", 0x0528, mandatory=False),
    CardFile("Load_Unload_Operations", 0x0529, mandatory=False),
    CardFile("Load_Type_Entries", 0x0530, mandatory=False),
    CardFile("VU_Configuration", 0x0540, mandatory=False),
)
"""Fichiers du DF Tachograph_G2 d'une carte conducteur (TCS_152, DDP_035).

``CardMA_Certificate`` (``C100``) n'est pas telecharge (DDP_037 ne retient que
``CardSignCertificate``), ni ``Card_Download`` (``050E``, exclu par DDP_035). Les
fichiers propres a la version 2 des cartes sont facultatifs : ils ne sont presents
que sur ces cartes.
"""


@dataclass(frozen=True, slots=True)
class CardDownload:
    """Resultat d'un telechargement de carte.

    Attributes:
        payload: Fichier de telechargement assemble (format DDP_041 a DDP_046),
            stocke tel quel dans un fichier ``.C1B``.
        atr: ATR de la carte, pour tracabilite.
        reader_name: Lecteur utilise.
        files: Noms des fichiers lus, prefixes de la generation (``G1:`` ou ``G2:``).
        skipped: Fichiers facultatifs absents de la carte.
    """

    payload: bytes
    atr: str | None = None
    reader_name: str | None = None
    files: tuple[str, ...] = ()
    skipped: tuple[str, ...] = field(default_factory=tuple)

    @property
    def size(self) -> int:
        """Taille des donnees telechargees, en octets."""
        return len(self.payload)

    @property
    def has_generation_2(self) -> bool:
        """Indique que l'application de 2e generation a ete telechargee."""
        return any(name.startswith("G2:") for name in self.files)


class _FileAbsentError(Exception):
    """Le fichier demande n'existe pas sur la carte (``6A82``)."""


def _unconfirmed(code: str) -> UnconfirmedStructureError:
    """Construit l'erreur d'incertitude associee a une question du domaine ``card``."""
    question = next((item for item in questions_for("card") if item.code == code), None)
    reference = question.reference if question else "specification non identifiee"
    detail = question.question if question else code
    return UnconfirmedStructureError(
        "La lecture directe de la carte n'est pas encore disponible.",
        cause=(
            "La sequence de commandes propre aux cartes tachygraphiques n'a pas encore "
            "ete confirmee a partir d'une specification officielle."
        ),
        action=(
            "Utilisez pour l'instant l'import d'un fichier C1B produit par un outil de "
            "telechargement existant."
        ),
        technical_detail=f"{code} - a confirmer via : {reference} ({detail})",
    )


class TachographCard:
    """Carte tachygraphique accessible via un lecteur.

    Args:
        reader: Lecteur deja connecte, ou a connecter.
    """

    def __init__(self, reader: CardReaderInterface) -> None:
        self._reader = reader
        self._signature_lengths: dict[int, int] = {}

    @property
    def reader(self) -> CardReaderInterface:
        """Lecteur utilise."""
        return self._reader

    def presence(self) -> CardPresence:
        """Retourne l'etat courant du lecteur et de la carte."""
        return self._reader.poll()

    def transmit(self, command: APDUCommand) -> APDUResponse:
        """Transmet une commande APDU brute a la carte.

        Raises:
            CardCommunicationError: Aucune connexion active ou echange interrompu.
        """
        if not self._reader.is_connected:
            raise CardCommunicationError(
                "Aucune carte connectee.",
                cause="La connexion avec la carte n'a pas ete etablie.",
                action="Connectez la carte avant d'envoyer une commande.",
            )
        return self._reader.transmit(command)

    # ------------------------------------------------------------------ #
    # Operations elementaires
    # ------------------------------------------------------------------ #
    def select_application(self, application_identifier: bytes = AID_TACHOGRAPH_G1) -> bool:
        """Selectionne une application tachygraphique (TCS_37).

        Args:
            application_identifier: AID de l'application.

        Returns:
            ``False`` si la carte ne contient pas cette application (``6A82``).

        Raises:
            CardCommunicationError: La carte a refuse la selection pour une autre raison.
        """
        self._require_referenced("CARD_APPLICATION_SELECTION")
        response = self._exchange(select_application(application_identifier))
        if response.status_word == StatusWord.FILE_NOT_FOUND:
            return False
        response.raise_for_status(context="selection de l'application tachygraphique")
        return True

    def read_elementary_file(self, file_identifier: bytes) -> bytes:
        """Selectionne puis lit integralement un fichier du DF courant.

        Args:
            file_identifier: Identifiant du fichier, sur 2 octets.

        Returns:
            Le contenu du fichier.

        Raises:
            CardCommunicationError: Fichier absent ou lecture refusee.
        """
        self._require_referenced("CARD_READ_BINARY_SEQUENCE")
        try:
            self._select_file(file_identifier)
        except _FileAbsentError as exc:
            raise CardCommunicationError(
                "Un fichier attendu est absent de la carte.",
                cause=f"Le fichier {file_identifier.hex().upper()} n'existe pas sur la carte.",
                action="Verifiez qu'il s'agit bien d'une carte conducteur.",
            ) from exc
        return self._read_current_file(file_identifier)

    # ------------------------------------------------------------------ #
    # Telechargement
    # ------------------------------------------------------------------ #
    def download(self) -> CardDownload:
        """Telecharge une carte conducteur et assemble le fichier ``.C1B``.

        Sequence (appendice 7, DDP_035 a DDP_038) : informations communes du MF,
        puis application de 1re generation, puis, si la carte la contient,
        application de 2e generation. Les fichiers d'application sont lus avec leur
        signature calculee par la carte.

        Returns:
            Le telechargement assemble.

        Raises:
            UnconfirmedStructureError: La sequence n'est pas referencee.
            NoCardPresentError: Aucune carte n'est inseree.
            CardCommunicationError: La carte n'est pas une carte conducteur, un
                fichier obligatoire manque, ou l'echange a ete interrompu.
        """
        self._require_referenced("CARD_FILE_IDENTIFIERS")
        self._require_referenced("CARD_DOWNLOAD_FILE_ASSEMBLY")

        presence = self._reader.connect() if not self._reader.is_connected else None
        payload = bytearray()
        files: list[str] = []
        skipped: list[str] = []

        # Informations communes (MF) : lues avant toute selection d'application,
        # tant que le MF est le repertoire courant.
        for card_file in MF_FILES:
            self._download_file(card_file, "MF", TAG_DATA_G1, payload, files, skipped)

        if not self.select_application(AID_TACHOGRAPH_G1):
            raise CardCommunicationError(
                "Cette carte n'est pas une carte tachygraphique lisible.",
                cause="L'application tachygraphique est absente de la carte.",
                action="Inserez une carte conducteur.",
                technical_detail="SELECT AID FF544143484F : 6A82",
            )
        self._ensure_driver_card()
        for card_file in G1_FILES:
            self._download_file(card_file, "G1", TAG_DATA_G1, payload, files, skipped)

        if self.select_application(AID_TACHOGRAPH_G2):
            for card_file in G2_FILES:
                self._download_file(card_file, "G2", TAG_DATA_G2, payload, files, skipped)
        else:
            logger.info("Carte de 1re generation : aucune application Tachograph_G2")

        download = CardDownload(
            payload=bytes(payload),
            atr=presence.atr if presence is not None else None,
            reader_name=(
                presence.reader.name
                if presence is not None and presence.reader is not None
                else None
            ),
            files=tuple(files),
            skipped=tuple(skipped),
        )
        logger.info(
            "Carte telechargee : %d octets, %d fichier(s), %d facultatif(s) absent(s)",
            download.size,
            len(files),
            len(skipped),
        )
        return download

    # ------------------------------------------------------------------ #
    # Interne
    # ------------------------------------------------------------------ #
    def _download_file(
        self,
        card_file: CardFile,
        scope: str,
        data_tag: int,
        payload: bytearray,
        files: list[str],
        skipped: list[str],
    ) -> None:
        """Lit un fichier (et sa signature) et l'ajoute au telechargement.

        Raises:
            CardCommunicationError: Fichier obligatoire absent ou lecture refusee.
        """
        label = f"{scope}:{card_file.name}"
        try:
            self._select_file(card_file.identifier)
        except CardCommunicationError:
            if card_file.mandatory:
                raise
            # Fichier facultatif dont la selection est refusee (droits d'acces,
            # repertoire courant different) : il n'est simplement pas telecharge.
            skipped.append(label)
            return
        except _FileAbsentError:
            if card_file.mandatory:
                raise CardCommunicationError(
                    "Un fichier obligatoire est absent de la carte.",
                    cause=f"Le fichier {card_file.name} ({scope}) n'a pas ete trouve.",
                    action=(
                        "Verifiez qu'il s'agit bien d'une carte conducteur. Si c'est le "
                        "cas, la carte est peut-etre endommagee."
                    ),
                    technical_detail=f"SELECT {card_file.fid:04X} : 6A82",
                ) from None
            skipped.append(label)
            return

        if card_file.signed:
            self._exchange(perform_hash_of_file()).raise_for_status(
                context=f"calcul de l'empreinte de {card_file.name}"
            )
        data = self._read_current_file(card_file.identifier)
        payload += self._tlv(card_file.fid, data_tag, data)

        if card_file.signed:
            signature = self._sign_current_file(card_file, data_tag)
            payload += self._tlv(card_file.fid, data_tag + 1, signature)
        files.append(label)

    def _sign_current_file(self, card_file: CardFile, data_tag: int) -> bytes:
        """Obtient la signature de l'empreinte du fichier courant (TCS_130).

        La carte attend la longueur exacte de la signature dans ``Le`` et repond
        ``6700`` sinon. En 1re generation, elle est fixe (128 octets). En 2e
        generation, elle depend de la courbe de la carte : les longueurs prevues sont
        essayees, en recalculant l'empreinte avant chaque nouvel essai, puis la
        longueur acceptee est conservee pour les fichiers suivants.

        Raises:
            CardCommunicationError: La carte a refuse toutes les longueurs prevues.
        """
        candidates = SIGNATURE_LENGTHS_G1 if data_tag == TAG_DATA_G1 else SIGNATURE_LENGTHS_G2
        known = self._signature_lengths.get(data_tag)
        if known is not None:
            candidates = (known, *(length for length in candidates if length != known))

        response: APDUResponse | None = None
        for attempt, length in enumerate(candidates):
            if attempt:
                self._exchange(perform_hash_of_file()).raise_for_status(
                    context=f"calcul de l'empreinte de {card_file.name}"
                )
            response = self._exchange(compute_digital_signature(length))
            if response.is_success:
                self._signature_lengths[data_tag] = len(response.data)
                return response.data
            if response.status_word != StatusWord.WRONG_LENGTH:
                break
        assert response is not None
        response.raise_for_status(context=f"signature de {card_file.name}")
        return response.data  # pragma: no cover - raise_for_status leve toujours ici

    def _ensure_driver_card(self) -> None:
        """Verifie qu'il s'agit d'une carte conducteur (``typeOfTachographCardId``).

        Raises:
            CardCommunicationError: La carte est d'un autre type (atelier, entreprise...).
        """
        try:
            self._select_file(b"\x05\x01")
        except _FileAbsentError:
            raise CardCommunicationError(
                "Seules les cartes conducteur peuvent etre telechargees.",
                cause="La carte ne contient pas de fichier Application_Identification.",
                action="Inserez une carte conducteur.",
                technical_detail="SELECT 0501 : 6A82",
            ) from None
        identification = self._read_current_file(b"\x05\x01")
        if not identification or identification[0] != EQUIPMENT_TYPE_DRIVER_CARD:
            card_type = identification[0] if identification else None
            raise CardCommunicationError(
                "Seules les cartes conducteur peuvent etre telechargees.",
                cause="La carte inseree n'est pas une carte conducteur.",
                action="Inserez une carte conducteur.",
                technical_detail=f"typeOfTachographCardId = {card_type}",
            )

    def _select_file(self, file_identifier: bytes) -> None:
        """Selectionne un fichier du DF courant (TCS_39).

        Raises:
            _FileAbsentError: Le fichier n'existe pas (``6A82``).
            CardCommunicationError: La selection a ete refusee pour une autre raison.
        """
        response = self._exchange(select_file_by_identifier(file_identifier))
        if response.status_word == StatusWord.FILE_NOT_FOUND:
            raise _FileAbsentError(file_identifier.hex())
        response.raise_for_status(context=f"selection du fichier {file_identifier.hex().upper()}")

    def _read_current_file(self, file_identifier: bytes) -> bytes:
        """Lit integralement le fichier courant par READ BINARY successifs (TCS_42-43).

        La taille du fichier n'est pas connue a l'avance : la lecture progresse par
        blocs jusqu'a ce que la carte indique la fin du fichier, soit en renvoyant
        moins d'octets que demande, soit par ``6Cxx`` (longueur exacte restante), soit
        par ``6B00`` / ``6700`` (decalage ou longueur au-dela de la fin).

        Raises:
            CardCommunicationError: La lecture a ete refusee, ou le fichier depasse la
                taille lisible avec un decalage sur deux octets.
        """
        content = bytearray()
        length = READ_CHUNK
        while True:
            if len(content) > MAX_SHORT_OFFSET:
                raise CardCommunicationError(
                    "Un fichier de la carte est trop volumineux pour cette version.",
                    cause="Sa taille depasse 32 767 octets.",
                    action="Signalez l'anomalie en indiquant le modele de carte.",
                    technical_detail=f"fichier {file_identifier.hex().upper()}",
                )
            response = self._exchange(read_binary(offset=len(content), length=length))
            status = response.status_word
            if response.is_success or status == 0x6281:
                if status == 0x6281:
                    logger.warning(
                        "Fichier %s : la carte signale une erreur d'integrite (6281)",
                        file_identifier.hex().upper(),
                    )
                content += response.data
                if len(response.data) < length or not response.data:
                    return bytes(content)
                length = READ_CHUNK
                continue
            if response.sw1 == 0x6C:
                if response.sw2 == 0:
                    return bytes(content)
                length = response.sw2
                continue
            if status == StatusWord.WRONG_PARAMETERS:
                return bytes(content)
            if status == StatusWord.WRONG_LENGTH:
                # Fin de fichier sans indication de longueur : on reduit la demande.
                if length == 1:
                    return bytes(content)
                length = max(1, length // 2)
                continue
            response.raise_for_status(context=f"lecture du fichier {file_identifier.hex().upper()}")

    def _exchange(self, command: APDUCommand) -> APDUResponse:
        """Transmet une commande en traitant les reponses ``61xx`` et ``6Cxx``.

        * ``61xx`` : donnees disponibles, recuperees par GET RESPONSE (TCS_31-32) ;
        * ``6Cxx`` sur une commande avec ``Le`` : la commande est rejouee avec la
          longueur exacte indiquee, sauf pour READ BINARY ou ce code signale la fin
          du fichier et est traite par l'appelant.
        """
        response = self.transmit(command)
        if (
            response.sw1 == 0x6C
            and command.expected_length is not None
            and command.ins != 0xB0
            and response.sw2
        ):
            response = self.transmit(
                APDUCommand(
                    cla=command.cla,
                    ins=command.ins,
                    p1=command.p1,
                    p2=command.p2,
                    data=command.data,
                    expected_length=response.sw2,
                )
            )
        data = bytearray(response.data)
        while response.has_more_data:
            response = self.transmit(get_response(response.sw2 or 256))
            data += response.data
        return APDUResponse(data=bytes(data), sw1=response.sw1, sw2=response.sw2)

    @staticmethod
    def _tlv(fid: int, suffix: int, value: bytes) -> bytes:
        """Construit un objet TLV du fichier de telechargement (DDP_041 a DDP_044).

        Raises:
            CardCommunicationError: La valeur depasse la longueur codable.
        """
        if len(value) >= 0xFFFF:
            raise CardCommunicationError(
                "Un fichier de la carte est trop volumineux.",
                cause="Sa longueur ne peut pas etre codee dans le format de telechargement.",
                action="Signalez l'anomalie en indiquant le modele de carte.",
                technical_detail=f"FID {fid:04X}, {len(value)} octets",
            )
        return fid.to_bytes(2, "big") + bytes([suffix]) + len(value).to_bytes(2, "big") + value

    @staticmethod
    def _require_referenced(code: str) -> None:
        """Refuse d'agir tant que le point de specification n'est pas reference.

        Raises:
            UnconfirmedStructureError: Le point est encore a l'etat ``OPEN``.
        """
        question = next((item for item in questions_for("card") if item.code == code), None)
        if question is None or not is_referenced("card", code=code):
            raise _unconfirmed(code)
