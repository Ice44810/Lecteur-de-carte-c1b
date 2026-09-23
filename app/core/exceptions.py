"""Hierarchie d'exceptions applicatives.

Regle UX (cf. cahier des charges section 19) : l'utilisateur ne doit jamais voir
une simple stack trace. Chaque erreur applicative porte donc trois informations
distinctes :

* ``message`` : ce qui s'est passe, en francais, sans jargon technique ;
* ``cause``   : la raison probable, comprehensible par un exploitant ;
* ``action``  : ce que l'utilisateur peut faire pour resoudre le probleme.

Le detail technique (``technical_detail`` et l'exception d'origine chainee) reste
disponible pour les journaux et le developpeur.
"""

from __future__ import annotations

__all__ = [
    "TachyError",
    "ConfigurationError",
    "StorageError",
    "DatabaseError",
    "MigrationError",
    "ImportError_",
    "DuplicateFileError",
    "UnsupportedFileTypeError",
    "ParsingError",
    "UnconfirmedStructureError",
    "AnalysisError",
    "RuleConfigurationError",
    "ReportError",
    "CardReaderError",
    "PCSCUnavailableError",
    "NoReaderFoundError",
    "NoCardPresentError",
    "UnknownCardError",
    "CardCommunicationError",
]


class TachyError(Exception):
    """Exception de base de l'application.

    Args:
        message: Description courte et lisible du probleme.
        cause: Raison probable, formulee pour un utilisateur non technique.
        action: Action concrete suggeree a l'utilisateur.
        technical_detail: Detail reserve aux journaux (jamais affiche tel quel).
    """

    default_message = "Une erreur est survenue."
    default_cause = "Cause inconnue."
    default_action = "Consultez le journal de l'application pour plus de details."

    def __init__(
        self,
        message: str | None = None,
        *,
        cause: str | None = None,
        action: str | None = None,
        technical_detail: str | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.cause = cause or self.default_cause
        self.action = action or self.default_action
        self.technical_detail = technical_detail
        super().__init__(self.message)

    def user_report(self) -> tuple[str, str, str]:
        """Retourne le triplet (message, cause, action) destine a l'interface."""
        return self.message, self.cause, self.action

    def __str__(self) -> str:  # pragma: no cover - representation triviale
        return self.message


# --------------------------------------------------------------------------- #
# Configuration / stockage
# --------------------------------------------------------------------------- #
class ConfigurationError(TachyError):
    """Configuration invalide ou incoherente."""

    default_message = "La configuration de l'application est invalide."
    default_cause = "Un parametre obligatoire est absent ou incorrect."
    default_action = "Verifiez les parametres dans la page Parametres."


class StorageError(TachyError):
    """Probleme d'acces au systeme de fichiers (lecture, ecriture, droits)."""

    default_message = "Impossible d'acceder au stockage des fichiers."
    default_cause = "Le repertoire est inaccessible ou les droits sont insuffisants."
    default_action = "Verifiez le chemin de stockage et les permissions du repertoire."


# --------------------------------------------------------------------------- #
# Base de donnees
# --------------------------------------------------------------------------- #
class DatabaseError(TachyError):
    """Erreur d'acces a la base locale."""

    default_message = "Impossible d'acceder a la base de donnees."
    default_cause = "Le fichier de base est absent, verrouille ou corrompu."
    default_action = "Verifiez le chemin de la base dans les parametres."


class MigrationError(DatabaseError):
    """Echec de la mise a jour du schema de base."""

    default_message = "La mise a jour de la base de donnees a echoue."
    default_cause = "Une migration de schema n'a pas pu etre appliquee."
    default_action = (
        "Restaurez une sauvegarde de la base puis relancez l'application. "
        "Aucun fichier importe n'a ete supprime."
    )


# --------------------------------------------------------------------------- #
# Import de fichiers
# --------------------------------------------------------------------------- #
class ImportError_(TachyError):
    """Erreur lors de l'import d'un fichier tachygraphique.

    Le nom porte un suffixe ``_`` pour ne pas masquer le ``ImportError`` natif
    de Python.
    """

    default_message = "L'import du fichier a echoue."
    default_cause = "Le fichier n'a pas pu etre lu ou enregistre."
    default_action = "Verifiez que le fichier est accessible puis reessayez."


class UnsupportedFileTypeError(ImportError_):
    """Extension ou type de fichier non pris en charge."""

    default_message = "Ce type de fichier n'est pas pris en charge."
    default_cause = "Seuls les fichiers .C1B (carte conducteur) et .V1B (vehicule) sont acceptes."
    default_action = "Selectionnez un fichier .C1B ou .V1B."


class DuplicateFileError(ImportError_):
    """Fichier deja present en base (meme empreinte SHA-256)."""

    default_message = "Ce fichier a deja ete importe."
    default_cause = "Un fichier possedant la meme empreinte SHA-256 existe deja."
    default_action = "Ouvrez l'import existant depuis l'historique des telechargements."

    def __init__(
        self,
        message: str | None = None,
        *,
        cause: str | None = None,
        action: str | None = None,
        technical_detail: str | None = None,
        existing_file_id: int | None = None,
        sha256: str | None = None,
    ) -> None:
        super().__init__(
            message, cause=cause, action=action, technical_detail=technical_detail
        )
        self.existing_file_id = existing_file_id
        self.sha256 = sha256


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
class ParsingError(TachyError):
    """Le contenu binaire n'a pas pu etre decode."""

    default_message = "Le contenu du fichier n'a pas pu etre decode."
    default_cause = "Le fichier est incomplet, tronque ou d'un format inattendu."
    default_action = (
        "Le fichier original est conserve intact. "
        "Verifiez qu'il provient bien d'un telechargement tachygraphique complet."
    )


class UnconfirmedStructureError(ParsingError):
    """Structure binaire non confirmee par une specification officielle.

    Levee volontairement tant qu'une structure n'a pas ete validee contre le
    reglement d'execution (UE) 2016/799 annexe I C (ou l'annexe I B du reglement
    (CEE) 3821/85) et contre un fichier reel de test. Cette exception garantit
    qu'aucune donnee tachygraphique n'est inventee.
    """

    default_message = "Ce decodage n'est pas encore disponible."
    default_cause = (
        "La structure binaire correspondante n'a pas encore ete confirmee "
        "a partir d'une specification officielle et d'un fichier de test reel."
    )
    default_action = (
        "Le fichier est archive et son empreinte enregistree. "
        "Le decodage sera possible apres validation de la specification."
    )


# --------------------------------------------------------------------------- #
# Analyse et regles
# --------------------------------------------------------------------------- #
class AnalysisError(TachyError):
    """Erreur pendant le calcul d'une analyse."""

    default_message = "L'analyse n'a pas pu etre calculee."
    default_cause = "Les donnees de la periode demandee sont incompletes."
    default_action = "Verifiez la periode selectionnee puis relancez l'analyse."


class RuleConfigurationError(ConfigurationError):
    """Configuration de regle invalide ou source reglementaire absente."""

    default_message = "La configuration des regles est invalide."
    default_cause = "Un seuil est absent, incoherent, ou depourvu de source reglementaire."
    default_action = "Corrigez la configuration des regles dans la page Parametres > Regles."


# --------------------------------------------------------------------------- #
# Rapports
# --------------------------------------------------------------------------- #
class ReportError(TachyError):
    """Erreur lors de la generation d'un rapport."""

    default_message = "La generation du rapport a echoue."
    default_cause = "Le fichier de sortie n'a pas pu etre ecrit."
    default_action = "Verifiez le repertoire d'export et l'espace disque disponible."


# --------------------------------------------------------------------------- #
# Lecteur de carte
# --------------------------------------------------------------------------- #
class CardReaderError(TachyError):
    """Erreur generique liee au lecteur de carte."""

    default_message = "Impossible de communiquer avec le lecteur de carte."
    default_cause = "Le lecteur ou le service PC/SC n'est pas disponible."
    default_action = "Verifiez le branchement du lecteur et l'etat du service pcscd."


class PCSCUnavailableError(CardReaderError):
    """La pile PC/SC est absente ou le service pcscd est arrete."""

    default_message = "Le service PC/SC n'est pas disponible."
    default_cause = "Le paquet pcscd n'est pas installe ou le service est arrete."
    default_action = (
        "Installez puis demarrez le service : "
        "sudo apt install pcscd pcsc-tools && sudo systemctl start pcscd"
    )


class NoReaderFoundError(CardReaderError):
    """Aucun lecteur PC/SC detecte."""

    default_message = "Aucun lecteur de carte detecte."
    default_cause = "Aucun lecteur PC/SC n'est connecte ou reconnu par le systeme."
    default_action = "Branchez le lecteur USB puis verifiez sa detection avec la commande pcsc_scan."


class NoCardPresentError(CardReaderError):
    """Aucune carte inseree dans le lecteur."""

    default_message = "Aucune carte inseree."
    default_cause = "Le lecteur est detecte mais aucune carte n'est presente."
    default_action = "Inserez la carte conducteur dans le lecteur, puce vers le haut."


class UnknownCardError(CardReaderError):
    """Carte presente mais non identifiee comme carte tachygraphique."""

    default_message = "La carte inseree n'a pas ete reconnue."
    default_cause = (
        "La carte ne repond pas comme une carte tachygraphique connue "
        "(type de carte non identifie)."
    )
    default_action = "Verifiez qu'il s'agit bien d'une carte conducteur tachygraphique."


class CardCommunicationError(CardReaderError):
    """Echange APDU interrompu ou refuse par la carte."""

    default_message = "La communication avec la carte a echoue."
    default_cause = "La carte a interrompu l'echange ou a renvoye un statut d'erreur."
    default_action = "Retirez puis reinserez la carte sans la bouger pendant la lecture."
