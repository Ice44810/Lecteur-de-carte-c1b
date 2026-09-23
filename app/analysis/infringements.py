"""Evaluation des regles et production des alertes (ANALYSE -> ALERTE).

Ce module orchestre : il applique les regles actives d'un registre a une periode, et
agrege leurs resultats. Il ne contient lui-meme aucune regle et aucun seuil.

Vocabulaire impose (section 11 du cahier des charges) : les resultats produits sont
des « situations a verifier » et des « depassements apparents », jamais des
infractions etablies. Les libelles affiches proviennent de
:class:`~app.core.enums.RuleStatus`, ce qui garantit l'homogeneite du vocabulaire
dans toute l'application.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.analysis.rules.base import Rule, RuleContext, RuleResult
from app.analysis.rules.config import RuleSet
from app.analysis.rules.registry import RuleRegistry
from app.config.logging_config import get_logger
from app.core.enums import RuleStatus, Severity
from app.core.exceptions import RuleConfigurationError

__all__ = ["RuleEvaluation", "evaluate_rules", "InfringementCandidate"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class InfringementCandidate:
    """Alerte prete a etre enregistree en base.

    Sert de frontiere entre le moteur d'analyse et la persistance : le moteur ne
    construit pas d'objet ORM, le service d'analyse s'en charge.

    Attributes:
        driver_id: Conducteur concerne.
        occurred_on: Jour de service concerne.
        rule_code: Code de la regle.
        status: Resultat de la regle.
        severity: Criticite interne.
        description: Description prudente destinee a l'utilisateur.
        measured_value: Valeur mesuree.
        allowed_value: Seuil applique.
        unit: Unite des valeurs.
        regulation_reference: Source du seuil applique.
        activity_id: Activite concernee, si identifiable.
        source_file_id: Fichier a l'origine des donnees.
    """

    driver_id: int
    occurred_on: date
    rule_code: str
    status: RuleStatus
    severity: Severity
    description: str
    measured_value: float | None
    allowed_value: float | None
    unit: str
    regulation_reference: str | None
    activity_id: int | None = None
    source_file_id: int | None = None


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    """Resultat complet d'une evaluation de regles.

    Attributes:
        results: Tous les resultats produits, y compris les statuts ``OK``.
        skipped: Codes des regles non evaluees, avec la raison.
        ruleset_version: Version du jeu de parametres applique.
        rules_evaluated: Nombre de regles effectivement evaluees.
    """

    results: tuple[RuleResult, ...]
    skipped: tuple[tuple[str, str], ...] = ()
    ruleset_version: str = ""
    rules_evaluated: int = 0

    @property
    def warnings(self) -> tuple[RuleResult, ...]:
        """Resultats de statut ``WARNING`` (situations a verifier)."""
        return tuple(item for item in self.results if item.status is RuleStatus.WARNING)

    @property
    def violations(self) -> tuple[RuleResult, ...]:
        """Resultats de statut ``VIOLATION`` (depassements apparents)."""
        return tuple(item for item in self.results if item.status is RuleStatus.VIOLATION)

    @property
    def reportable(self) -> tuple[RuleResult, ...]:
        """Resultats devant etre presentes a l'utilisateur."""
        return tuple(item for item in self.results if item.is_reportable)

    @property
    def warnings_count(self) -> int:
        """Nombre de situations a verifier."""
        return len(self.warnings)

    @property
    def violations_count(self) -> int:
        """Nombre de depassements apparents."""
        return len(self.violations)

    def user_message(self) -> str:
        """Retourne un message de synthese prudent, affichable dans l'interface.

        Returns:
            Par exemple ``"7 situations necessitent une verification"``.
        """
        total = len(self.reportable)
        if total == 0:
            if self.rules_evaluated == 0:
                return (
                    "Aucun controle reglementaire effectue : aucune regle verifiee "
                    "n'est active."
                )
            return "Aucune situation a verifier sur la periode analysee."
        if total == 1:
            return "1 situation necessite une verification"
        return f"{total} situations necessitent une verification"

    def to_candidates(
        self, *, driver_id: int, source_file_id: int | None = None
    ) -> tuple[InfringementCandidate, ...]:
        """Convertit les resultats a signaler en alertes enregistrables.

        Args:
            driver_id: Conducteur concerne.
            source_file_id: Fichier a l'origine des donnees analysees.

        Returns:
            Les alertes correspondant aux resultats ``WARNING`` et ``VIOLATION``.
        """
        candidates: list[InfringementCandidate] = []
        for result in self.reportable:
            occurred_on = result.occurred_on or (
                result.period_start.date() if result.period_start else None
            )
            if occurred_on is None:
                logger.warning(
                    "Resultat de regle %s ignore : aucune date de service identifiable",
                    result.rule_code,
                )
                continue
            candidates.append(
                InfringementCandidate(
                    driver_id=driver_id,
                    occurred_on=occurred_on,
                    rule_code=result.rule_code,
                    status=result.status,
                    severity=result.severity,
                    description=result.description,
                    measured_value=result.measured_value,
                    allowed_value=result.allowed_value,
                    unit=result.unit,
                    regulation_reference=result.regulation_reference,
                    activity_id=result.activity_id,
                    source_file_id=source_file_id,
                )
            )
        return tuple(candidates)


