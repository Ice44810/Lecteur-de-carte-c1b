"""Tables de correspondance du dictionnaire de donnees tachygraphique.

Sources :

* codes pays (``NationNumeric`` / ``NationAlpha``) : liste tenue par le laboratoire
  d'interoperabilite de la Commission europeenne (JRC), a laquelle renvoie le
  reglement d'execution (UE) 2016/799, annexe I C, appendice 1, types 2.100 et 2.101 :
  https://dtc.jrc.ec.europa.eu/dtc_nation_codes.php.html ;
* types d'evenements et d'anomalies (``EventFaultType``) : appendice 1, type 2.70 ;
* types de saisie de lieu (``EntryTypeDailyWorkPeriod``) : appendice 1, type 2.66 ;
* conditions particulieres (``SpecificConditionType``) : appendice 1, type 2.154 ;
* jeux de caracteres (``codePage``) : appendice 1, chapitre 4.
"""

from __future__ import annotations

__all__ = [
    "NATIONS",
    "nation_alpha",
    "nation_name",
    "event_fault_label",
    "ENTRY_TYPES",
    "SPECIFIC_CONDITIONS",
    "CODE_PAGES",
]

NATIONS: dict[int, tuple[str, str]] = {
    0x00: ("", "Aucune information"),
    0x01: ("A", "Autriche"),
    0x02: ("AL", "Albanie"),
    0x03: ("AND", "Andorre"),
    0x04: ("ARM", "Armenie"),
    0x05: ("AZ", "Azerbaidjan"),
    0x06: ("B", "Belgique"),
    0x07: ("BG", "Bulgarie"),
    0x08: ("BIH", "Bosnie-Herzegovine"),
    0x09: ("BY", "Bielorussie"),
    0x0A: ("CH", "Suisse"),
    0x0B: ("CY", "Chypre"),
    0x0C: ("CZ", "Republique tcheque"),
    0x0D: ("D", "Allemagne"),
    0x0E: ("DK", "Danemark"),
    0x0F: ("E", "Espagne"),
    0x10: ("EST", "Estonie"),
    0x11: ("F", "France"),
    0x12: ("FIN", "Finlande"),
    0x13: ("FL", "Liechtenstein"),
    0x14: ("FR", "Iles Feroe"),
    0x15: ("UK", "Royaume-Uni"),
    0x16: ("GE", "Georgie"),
    0x17: ("GR", "Grece"),
    0x18: ("H", "Hongrie"),
    0x19: ("HR", "Croatie"),
    0x1A: ("I", "Italie"),
    0x1B: ("IRL", "Irlande"),
    0x1C: ("IS", "Islande"),
    0x1D: ("KZ", "Kazakhstan"),
    0x1E: ("L", "Luxembourg"),
    0x1F: ("LT", "Lituanie"),
    0x20: ("LV", "Lettonie"),
    0x21: ("M", "Malte"),
    0x22: ("MC", "Monaco"),
    0x23: ("MD", "Moldavie"),
    0x24: ("MK", "Macedoine du Nord"),
    0x25: ("N", "Norvege"),
    0x26: ("NL", "Pays-Bas"),
    0x27: ("P", "Portugal"),
    0x28: ("PL", "Pologne"),
    0x29: ("RO", "Roumanie"),
    0x2A: ("RSM", "Saint-Marin"),
    0x2B: ("RUS", "Russie"),
    0x2C: ("S", "Suede"),
    0x2D: ("SK", "Slovaquie"),
    0x2E: ("SLO", "Slovenie"),
    0x2F: ("TM", "Turkmenistan"),
    0x30: ("TR", "Turquie"),
    0x31: ("UA", "Ukraine"),
    0x32: ("V", "Vatican"),
    0x33: ("YU", "Yougoslavie"),
    0x34: ("MNE", "Montenegro"),
    0x35: ("SRB", "Serbie"),
    0x36: ("UZ", "Ouzbekistan"),
    0x37: ("TJ", "Tadjikistan"),
    0x38: ("KG", "Kirghizistan"),
    0x39: ("IL", "Israel"),
    0xFD: ("EC", "Communaute europeenne"),
    0xFE: ("EUR", "Reste de l'Europe"),
    0xFF: ("WLD", "Reste du monde"),
}
"""Codes pays : valeur numerique -> (code alphabetique, nom)."""


def nation_alpha(code: int) -> str | None:
    """Retourne le code alphabetique d'un pays, ou ``None`` s'il est inconnu ou absent."""
    entry = NATIONS.get(code)
    return entry[0] or None if entry else None


