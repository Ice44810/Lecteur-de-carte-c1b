"""Parser de fichiers C1B (telechargement de carte conducteur).

Le fichier est une concatenation d'objets TLV (reglement d'execution (UE) 2016/799,
annexe I C, appendice 7, DDP_041 a DDP_046) : etiquette = identifiant du fichier de la
carte (2 octets) suivi d'un suffixe (``00`` donnees de l'application de 1re
generation, ``01`` sa signature, ``02`` / ``03`` idem pour la 2e generation), puis une
longueur sur 2 octets.

Le decodage porte sur les fichiers de l'application de **1re generation**, presente
sur toutes les cartes conducteur (TCS_140) et dont les structures sont definies par
l'appendice 1 du meme reglement :

========================  ======  ==============================================
Fichier                   FID     Type (appendice 1)
========================  ======  ==============================================
Identification            0520    CardIdentification (2.24) +
                                  DriverCardHolderIdentification (2.62)
Driving_Licence_Info      0521    CardDrivingLicenceInformation (2.18)
Events_Data               0502    CardEventData (2.19), CardEventRecord (2.20)
Faults_Data               0503    CardFaultData (2.21), CardFaultRecord (2.22)
Driver_Activity_Data      0504    CardDriverActivity (2.17),
                                  CardActivityDailyRecord (2.9),
                                  ActivityChangeInfo (2.1)
Vehicles_Used             0505    CardVehiclesUsed (2.38), CardVehicleRecord (2.37)
Places                    0506    CardPlaceDailyWorkPeriod (2.27), PlaceRecord (2.117)
Specific_Conditions       0522    SpecificConditionRecord (2.152)
========================  ======  ==============================================

Le decodage a ete valide sur un fichier reel en comparant identite, vehicules,
activites et totaux a ceux d'un logiciel de lecture tiers.

Les signatures ne sont pas verifiees (``C1B_SIGNATURE_VERIFICATION``) : un fichier
altere serait decode sans etre signale comme tel.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta

from app.core.enums import ActivityType, FileType
from app.core.exceptions import ParsingError
from app.core.timeutils import utcnow
from app.parser.base import TachographFileParser
from app.parser.models import (
    DecodedActivityPeriod,
    DecodedDriverIdentification,
    DecodedEvent,
    DecodedPlace,
    DecodedSpecificCondition,
    DecodedTechnicalData,
    DecodedVehicleIdentification,
    DecodedVehicleUse,
    DiagnosticLevel,
    ParseDiagnostic,
)
from app.parser.reference_tables import (
    CODE_PAGES,
    event_fault_label,
    nation_alpha,
    nation_name,
)

__all__ = ["C1BParser", "content_digest", "decode_container"]

FID_IDENTIFICATION = 0x0520
FID_DRIVING_LICENCE = 0x0521
FID_EVENTS = 0x0502
FID_FAULTS = 0x0503
FID_DRIVER_ACTIVITY = 0x0504
FID_VEHICLES_USED = 0x0505
FID_PLACES = 0x0506
FID_SPECIFIC_CONDITIONS = 0x0522

SUFFIX_DATA_G1 = 0x00
SUFFIX_DATA_G2 = 0x02

EVENT_RECORD_SIZE = 24
"""CardEventRecord / CardFaultRecord : 1 + 4 + 4 + 15 octets."""
EVENT_TYPES_PER_FILE = 6
"""CardEventData : SEQUENCE SIZE(6) (2.19)."""
FAULT_TYPES_PER_FILE = 2
"""CardFaultData : SEQUENCE SIZE(2) (2.21)."""
VEHICLE_RECORD_SIZE = 31
"""CardVehicleRecord de 1re generation : 3 + 3 + 4 + 4 + 15 + 2 octets."""
PLACE_RECORD_SIZE = 10
"""PlaceRecord de 1re generation : 4 + 1 + 1 + 1 + 3 octets."""
CONDITION_RECORD_SIZE = 5
"""SpecificConditionRecord : 4 + 1 octets."""
DAILY_RECORD_HEADER = 12
"""En-tete de CardActivityDailyRecord : 2 + 2 + 4 + 2 + 2 octets."""

_ACTIVITY_CODES = (
    ActivityType.REST,
    ActivityType.AVAILABILITY,
    ActivityType.WORK,
    ActivityType.DRIVING,
)
"""Bits ``aa`` d'ActivityChangeInfo (2.1) : 00 repos, 01 disponibilite, 10 travail, 11 conduite."""


