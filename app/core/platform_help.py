"""Consignes d'installation et de diagnostic propres a chaque systeme.

La pile PC/SC n'est pas installee de la meme facon partout :

* Windows : le service « Carte a puce » (SCardSvr) est integre au systeme ;
* macOS : le service PC/SC est integre au systeme ;
* Linux : le service ``pcscd`` et sa bibliotheque sont des paquets a installer.

La bibliotheque Python ``pyscard`` est distribuee prete a l'emploi pour Windows et
macOS ; sous Linux, elle se compile et demande donc des paquets de developpement.
"""

from __future__ import annotations

import sys

__all__ = [
    "pcsc_install_action",
    "pcsc_service_action",
    "pcsc_service_cause",
    "reader_detection_action",
]


def _family(platform: str | None) -> str:
    value = platform if platform is not None else sys.platform
    if value.startswith("win"):
        return "windows"
    if value == "darwin":
        return "macos"
    return "linux"


def pcsc_install_action(platform: str | None = None) -> str:
    """Consigne pour installer la prise en charge des lecteurs de carte."""
    family = _family(platform)
    if family == "linux":
        return (
            "Installez les dependances : sudo apt install pcscd libpcsclite-dev "
            "python3-dev build-essential swig && pip install pyscard"
        )
    return "Installez la bibliotheque des lecteurs de carte : pip install pyscard"


def pcsc_service_cause(platform: str | None = None) -> str:
    """Cause probable d'une pile PC/SC qui ne repond pas."""
    family = _family(platform)
    if family == "windows":
        return "Le service Windows « Carte a puce » (SCardSvr) est arrete ou desactive."
    if family == "macos":
        return "Le service PC/SC de macOS n'a pas repondu."
    return "Le paquet pcscd n'est pas installe ou le service est arrete."


def pcsc_service_action(platform: str | None = None) -> str:
    """Consigne pour demarrer ou verifier le service PC/SC."""
    family = _family(platform)
    if family == "windows":
        return (
            "Ouvrez services.msc, puis demarrez le service « Carte a puce » et "
            "reglez son demarrage sur Automatique. Verifiez aussi que le pilote du "
            "lecteur est installe (Gestionnaire de peripheriques)."
        )
    if family == "macos":
        return "Debranchez puis rebranchez le lecteur. Si le probleme persiste, redemarrez le Mac."
    return (
        "Installez puis demarrez le service : "
        "sudo apt install pcscd pcsc-tools && sudo systemctl start pcscd "
        "(etat : sudo systemctl status pcscd)"
    )


def reader_detection_action(platform: str | None = None) -> str:
    """Consigne lorsque le service repond mais qu'aucun lecteur n'est detecte."""
    family = _family(platform)
    if family == "windows":
        return (
            "Branchez le lecteur USB, puis verifiez qu'il apparait dans le "
            "Gestionnaire de peripheriques (Lecteurs de cartes a puce)."
        )
    if family == "macos":
        return "Branchez le lecteur USB, puis verifiez sa presence dans Informations systeme > USB."
    return "Branchez le lecteur USB, puis verifiez sa detection avec la commande pcsc_scan."
