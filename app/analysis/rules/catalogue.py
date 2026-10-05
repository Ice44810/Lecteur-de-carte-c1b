"""Catalogue des regles a implementer et des seuils a verifier.

Ce catalogue joue pour le moteur de regles le meme role que
:mod:`app.parser.specification` pour le decodage : il enonce ce qui reste a
confirmer, avec la reference a consulter, **avant** que du code ne soit ecrit.

Il est volontairement declaratif et ne contient aucune valeur de seuil : les valeurs
seront saisies dans le jeu de regles (``rules.json``) apres verification du texte, et
marquees comme confirmees a ce moment-la.

Textes a consulter :

* reglement (CE) no 561/2006 du Parlement europeen et du Conseil du 15 mars 2006
  (temps de conduite, pauses et temps de repos), notamment ses articles 4, 6, 7 et 8 ;
* reglement (UE) 2020/1054 du 15 juillet 2020, qui modifie le precedent ;
* directive 2002/15/CE du 11 mars 2002 (temps de travail des personnels mobiles) ;
* reglement (UE) no 165/2014 du 4 fevrier 2014 (appareils de controle) ;
* le cas echeant, la reglementation nationale applicable et l'accord AETR pour les
  trajets hors Union.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.parser.specification import ConfirmationStatus

__all__ = ["PlannedRule", "RULE_CATALOGUE", "REGULATION_SOURCES", "planned_rule"]


REGULATION_SOURCES: tuple[str, ...] = (
    "Reglement (CE) no 561/2006 du 15 mars 2006 - temps de conduite, pauses et repos",
    "Reglement (UE) 2020/1054 du 15 juillet 2020 - modification du reglement 561/2006",
    "Directive 2002/15/CE du 11 mars 2002 - temps de travail des personnels mobiles",
    "Reglement (UE) no 165/2014 du 4 fevrier 2014 - appareils de controle dans le"
    " transport routier",
    "Accord AETR - trajets effectues hors Union europeenne",
)
"""Textes de reference a consulter avant activation d'une regle."""


@dataclass(frozen=True, slots=True)
class PlannedRule:
    """Regle prevue, non encore implementee.

    Attributes:
        code: Code stable que portera la regle.
        title: Libelle affichable prevu.
        description: Ce que la regle devra verifier.
        reference_to_verify: Texte et article a consulter pour fixer le seuil.
        parameter_codes: Parametres de configuration necessaires.
        status: Etat de verification de la reference.
    """

    code: str
    title: str
    description: str
    reference_to_verify: str
    parameter_codes: tuple[str, ...] = field(default_factory=tuple)
    status: ConfirmationStatus = ConfirmationStatus.OPEN