def nation_name(code: int) -> str:
    """Retourne le nom d'un pays, ou une mention explicite d'un code non repertorie."""
    entry = NATIONS.get(code)
    return entry[1] if entry else f"Code pays non repertorie ({code:02X}h)"


_EVENT_FAULT_LABELS: dict[int, str] = {
    0x00: "Evenement general sans precision",
    0x01: "Insertion d'une carte non valable",
    0x02: "Conflit de cartes",
    0x03: "Chevauchement temporel",
    0x04: "Conduite sans carte appropriee",
    0x05: "Insertion de la carte en cours de conduite",
    0x06: "Derniere session de carte mal cloturee",
    0x07: "Exces de vitesse",
    0x08: "Interruption de l'alimentation electrique",
    0x09: "Erreur sur les donnees de mouvement",
    0x0A: "Conflit concernant le mouvement du vehicule",
    0x0B: "Conflit temporel (GNSS / horloge de l'unite embarquee)",
    0x0C: "Erreur de communication avec le dispositif de communication a distance",
    0x0D: "Absence d'information de position du recepteur GNSS",
    0x0E: "Erreur de communication avec le dispositif GNSS externe",
    0x0F: "Anomalie GNSS",
    0x10: "Tentative d'atteinte a la securite (unite embarquee) sans precision",
    0x11: "Echec d'authentification du capteur de mouvement",
    0x12: "Echec d'authentification de la carte tachygraphique",
    0x13: "Changement non autorise du capteur de mouvement",
    0x14: "Erreur d'integrite des donnees de la carte",
    0x15: "Erreur d'integrite des donnees enregistrees",
    0x16: "Erreur de transfert interne de donnees",
    0x17: "Ouverture non autorisee du boitier",
    0x18: "Sabotage du materiel",
    0x19: "Detection de manipulation du GNSS",
    0x1A: "Echec d'authentification du dispositif GNSS externe",
    0x1B: "Certificat du dispositif GNSS externe expire",
    0x1C: "Incoherence entre donnees de mouvement et activites enregistrees",
    0x20: "Tentative d'atteinte a la securite (capteur) sans precision",
    0x21: "Echec d'authentification (capteur)",
    0x22: "Erreur d'integrite des donnees enregistrees (capteur)",
    0x23: "Erreur de transfert interne de donnees (capteur)",
    0x24: "Ouverture non autorisee du boitier (capteur)",
    0x25: "Sabotage du materiel (capteur)",
    0x30: "Anomalie de l'appareil de controle sans precision",
    0x31: "Anomalie interne de l'unite embarquee",
    0x32: "Anomalie de l'imprimante",
    0x33: "Anomalie de l'affichage",
    0x34: "Anomalie de telechargement",
    0x35: "Anomalie du capteur",
    0x36: "Anomalie du recepteur GNSS interne",
    0x37: "Anomalie du dispositif GNSS externe",
    0x38: "Anomalie du dispositif de communication a distance",
    0x39: "Anomalie de l'interface ITS",
    0x3A: "Anomalie du capteur interne",
    0x40: "Anomalie de la carte sans precision",
}


def event_fault_label(code: int) -> str:
    """Retourne le libelle d'un type d'evenement ou d'anomalie (appendice 1, 2.70)."""
    if code in _EVENT_FAULT_LABELS:
        return _EVENT_FAULT_LABELS[code]
    if code >= 0x80:
        return f"Code propre au constructeur ({code:02X}h)"
    return f"Code reserve ({code:02X}h)"


ENTRY_TYPES: dict[int, str] = {
    0: "Debut (carte inseree)",
    1: "Fin (carte retiree)",
    2: "Debut (saisie manuelle)",
    3: "Fin (saisie manuelle)",
    4: "Debut (deduit par l'unite embarquee)",
    5: "Fin (deduit par l'unite embarquee)",
}
"""Types de saisie d'un lieu de debut ou de fin de periode de travail (2.66)."""

SPECIFIC_CONDITIONS: dict[int, str] = {
    1: "Hors champ - debut",
    2: "Hors champ - fin",
    3: "Traversee en ferry / train - debut",
    4: "Traversee en ferry / train - fin",
}
"""Conditions particulieres (2.154, generation 2 ; en generation 1, le code 3 seul)."""

CODE_PAGES: dict[int, str] = {
    1: "iso8859_1",
    2: "iso8859_2",
    3: "iso8859_3",
    5: "iso8859_5",
    7: "iso8859_7",
    9: "iso8859_9",
    13: "iso8859_13",
    15: "iso8859_15",
    16: "iso8859_16",
}
"""Jeux de caracteres des noms et immatriculations (appendice 1, chapitre 4)."""