def decode_container(payload: bytes) -> dict[tuple[int, int], bytes]:
    """Decoupe un fichier de telechargement de carte en objets TLV (DDP_041 a DDP_046).

    Args:
        payload: Contenu complet du fichier.

    Returns:
        Un dictionnaire ``(FID, suffixe) -> valeur``.

    Raises:
        ParsingError: Le fichier est tronque ou n'a pas la forme attendue.
    """
    objects: dict[tuple[int, int], bytes] = {}
    position = 0
    while position < len(payload):
        if position + 5 > len(payload):
            raise ParsingError(
                "Le fichier de carte est tronque.",
                cause="La derniere structure du fichier est incomplete.",
                action="Telechargez a nouveau la carte.",
                technical_detail=f"en-tete incomplet a la position {position}",
            )
        fid = int.from_bytes(payload[position : position + 2], "big")
        suffix = payload[position + 2]
        length = int.from_bytes(payload[position + 3 : position + 5], "big")
        end = position + 5 + length
        if suffix > 0x03 or length == 0xFFFF or end > len(payload):
            raise ParsingError(
                "Le fichier n'a pas la structure d'un telechargement de carte.",
                cause="Une structure du fichier a une etiquette ou une longueur invalide.",
                action="Verifiez qu'il s'agit bien d'un fichier de carte conducteur (.C1B).",
                technical_detail=(
                    f"objet {fid:04X}/{suffix:02X} de {length} octets a la position {position}"
                ),
            )
        objects[(fid, suffix)] = payload[position + 5 : end]
        position = end
    return objects


def content_digest(payload: bytes) -> str | None:
    """Empreinte SHA-256 des donnees d'un telechargement de carte, signatures exclues.

    Les signatures ECDSA de 2e generation different a chaque telechargement (elles
    integrent un alea) : deux telechargements successifs d'une carte inchangee n'ont
    donc pas la meme empreinte de fichier, mais ont la meme empreinte de contenu.

    Args:
        payload: Contenu complet du fichier.

    Returns:
        L'empreinte hexadecimale, ou ``None`` si le fichier n'est pas un conteneur
        de carte valide.
    """
    try:
        objects = decode_container(payload)
    except ParsingError:
        return None
    digest = hashlib.sha256()
    for (fid, suffix), value in objects.items():
        if suffix in (SUFFIX_DATA_G1, SUFFIX_DATA_G2):
            digest.update(fid.to_bytes(2, "big") + bytes([suffix]))
            digest.update(len(value).to_bytes(2, "big") + value)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# Types elementaires (appendice 1)
# --------------------------------------------------------------------------- #
def _time_real(raw: bytes) -> datetime | None:
    """TimeReal (2.162) : secondes depuis le 1er janvier 1970 UTC ; 0 = absent."""
    value = int.from_bytes(raw, "big")
    if value in (0, 0xFFFFFFFF):
        return None
    return datetime.fromtimestamp(value, UTC)


def _datef(raw: bytes) -> date | None:
    """Datef (2.57) : AAAAMMJJ code en BCD ; ``00000000`` = pas de date."""
    digits = raw.hex()
    if digits == "00000000" or not digits.isdigit():
        return None
    try:
        return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def _name(raw: bytes) -> str | None:
    """Name (2.99) : un octet de code page puis le texte (chapitre 4)."""
    encoding = CODE_PAGES.get(raw[0], "latin-1")
    text = raw[1:].decode(encoding, errors="replace").strip(" \x00\xff")
    return text or None


def _ia5(raw: bytes) -> str | None:
    """IA5String : caracteres ASCII, espaces de remplissage retires."""
    text = raw.decode("ascii", errors="replace").strip(" \x00\xff")
    return text or None


def _registration(raw: bytes) -> tuple[str | None, str | None]:
    """VehicleRegistrationIdentification (2.166) : pays puis immatriculation (2.167)."""
    return nation_alpha(raw[0]), _name(raw[1:15])