def evaluate_rules(
    context: RuleContext,
    *,
    registry: RuleRegistry,
    ruleset: RuleSet | None = None,
) -> RuleEvaluation:
    """Applique les regles actives a une periode.

    Une regle dont un parametre n'est pas configure ou n'est pas confirme est
    **ignoree** et signalee dans ``skipped``, plutot que d'echouer : l'absence d'un
    seuil ne doit pas empecher les autres controles, et surtout ne doit jamais
    produire un resultat calcule sur une valeur devinee.

    Args:
        context: Donnees de la periode analysee.
        registry: Regles actives.
        ruleset: Jeu de parametres ; par defaut celui porte par le contexte.

    Returns:
        L'evaluation complete.
    """
    effective_ruleset = ruleset if ruleset is not None else context.ruleset
    if not isinstance(effective_ruleset, RuleSet):  # pragma: no cover - garde-fou
        raise TypeError("evaluate_rules attend un RuleSet")

    results: list[RuleResult] = []
    skipped: list[tuple[str, str]] = []
    evaluated = 0

    if registry.is_empty:
        logger.info(
            "Aucune regle active : analyse des temps effectuee, aucun controle reglementaire"
        )
        return RuleEvaluation(results=(), skipped=(), ruleset_version=effective_ruleset.version)

    evaluation_context = RuleContext(
        driver_id=context.driver_id,
        intervals=context.intervals,
        period_start=context.period_start,
        period_end=context.period_end,
        ruleset=effective_ruleset,
        metadata=context.metadata,
    )

    for rule in registry:
        try:
            results.extend(_evaluate_one(rule, evaluation_context))
            evaluated += 1
        except RuleConfigurationError as exc:
            logger.warning("Regle %s ignoree : %s", rule.code, exc.cause)
            skipped.append((rule.code, exc.cause))

    return RuleEvaluation(
        results=tuple(results),
        skipped=tuple(skipped),
        ruleset_version=effective_ruleset.version,
        rules_evaluated=evaluated,
    )


def _evaluate_one(rule: Rule, context: RuleContext) -> list[RuleResult]:
    """Evalue une regle apres verification de la disponibilite de ses parametres.

    Args:
        rule: Regle a evaluer.
        context: Contexte d'evaluation.

    Returns:
        Les resultats produits par la regle.

    Raises:
        RuleConfigurationError: Un parametre requis est absent ou non confirme.
    """
    ruleset: RuleSet = context.ruleset
    for parameter_code in rule.parameter_codes:
        ruleset.require(parameter_code)
    return rule.evaluate(context)
