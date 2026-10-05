"""Enumerations du domaine tachygraphique.

Ces enumerations decrivent le **domaine**, pas le stockage : elles vivent donc
dans ``app.core`` et peuvent etre utilisees indifferemment par le parser (donnee
decodee), les modeles ORM (donnee metier), le moteur d'analyse et l'interface,
sans qu'aucune de ces couches ne depende d'une autre.

Les valeurs stockees en base sont les noms techniques en majuscules (stables,
utilisables par une future API REST). Les libelles francais destines a
l'interface sont fournis par la propriete ``label`` de chaque enumeration :
l'interface ne doit jamais afficher la valeur technique brute.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["FileType", "ParsingStatus", "ActivityType", "RuleStatus", "Severity"]


class FileType(StrEnum):
    """Type de fichier tachygraphique importe.

    Attributes:
        C1B: Telechargement de carte conducteur.
        V1B: Telechargement d'unite embarquee (vehicule).
    """

    C1B = "C1B"
    V1B = "V1B"

    @property
    def label(self) -> str:
        """Libelle affichable."""
        return {
            FileType.C1B: "Carte conducteur (C1B)",
            FileType.V1B: "Vehicule (V1B)",
        }[self]

    @property
    def extension(self) -> str:
        """Extension de fichier canonique, en majuscules, avec le point."""
        return f".{self.value}"


class ParsingStatus(StrEnum):
    """Etat du decodage d'un fichier importe.

    Attributes:
        PENDING: Fichier archive, decodage pas encore tente.
        PARTIAL: Decodage partiel : seules les structures confirmees ont ete lues.
        SUCCESS: Decodage complet.
        FAILED: Decodage en echec (le fichier original reste conserve).
        UNSUPPORTED: Format reconnu mais non encore pris en charge par cette version.
    """

    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"

    @property
    def label(self) -> str:
        """Libelle affichable."""
        return {
            ParsingStatus.PENDING: "En attente",
            ParsingStatus.PARTIAL: "Partiel",
            ParsingStatus.SUCCESS: "OK",
            ParsingStatus.FAILED: "Echec",
            ParsingStatus.UNSUPPORTED: "Non pris en charge",
        }[self]

    @property
    def is_terminal(self) -> bool:
        """Indique qu'aucun nouveau traitement automatique n'est attendu."""
        return self in {ParsingStatus.SUCCESS, ParsingStatus.FAILED}


class ActivityType(StrEnum):
    """Nature d'une periode d'activite du conducteur.

    Les quatre premieres valeurs correspondent aux quatre modes d'activite
    enregistres par un tachygraphe. ``UNKNOWN`` couvre les periodes dont le mode
    n'a pas pu etre determine : elles sont conservees telles quelles et ne sont
    jamais reclassees arbitrairement.

    Attributes:
        DRIVING: Temps de conduite.
        WORK: Autre tache (travail hors conduite).
        AVAILABILITY: Temps de disponibilite.
        REST: Repos ou pause (coupure).
        UNKNOWN: Mode indetermine.
    """

    DRIVING = "DRIVING"
    WORK = "WORK"
    AVAILABILITY = "AVAILABILITY"
    REST = "REST"
    UNKNOWN = "UNKNOWN"

    @property
    def label(self) -> str:
        """Libelle affichable."""
        return {
            ActivityType.DRIVING: "Conduite",
            ActivityType.WORK: "Travail",
            ActivityType.AVAILABILITY: "Disponibilite",
            ActivityType.REST: "Repos",
            ActivityType.UNKNOWN: "Indetermine",
        }[self]

    @property
    def color(self) -> str:
        """Couleur hexadecimale utilisee par la frise d'activites."""
        return {
            ActivityType.DRIVING: "#1F6FB2",
            ActivityType.WORK: "#E8A33D",
            ActivityType.AVAILABILITY: "#8FA0AE",
            ActivityType.REST: "#4C9A5E",
            ActivityType.UNKNOWN: "#B9BFC5",
        }[self]


class RuleStatus(StrEnum):
    """Resultat de l'evaluation d'une regle.

    Le vocabulaire affiche reste prudent : l'application signale une situation a
    verifier, elle ne qualifie jamais juridiquement une infraction (section 11 du
    cahier des charges).

    Attributes:
        OK: Aucun ecart detecte sur la periode analysee.
        WARNING: Situation a verifier.
        VIOLATION: Depassement apparent du seuil configure.
        NOT_APPLICABLE: Regle non evaluable (donnees insuffisantes sur la periode).
    """

    OK = "OK"
    WARNING = "WARNING"
    VIOLATION = "VIOLATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"

    @property
    def label(self) -> str:
        """Libelle affichable, volontairement non juridique."""
        return {
            RuleStatus.OK: "Conforme aux seuils configures",
            RuleStatus.WARNING: "Situation a verifier",
            RuleStatus.VIOLATION: "Depassement apparent",
            RuleStatus.NOT_APPLICABLE: "Non evaluable",
        }[self]

    @property
    def is_reportable(self) -> bool:
        """Indique si le resultat doit etre remonte a l'utilisateur."""
        return self in {RuleStatus.WARNING, RuleStatus.VIOLATION}


class Severity(StrEnum):
    """Niveau de criticite interne d'une anomalie detectee.

    Ce niveau est un critere de tri et de priorisation interne a l'application.
    Il ne correspond pas a la classification juridique des infractions, qui
    releve des autorites de controle.

    Attributes:
        INFO: Information, aucune action attendue.
        LOW: Ecart faible.
        MEDIUM: Ecart significatif.
        HIGH: Ecart important, a traiter en priorite.
    """

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def label(self) -> str:
        """Libelle affichable."""
        return {
            Severity.INFO: "Information",
            Severity.LOW: "Faible",
            Severity.MEDIUM: "Moyenne",
            Severity.HIGH: "Elevee",
        }[self]

    @property
    def rank(self) -> int:
        """Rang numerique croissant, pour le tri."""
        return {Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}[self]