class C1BParser(TachographFileParser):
    """Parser de fichier de telechargement de carte conducteur."""

    file_type = FileType.C1B
    specification_topic = "c1b"

    def __init__(self, data: bytes, *, filename: str | None = None) -> None:
        super().__init__(data, filename=filename)
        self._objects: dict[tuple[int, int], bytes] | None = None

    # ------------------------------------------------------------------ #
    # Conteneur
    # ------------------------------------------------------------------ #
    def _container(self) -> dict[tuple[int, int], bytes]:
        """Objets TLV du fichier, decoupes une seule fois."""
        if self._objects is None:
            self._objects = decode_container(self._data)
        return self._objects

    def _file(self, fid: int, *, required: bool = True) -> bytes | None:
        """Donnees d'un fichier de l'application de 1re generation.

        Raises:
            ParsingError: Le fichier est obligatoire et absent.
        """
        value = self._container().get((fid, SUFFIX_DATA_G1))
        if value is None and required:
            raise ParsingError(
                "Une partie attendue du fichier de carte est absente.",
                cause=f"Le fichier {fid:04X} de la carte ne figure pas dans le telechargement.",
                action="Telechargez a nouveau la carte.",
                technical_detail=f"objet {fid:04X}/00 absent",
            )
        return value

    def _validate_format(self) -> list[ParseDiagnostic]:
        """Verifie que le fichier est un conteneur TLV coherent."""
        objects = self._container()
        if not any(suffix == SUFFIX_DATA_G1 for _, suffix in objects):
            raise ParsingError(
                "Le fichier ne contient aucune donnee de carte exploitable.",
                cause="Aucune donnee de l'application tachygraphique n'a ete trouvee.",
                action="Verifiez qu'il s'agit bien d'un fichier de carte conducteur (.C1B).",
            )
        return self.unsupported_sections()

    # ------------------------------------------------------------------ #
    # Identification
    # ------------------------------------------------------------------ #
    def extract_driver(self) -> DecodedDriverIdentification | None:
        """Decode l'identification de la carte et de son titulaire (0520, 0521)."""
        raw = self._file(FID_IDENTIFICATION)
        assert raw is not None
        if len(raw) < 143:
            raise ParsingError(
                "L'identification de la carte est incomplete.",
                technical_detail=f"0520 : {len(raw)} octets au lieu de 143",
            )
        # CardIdentification (2.24) : 1 + 16 + 36 + 4 + 4 + 4 = 65 octets.
        issue = _time_real(raw[53:57])
        validity = _time_real(raw[57:61])
        expiry = _time_real(raw[61:65])
        # DriverCardHolderIdentification (2.62) : 36 + 36 + 4 + 2 = 78 octets.
        holder = raw[65:143]
        licence = self._file(FID_DRIVING_LICENCE, required=False)
        licence_fields: dict[str, str | None] = {}
        if licence is not None and len(licence) >= 53:
            licence_fields = {
                "licence_issuing_authority": _name(licence[0:36]),
                "licence_issuing_country": nation_alpha(licence[36]),
                "licence_number": _ia5(licence[37:53]),
            }
        card_number = _ia5(raw[1:17])
        if card_number is None:
            raise ParsingError(
                "Le numero de la carte est illisible.",
                technical_detail="0520 : cardNumber vide",
            )
        return DecodedDriverIdentification(
            card_number=card_number,
            card_issuing_country=nation_alpha(raw[0]),
            card_issuing_authority=_name(raw[17:53]),
            card_issue_date=issue.date() if issue else None,
            card_validity_begin=validity.date() if validity else None,
            card_expiry_date=expiry.date() if expiry else None,
            last_name=_name(holder[0:36]),
            first_name=_name(holder[36:72]),
            birth_date=_datef(holder[72:76]),
            preferred_language=_ia5(holder[76:78]),
            **licence_fields,
        )

    def extract_vehicle(self) -> DecodedVehicleIdentification | None:
        """Un telechargement de carte ne porte pas d'identification de vehicule propre."""
        return None

    # ------------------------------------------------------------------ #
    # Vehicules, lieux, conditions particulieres
    # ------------------------------------------------------------------ #
    def extract_vehicles_used(self) -> tuple[DecodedVehicleUse, ...]:
        """Decode les periodes d'utilisation de vehicules (0505), par date croissante."""
        raw = self._file(FID_VEHICLES_USED, required=False)
        if raw is None:
            return ()
        records: list[DecodedVehicleUse] = []
        for offset in range(2, len(raw) - VEHICLE_RECORD_SIZE + 1, VEHICLE_RECORD_SIZE):
            record = raw[offset : offset + VEHICLE_RECORD_SIZE]
            first_use = _time_real(record[6:10])
            country, registration = _registration(record[14:29])
            if first_use is None or registration is None:
                continue
            records.append(
                DecodedVehicleUse(
                    first_use=first_use,
                    last_use=_time_real(record[10:14]),
                    registration=registration,
                    registration_country=country,
                    odometer_begin=int.from_bytes(record[0:3], "big"),
                    odometer_end=int.from_bytes(record[3:6], "big"),
                )
            )
        return tuple(sorted(records, key=lambda item: item.first_use))

    def extract_places(self) -> tuple[DecodedPlace, ...]:
        """Decode les lieux de debut et de fin de periode de travail (0506)."""
        raw = self._file(FID_PLACES, required=False)
        if raw is None:
            return ()
        places: list[DecodedPlace] = []
        for offset in range(1, len(raw) - PLACE_RECORD_SIZE + 1, PLACE_RECORD_SIZE):
            record = raw[offset : offset + PLACE_RECORD_SIZE]
            entry_time = _time_real(record[0:4])
            if entry_time is None:
                continue
            places.append(
                DecodedPlace(
                    entry_time=entry_time,
                    entry_type=record[4],
                    country=nation_alpha(record[5]),
                    country_name=nation_name(record[5]),
                    region=record[6],
                    odometer=int.from_bytes(record[7:10], "big"),
                )
            )
        return tuple(sorted(places, key=lambda item: item.entry_time))

    def extract_specific_conditions(self) -> tuple[DecodedSpecificCondition, ...]:
        """Decode les conditions particulieres (0522)."""
        raw = self._file(FID_SPECIFIC_CONDITIONS, required=False)
        if raw is None:
            return ()
        conditions = [
            DecodedSpecificCondition(entry_time=entry_time, condition_type=raw[offset + 4])
            for offset in range(0, len(raw) - CONDITION_RECORD_SIZE + 1, CONDITION_RECORD_SIZE)
            if (entry_time := _time_real(raw[offset : offset + 4])) is not None
        ]
        return tuple(sorted(conditions, key=lambda item: item.entry_time))

    # ------------------------------------------------------------------ #
    # Evenements et anomalies
    # ------------------------------------------------------------------ #
    def extract_events(self) -> tuple[DecodedEvent, ...]:
        """Decode les evenements (0502) et les anomalies (0503), par date croissante."""
        records = [
            *self._event_records(FID_EVENTS, is_fault=False),
            *self._event_records(FID_FAULTS, is_fault=True),
        ]
        return tuple(sorted(records, key=lambda item: item.begin))

    def _event_records(self, fid: int, *, is_fault: bool) -> list[DecodedEvent]:
        """Decode un fichier d'enregistrements d'evenements ou d'anomalies."""
        raw = self._file(fid, required=False)
        if raw is None:
            return []
        records: list[DecodedEvent] = []
        for offset in range(0, len(raw) - EVENT_RECORD_SIZE + 1, EVENT_RECORD_SIZE):
            record = raw[offset : offset + EVENT_RECORD_SIZE]
            begin = _time_real(record[1:5])
            if begin is None:
                continue
            _, registration = _registration(record[9:24])
            records.append(
                DecodedEvent(
                    event_type_code=f"{record[0]:02X}",
                    begin=begin,
                    end=_time_real(record[5:9]),
                    vehicle_registration=registration,
                    description=event_fault_label(record[0]),
                    is_fault=is_fault,
                )
            )
        return records

    # ------------------------------------------------------------------ #
    # Activites
    # ------------------------------------------------------------------ #
    def extract_activities(self) -> tuple[DecodedActivityPeriod, ...]:
        """Decode les activites du conducteur (0504).

        Chaque enregistrement journalier contient les changements d'activite de la
        journee, dont celui de 00h00 (2.9). Une activite dure jusqu'au changement
        suivant ; la derniere de la journee jusqu'a minuit, sauf pour la journee en
        cours, bornee a l'instant du decodage. Une journee absente de la carte reste
        une periode sans enregistrement : rien n'est invente pour la combler.
        """
        raw = self._file(FID_DRIVER_ACTIVITY)
        assert raw is not None
        vehicles = self.extract_vehicles_used()
        now = utcnow()
        periods: list[DecodedActivityPeriod] = []
        for day, changes in self._daily_records(raw):
            day_end = min(day + timedelta(days=1), now)
            points = []
            for word in changes:
                minute = word & 0x7FF
                if minute >= 1440:
                    continue
                points.append((day + timedelta(minutes=minute), word))
            points.sort(key=lambda item: item[0])
            for index, (start, word) in enumerate(points):
                end = points[index + 1][0] if index + 1 < len(points) else day_end
                if end <= start:
                    continue
                periods.append(self._activity(start, end, word, vehicles))
        return tuple(periods)

    @staticmethod
    def _activity(
        start: datetime, end: datetime, word: int, vehicles: tuple[DecodedVehicleUse, ...]
    ) -> DecodedActivityPeriod:
        """Construit une periode depuis un ActivityChangeInfo (2.1).

        ``scpaattttttttttt`` : ``s`` emplacement, ``c`` equipage (carte inseree) ou
        activite connue (carte retiree), ``p`` carte retiree, ``aa`` activite.
        """
        slot = (word >> 15) & 1
        crew_or_known = (word >> 14) & 1
        not_inserted = (word >> 13) & 1
        activity = _ACTIVITY_CODES[(word >> 11) & 0b11]
        if not_inserted:
            known = bool(crew_or_known)
            return DecodedActivityPeriod(
                activity_type=activity if known else ActivityType.UNKNOWN,
                start=start,
                end=end,
                card_inserted=False,
                manual_entry=known,
            )
        registration = next(
            (
                vehicle.registration
                for vehicle in vehicles
                # Les activites sont enregistrees a la minute, l'utilisation du
                # vehicule a la seconde : on compare a la minute pres.
                if vehicle.first_use.replace(second=0, microsecond=0) <= start
                and (vehicle.last_use is None or start < vehicle.last_use)
            ),
            None,
        )
        return DecodedActivityPeriod(
            activity_type=activity,
            start=start,
            end=end,
            vehicle_registration=registration,
            card_slot=slot + 1,
            card_inserted=True,
            manual_entry=False,
            crew=bool(crew_or_known),
        )

    @staticmethod
    def _daily_records(raw: bytes) -> list[tuple[datetime, list[int]]]:
        """Parcourt la memoire circulaire des enregistrements journaliers (2.17).

        Le parcours part de l'enregistrement le plus recent et remonte grace a la
        longueur de l'enregistrement precedent, jusqu'au plus ancien.

        Returns:
            Les journees ``(date UTC a 00h00, mots ActivityChangeInfo)``, par date
            croissante.

        Raises:
            ParsingError: Les pointeurs ou les longueurs sont incoherents.
        """
        if len(raw) < 4 + DAILY_RECORD_HEADER:
            return []
        oldest = int.from_bytes(raw[0:2], "big")
        newest = int.from_bytes(raw[2:4], "big")
        buffer = raw[4:]
        size = len(buffer)
        if oldest >= size or newest >= size:
            raise ParsingError(
                "Les activites de la carte sont illisibles.",
                cause="Les pointeurs de la memoire des activites sont incoherents.",
                action="Telechargez a nouveau la carte.",
                technical_detail=f"oldest={oldest} newest={newest} taille={size}",
            )

        def read(position: int, count: int) -> bytes:
            return bytes(buffer[(position + index) % size] for index in range(count))

        days: list[tuple[datetime, list[int]]] = []
        position = newest
        for _ in range(size // DAILY_RECORD_HEADER + 1):
            previous_length = int.from_bytes(read(position, 2), "big")
            record_length = int.from_bytes(read(position + 2, 2), "big")
            day = _time_real(read(position + 4, 4))
            if record_length < DAILY_RECORD_HEADER or record_length > size or day is None:
                break
            count = (record_length - DAILY_RECORD_HEADER) // 2
            body = read(position + DAILY_RECORD_HEADER, count * 2)
            changes = [
                int.from_bytes(body[2 * index : 2 * index + 2], "big") for index in range(count)
            ]
            days.append((day, changes))
            if position == oldest or previous_length == 0:
                break
            position = (position - previous_length) % size
        days.reverse()
        return days

    # ------------------------------------------------------------------ #
    # Donnees techniques
    # ------------------------------------------------------------------ #
    def extract_technical_data(self) -> DecodedTechnicalData | None:
        """Retourne la generation de la carte et son numero."""
        objects = self._container()
        generation = "G2" if any(suffix == SUFFIX_DATA_G2 for _, suffix in objects) else "G1"
        raw = objects.get((FID_IDENTIFICATION, SUFFIX_DATA_G1))
        return DecodedTechnicalData(
            card_number=_ia5(raw[1:17]) if raw and len(raw) >= 17 else None,
            generation=generation,
        )

    def unsupported_sections(self) -> list[ParseDiagnostic]:
        """Sections presentes mais non decodees (application de 2e generation)."""
        if any(suffix == SUFFIX_DATA_G2 for _, suffix in self._container()):
            return [
                ParseDiagnostic(
                    level=DiagnosticLevel.INFO,
                    code="G2_NOT_DECODED",
                    message=(
                        "Les donnees propres a la 2e generation (positions GNSS, unites "
                        "embarquees utilisees) sont archivees mais pas encore affichees."
                    ),
                )
            ]
        return []