RULE_CATALOGUE: tuple[PlannedRule, ...] = (
    PlannedRule(
        code="DAILY_DRIVING_MAX",
        title="Duree de conduite journaliere",
        description=(
            "Comparer le temps de conduite de chaque journee au maximum autorise, en "
            "tenant compte de la possibilite d'un maximum etendu un nombre limite de "
            "fois par semaine."
        ),
        reference_to_verify="Reglement (CE) no 561/2006, article 6, paragraphe 1",
        parameter_codes=(
            "DAILY_DRIVING_MAX_SECONDS",
            "DAILY_DRIVING_EXTENDED_SECONDS",
            "DAILY_DRIVING_EXTENSIONS_PER_WEEK",
        ),
    ),
    PlannedRule(
        code="WEEKLY_DRIVING_MAX",
        title="Duree de conduite hebdomadaire",
        description="Comparer le temps de conduite de la semaine au maximum autorise.",
        reference_to_verify="Reglement (CE) no 561/2006, article 6, paragraphe 2",
        parameter_codes=("WEEKLY_DRIVING_MAX_SECONDS",),
    ),
    PlannedRule(
        code="TWO_WEEK_DRIVING_MAX",
        title="Duree de conduite sur deux semaines consecutives",
        description=(
            "Comparer le cumul de conduite de deux semaines consecutives au maximum autorise."
        ),
        reference_to_verify="Reglement (CE) no 561/2006, article 6, paragraphe 3",
        parameter_codes=("TWO_WEEK_DRIVING_MAX_SECONDS",),
    ),
    PlannedRule(
        code="CONTINUOUS_DRIVING_BREAK",
        title="Interruption de conduite continue",
        description=(
            "Verifier qu'une interruption d'une duree minimale intervient avant d'avoir "
            "atteint la duree de conduite continue maximale, y compris lorsque "
            "l'interruption est fractionnee."
        ),
        reference_to_verify="Reglement (CE) no 561/2006, article 7",
        parameter_codes=(
            "CONTINUOUS_DRIVING_MAX_SECONDS",
            "BREAK_MINIMUM_SECONDS",
            "BREAK_FIRST_PART_SECONDS",
            "BREAK_SECOND_PART_SECONDS",
        ),
    ),
    PlannedRule(
        code="DAILY_REST_MINIMUM",
        title="Repos journalier",
        description=(
            "Verifier la duree du repos journalier, en distinguant repos normal, repos "
            "reduit, repos fractionne, et le nombre de repos reduits autorises entre "
            "deux repos hebdomadaires."
        ),
        reference_to_verify="Reglement (CE) no 561/2006, article 8, paragraphes 1 a 5",
        parameter_codes=(
            "DAILY_REST_NORMAL_SECONDS",
            "DAILY_REST_REDUCED_SECONDS",
            "DAILY_REST_SPLIT_FIRST_SECONDS",
            "DAILY_REST_SPLIT_SECOND_SECONDS",
            "REDUCED_DAILY_REST_PER_WEEK",
        ),
    ),
    PlannedRule(
        code="WEEKLY_REST_MINIMUM",
        title="Repos hebdomadaire",
        description=(
            "Verifier la duree et la periodicite du repos hebdomadaire, ainsi que la "
            "compensation d'un repos hebdomadaire reduit."
        ),
        reference_to_verify="Reglement (CE) no 561/2006, article 8, paragraphes 6 a 9",
        parameter_codes=(
            "WEEKLY_REST_NORMAL_SECONDS",
            "WEEKLY_REST_REDUCED_SECONDS",
            "WEEKLY_REST_MAX_INTERVAL_SECONDS",
        ),
    ),
    PlannedRule(
        code="WORKING_TIME_MAX",
        title="Temps de travail hebdomadaire",
        description=(
            "Verifier le temps de travail hebdomadaire et sa moyenne, apres confirmation "
            "de la composition du temps de travail."
        ),
        reference_to_verify="Directive 2002/15/CE, articles 4 et 3",
        parameter_codes=("WEEKLY_WORKING_TIME_MAX_SECONDS", "WEEKLY_WORKING_TIME_AVERAGE_SECONDS"),
    ),
    PlannedRule(
        code="NIGHT_WORK",
        title="Travail de nuit",
        description="Verifier la duree du travail effectue pendant la periode nocturne.",
        reference_to_verify="Directive 2002/15/CE, article 7",
        parameter_codes=("NIGHT_WORK_MAX_SECONDS", "NIGHT_PERIOD_START", "NIGHT_PERIOD_END"),
    ),
    PlannedRule(
        code="MISSING_DATA",
        title="Periodes sans enregistrement",
        description=(
            "Signaler les periodes pour lesquelles aucune activite n'est enregistree, "
            "afin que l'exploitant verifie l'exhaustivite des telechargements. Cette "
            "regle ne depend d'aucun seuil reglementaire, seulement d'une duree de "
            "tolerance choisie par l'entreprise."
        ),
        reference_to_verify=(
            "Reglement (UE) no 165/2014, article 36 - obligations de conservation "
            "et de telechargement des donnees"
        ),
        parameter_codes=("MISSING_DATA_TOLERANCE_SECONDS",),
    ),
    PlannedRule(
        code="CARD_EXPIRY",
        title="Validite de la carte conducteur",
        description="Signaler une carte conducteur expiree ou proche de l'expiration.",
        reference_to_verify="Reglement (UE) no 165/2014, article 28",
        parameter_codes=("CARD_EXPIRY_WARNING_SECONDS",),
    ),
)
"""Regles prevues, avec la reference a verifier pour chacune.

Aucune de ces regles n'est implementee : ce catalogue constitue le cahier des charges
de la phase 7. Implementer une regle suppose, dans cet ordre : consulter le texte
cite, saisir les seuils dans ``rules.json`` avec leur source, marquer ces seuils comme
confirmes, ecrire la classe de regle et ses tests.
"""


def planned_rule(code: str) -> PlannedRule | None:
    """Retourne la fiche d'une regle prevue, ou ``None`` si le code est inconnu."""
    normalized = code.upper()
    return next((item for item in RULE_CATALOGUE if item.code == normalized), None)
