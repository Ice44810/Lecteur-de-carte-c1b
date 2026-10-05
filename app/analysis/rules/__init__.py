"""Moteur de regles : seuils configurables et evaluation.

Hierarchie prevue (section 12 du cahier des charges) :

.. code-block:: text

    Rule
    |-- DailyDrivingRule        (DAILY_DRIVING_MAX)
    |-- WeeklyDrivingRule       (WEEKLY_DRIVING_MAX, TWO_WEEK_DRIVING_MAX)
    |-- BreakRule               (CONTINUOUS_DRIVING_BREAK)
    |-- RestPeriodRule          (DAILY_REST_MINIMUM, WEEKLY_REST_MINIMUM)
    +-- OtherRule               (MISSING_DATA, CARD_EXPIRY, ...)

Aucune de ces classes n'est encore ecrite : le catalogue
:data:`~app.analysis.rules.catalogue.RULE_CATALOGUE` recense, pour chacune, le texte
a consulter et les parametres a saisir. Le cadre (contrat, configuration, registre,
evaluation) est en place et teste, de sorte que l'ecriture d'une regle se limite a
une classe et ses tests.
"""

from app.analysis.rules.base import Rule, RuleContext, RuleResult
from app.analysis.rules.catalogue import RULE_CATALOGUE, PlannedRule, planned_rule
from app.analysis.rules.config import (
    RULESET_FILENAME,
    RuleParameter,
    RuleSet,
    empty_ruleset,
    load_ruleset,
    save_ruleset,
)
from app.analysis.rules.registry import RuleRegistry, default_registry

__all__ = [
    "PlannedRule",
    "RULESET_FILENAME",
    "RULE_CATALOGUE",
    "Rule",
    "RuleContext",
    "RuleParameter",
    "RuleRegistry",
    "RuleResult",
    "RuleSet",
    "default_registry",
    "empty_ruleset",
    "load_ruleset",
    "planned_rule",
    "save_ruleset",
]
