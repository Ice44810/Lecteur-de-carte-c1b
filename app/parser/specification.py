"""Registre des incertitudes de specification.

Ce module est la traduction en code d'une exigence du cahier des charges : ne
jamais inventer une structure binaire ni une donnee tachygraphique. Il recense les
points qui doivent etre confirmes a partir d'une source officielle **avant** que le
decodage correspondant ne soit implemente.

Sources a utiliser pour la confirmation (aucune n'est reproduite ici, seules leurs
references sont citees) :

* reglement d'execution (UE) 2016/799 de la Commission du 18 mars 2016, annexe I C
  (tachygraphe intelligent), en particulier :

  - appendice 1 : dictionnaire de donnees (definition de chaque type) ;
  - appendice 2 : specification de la carte a puce tachygraphique ;
  - appendice 7 : protocole de telechargement des donnees ;

* reglement (CEE) no 3821/85 du Conseil, annexe I B, pour les equipements et cartes
  des generations anterieures, dont les memes appendices 1, 2 et 7.

Regle d'usage : tant qu'une entree de :data:`OPEN_QUESTIONS` porte le statut
``OPEN``, le code correspondant doit lever
:class:`~app.core.exceptions.UnconfirmedStructureError` plutot que produire une
valeur. Une entree ne passe a ``CONFIRMED`` que lorsque deux conditions sont
reunies : la reference precise de la specification est renseignee, et un fichier
reel de test valide le decodage dans ``tests/fixtures/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "ConfirmationStatus",
    "OpenQuestion",
    "OPEN_QUESTIONS",
    "REFERENCE_DOCUMENTS",
    "questions_for",
    "is_confirmed",
    "unconfirmed_topics",
]


class ConfirmationStatus(StrEnum):
    """Etat de confirmation d'un point de specification.

    Attributes:
        OPEN: Non confirme. Aucun decodage ne doit etre tente.
        IN_REVIEW: Reference identifiee, validation sur fichier reel en cours.
        CONFIRMED: Reference et fichier de test valides ; decodage autorise.
    """

    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    CONFIRMED = "CONFIRMED"

    @property
    def label(self) -> str:
        """Libelle affichable."""
        return {
            ConfirmationStatus.OPEN: "A confirmer",
            ConfirmationStatus.IN_REVIEW: "En cours de validation",
            ConfirmationStatus.CONFIRMED: "Confirme",
        }[self]


@dataclass(frozen=True, slots=True)
class OpenQuestion:
    """Point de specification a confirmer avant implementation.

    Attributes:
        topic: Domaine concerne (``c1b``, ``v1b``, ``card``).
        code: Identifiant stable, utilisable dans les diagnostics et les tests.
        question: Ce qui doit precisement etre determine.
        reference: Document et section a consulter.
        status: Etat de confirmation.
        blocking: Indique que cette question bloque le decodage du format.
    """

    topic: str
    code: str
    question: str
    reference: str
    status: ConfirmationStatus = ConfirmationStatus.OPEN
    blocking: bool = True


REFERENCE_DOCUMENTS: tuple[str, ...] = (
    "Reglement d'execution (UE) 2016/799, annexe I C, appendice 1 - dictionnaire de donnees",
    "Reglement d'execution (UE) 2016/799, annexe I C, appendice 2 - carte tachygraphique",
    "Reglement d'execution (UE) 2016/799, annexe I C, appendice 7 - telechargement des donnees",
    "Reglement d'execution (UE) 2016/799, annexe I C, appendice 11 - securite (signatures)",
    "Reglement (CEE) no 3821/85, annexe I B, appendices 1, 2, 7 et 11 - generations anterieures",
)
"""References a consulter pour lever les incertitudes ci-dessous."""


OPEN_QUESTIONS: tuple[OpenQuestion, ...] = (
    OpenQuestion(
        topic="c1b",
        code="C1B_CONTAINER_LAYOUT",
        question=(
            "Organisation exacte du conteneur d'un fichier de telechargement de carte "
            "conducteur : nature et taille du marqueur de debut de chaque bloc, codage de "
            "la longueur, et emplacement des blocs de signature."
        ),
        reference="Annexe I C, appendice 7 (protocole de telechargement), section carte conducteur",
    ),
    OpenQuestion(
        topic="c1b",
        code="C1B_BLOCK_IDENTIFIERS",
        question=(
            "Liste des identifiants de blocs presents dans un telechargement de carte et "
            "correspondance avec les fichiers elementaires de la carte."
        ),
        reference="Annexe I C, appendice 2 (structure de fichiers de la carte)",
    ),
    OpenQuestion(
        topic="c1b",
        code="C1B_DRIVER_IDENTIFICATION_FIELDS",
        question=(
            "Position, longueur et codage des champs d'identification du titulaire "
            "(numero de carte, nom, prenom, date de naissance, pays emetteur, dates de "
            "validite), y compris la page de codes utilisee pour les caracteres."
        ),
        reference=(
            "Annexe I C, appendice 1 (types CardIdentification, DriverCardHolderIdentification)"
        ),
    ),
    OpenQuestion(
        topic="c1b",
        code="C1B_ACTIVITY_CHANGE_ENCODING",
        question=(
            "Codage des enregistrements de changement d'activite : bits de mode d'activite, "
            "minute de la journee, et regle de reconstitution des bornes de fin de periode."
        ),
        reference="Annexe I C, appendice 1 (type ActivityChangeInfo)",
    ),
    OpenQuestion(
        topic="c1b",
        code="C1B_TIME_ENCODING",
        question=(
            "Codage des horodatages et referentiel temporel applique (UTC ou heure locale) "
            "pour chaque type de date du dictionnaire de donnees."
        ),
        reference="Annexe I C, appendice 1 (types TimeReal, Datef)",
    ),
    OpenQuestion(
        topic="c1b",
        code="C1B_EVENT_FAULT_CODES",
        question=(
            "Table de correspondance entre les codes d'evenements et d'anomalies et leur "
            "libelle, pour chaque generation d'equipement."
        ),
        reference="Annexe I C, appendice 1 (types EventFaultType)",
        blocking=False,
    ),
    OpenQuestion(
        topic="c1b",
        code="C1B_SIGNATURE_VERIFICATION",
        question=(
            "Procedure de verification des signatures numeriques accompagnant les blocs de "
            "donnees, et chaine de certification a utiliser."
        ),
        reference="Annexe I C, appendice 11 (mecanismes de securite)",
        blocking=False,
    ),
    OpenQuestion(
        topic="v1b",
        code="V1B_CONTAINER_LAYOUT",
        question=(
            "Organisation du conteneur d'un telechargement d'unite embarquee et liste des "
            "blocs de donnees transmis."
        ),
        reference="Annexe I C, appendice 7 (protocole de telechargement), section unite embarquee",
    ),
    OpenQuestion(
        topic="v1b",
        code="V1B_VEHICLE_IDENTIFICATION_FIELDS",
        question=(
            "Position et codage de l'immatriculation, du pays d'immatriculation, du VIN et "
            "de l'identifiant de l'unite embarquee."
        ),
        reference=(
            "Annexe I C, appendice 1 (types VehicleIdentificationNumber, "
            "VehicleRegistrationIdentification)"
        ),
    ),
    OpenQuestion(
        topic="v1b",
        code="V1B_DRIVER_SLOT_ACTIVITIES",
        question=(
            "Reconstitution des activites par emplacement de carte (conducteur et convoyeur) "
            "a partir des blocs d'activite de l'unite embarquee."
        ),
        reference="Annexe I C, appendice 1 (types VuActivityDailyData)",
    ),
    OpenQuestion(
        topic="card",
        code="CARD_APPLICATION_SELECTION",
        question=(
            "Identifiant d'application (AID) et sequence de selection a utiliser pour "
            "acceder a l'application tachygraphique d'une carte conducteur."
        ),
        reference="Annexe I C, appendice 2 (selection de l'application tachygraphique)",
    ),
    OpenQuestion(
        topic="card",
        code="CARD_FILE_IDENTIFIERS",
        question=(
            "Identifiants des fichiers elementaires a lire et ordre de lecture pour "
            "reconstituer un telechargement complet."
        ),
        reference="Annexe I C, appendice 2 (structure de fichiers)",
    ),
    OpenQuestion(
        topic="card",
        code="CARD_READ_BINARY_SEQUENCE",
        question=(
            "Sequence exacte des commandes de lecture (selection, lecture par blocs, "
            "gestion des reponses longues) et traitement des mots d'etat renvoyes."
        ),
        reference="Annexe I C, appendice 2 (commandes) et ISO/IEC 7816-4",
    ),
    OpenQuestion(
        topic="card",
        code="CARD_DOWNLOAD_FILE_ASSEMBLY",
        question=(
            "Regles d'assemblage des donnees lues sur la carte en un fichier .C1B "
            "conforme, afin qu'il soit exploitable par des outils tiers."
        ),
        reference="Annexe I C, appendice 7 (format du fichier de telechargement)",
    ),
)
"""Points de specification a confirmer, par domaine."""


def questions_for(topic: str, *, blocking_only: bool = False) -> tuple[OpenQuestion, ...]:
    """Retourne les questions ouvertes d'un domaine.

    Args:
        topic: Domaine recherche (``c1b``, ``v1b``, ``card``).
        blocking_only: Ne retenir que les questions bloquantes.

    Returns:
        Les questions correspondantes, dans l'ordre de declaration.
    """
    normalized = topic.lower()
    return tuple(
        question
        for question in OPEN_QUESTIONS
        if question.topic == normalized and (not blocking_only or question.blocking)
    )


def unconfirmed_topics() -> tuple[str, ...]:
    """Retourne les domaines comportant au moins une question bloquante non confirmee."""
    topics = {
        question.topic
        for question in OPEN_QUESTIONS
        if question.blocking and question.status is not ConfirmationStatus.CONFIRMED
    }
    return tuple(sorted(topics))


def is_confirmed(topic: str) -> bool:
    """Indique si un domaine peut etre decode.

    Args:
        topic: Domaine evalue.

    Returns:
        ``True`` si aucune question bloquante du domaine n'est en attente de
        confirmation.
    """
    return all(
        question.status is ConfirmationStatus.CONFIRMED
        for question in questions_for(topic, blocking_only=True)
    )
