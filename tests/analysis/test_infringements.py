"""Tests de l'orchestration des regles et de la production des alertes.

Ces tests verifient trois exigences du cahier des charges qui portent sur le
comportement, et non sur un calcul :

* une regle dont le seuil n'est pas configure, ou pas encore verifie, est **ignoree**
  et signalee : elle ne produit jamais un resultat calcule sur une valeur devinee ;
* le vocabulaire reste prudent, y compris dans les messages de synthese ;
* chaque alelte produite conserve la source du seuil applique et la version du jeu de
  regles, pour pouvoir etre retracee.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest

from app.analysis.infringements import RuleEvaluation, evaluate_rules
from app.analysis.models import ActivityInterval
from app.analysis.rules import (
    Rule,
    RuleContext,
    RuleRegistry,
    RuleResult,
    RuleSet,
    empty_ruleset,
)
from app.analysis.rules.config import RuleParameter
from app.core.enums import ActivityType, RuleStatus, Severity
from app.parser.specification import ConfirmationStatus

JOUR = datetime(2026, 9, 15, tzinfo=UTC)
FIN = datetime(2026, 9, 16, tzinfo=UTC)

SOURCE_FICTIVE = "Source de test - aucune valeur reglementaire reelle n'est utilisee ici"


class ReglePourTest(Rule):
    """Regle minimale servant a tester l'orchestration, pas une regle reelle.

    Elle ne mesure rien : elle retourne le resultat qui lui a ete fourni. Cela permet
    de tester l'agregation sans introduire de seuil reglementaire dans les tests.
    """

    code = "TEST_ORCHESTRATION"
    title = "Regle de test de l'orchestration"
    regulation_reference = SOURCE_FICTIVE
    parameter_codes = ()

    def __init__(self, results: list[RuleResult]) -> None:
        self._results = results
        self.calls = 0

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        """Retourne les resultats preprogrammes et compte les appels."""
        self.calls += 1
        return list(self._results)


class RegleAvecSeuil(ReglePourTest):
    """Regle de test exigeant un parametre, pour verifier le filtrage."""

    code = "TEST_AVEC_SEUIL"
    title = "Regle de test exigeant un seuil"
    regulation_reference = SOURCE_FICTIVE
    parameter_codes = ("TEST_SEUIL",)


def resultat(
    *,
    status: RuleStatus = RuleStatus.VIOLATION,
    code: str = "TEST_ORCHESTRATION",
    severity: Severity = Severity.HIGH,
    occurred_on: date | None = None,
    period_start: datetime | None = None,
) -> RuleResult:
    """Construit un resultat de regle pour les tests."""
    return RuleResult(
        rule_code=code,
        status=status,
        description="Depassement apparent detecte sur la journee analysee.",
        measured_value=36000.0,
        allowed_value=32400.0,
        period_start=period_start,
        period_end=FIN if period_start else None,
        occurred_on=occurred_on,
        severity=severity,
        regulation_reference=SOURCE_FICTIVE,
    )


@pytest.fixture
def contexte(interval_factory: Callable[..., ActivityInterval]) -> RuleContext:
    """Contexte d'evaluation portant une journee de conduite."""
    return RuleContext(
        driver_id=1,
        intervals=(interval_factory(ActivityType.DRIVING, 7, 12),),
        period_start=JOUR,
        period_end=FIN,
        ruleset=empty_ruleset(),
    )


# --------------------------------------------------------------------------- #
# Registre vide
# --------------------------------------------------------------------------- #
def test_un_registre_vide_ne_produit_aucun_resultat(contexte: RuleContext) -> None:
    evaluation = evaluate_rules(contexte, registry=RuleRegistry())

    assert evaluation.results == ()
    assert evaluation.skipped == ()
    assert evaluation.rules_evaluated == 0


def test_un_registre_vide_le_dit_explicitement(contexte: RuleContext) -> None:
    evaluation = evaluate_rules(contexte, registry=RuleRegistry())

    message = evaluation.user_message()
    assert "aucune regle" in message.lower()
    assert "infraction" not in message.lower()


def test_la_version_du_jeu_de_regles_est_conservee(contexte: RuleContext) -> None:
    evaluation = evaluate_rules(contexte, registry=RuleRegistry())

    assert evaluation.ruleset_version == empty_ruleset().version


# --------------------------------------------------------------------------- #
# Seuil absent ou non confirme : la regle est ignoree
# --------------------------------------------------------------------------- #
def test_une_regle_dont_le_seuil_est_absent_est_ignoree(contexte: RuleContext) -> None:
    regle = RegleAvecSeuil([resultat()])

    evaluation = evaluate_rules(contexte, registry=RuleRegistry((regle,)))

    assert evaluation.results == ()
    assert regle.calls == 0
    assert [code for code, _ in evaluation.skipped] == ["TEST_AVEC_SEUIL"]


def test_une_regle_ignoree_explique_pourquoi(contexte: RuleContext) -> None:
    evaluation = evaluate_rules(contexte, registry=RuleRegistry((RegleAvecSeuil([resultat()]),)))

    _, raison = evaluation.skipped[0]
    assert "TEST_SEUIL" in raison


def test_un_seuil_non_confirme_n_est_jamais_applique(contexte: RuleContext) -> None:
    """Un parametre renseigne mais non verifie ne doit pas declencher d'evaluation."""
    ruleset = RuleSet(
        version="test-non-confirme",
        parameters={
            "TEST_SEUIL": RuleParameter(
                code="TEST_SEUIL",
                label="Seuil de test",
                value=1.0,
                source=SOURCE_FICTIVE,
                status=ConfirmationStatus.OPEN,
            )
        },
    )
    regle = RegleAvecSeuil([resultat()])

    evaluation = evaluate_rules(contexte, registry=RuleRegistry((regle,)), ruleset=ruleset)

    assert regle.calls == 0
    assert evaluation.results == ()
    assert "confirmee" in evaluation.skipped[0][1]


def test_un_seuil_confirme_permet_l_evaluation(contexte: RuleContext) -> None:
    ruleset = RuleSet(
        version="test-confirme",
        parameters={
            "TEST_SEUIL": RuleParameter(
                code="TEST_SEUIL",
                label="Seuil de test",
                value=1.0,
                source=SOURCE_FICTIVE,
                status=ConfirmationStatus.CONFIRMED,
            )
        },
    )
    regle = RegleAvecSeuil([resultat()])

    evaluation = evaluate_rules(contexte, registry=RuleRegistry((regle,)), ruleset=ruleset)

    assert regle.calls == 1
    assert evaluation.rules_evaluated == 1
    assert evaluation.ruleset_version == "test-confirme"


def test_une_regle_ignoree_n_empeche_pas_les_autres(contexte: RuleContext) -> None:
    sans_seuil = RegleAvecSeuil([resultat()])
    autonome = ReglePourTest([resultat(status=RuleStatus.OK)])

    evaluation = evaluate_rules(contexte, registry=RuleRegistry((sans_seuil, autonome)))

    assert autonome.calls == 1
    assert evaluation.rules_evaluated == 1
    assert len(evaluation.skipped) == 1


# --------------------------------------------------------------------------- #
# Agregation des resultats
# --------------------------------------------------------------------------- #
def test_les_resultats_sont_classes_par_statut(contexte: RuleContext) -> None:
    regle = ReglePourTest(
        [
            resultat(status=RuleStatus.OK),
            resultat(status=RuleStatus.WARNING),
            resultat(status=RuleStatus.VIOLATION),
            resultat(status=RuleStatus.NOT_APPLICABLE),
        ]
    )

    evaluation = evaluate_rules(contexte, registry=RuleRegistry((regle,)))

    assert evaluation.warnings_count == 1
    assert evaluation.violations_count == 1
    assert len(evaluation.results) == 4


def test_les_resultats_conformes_sont_conserves(contexte: RuleContext) -> None:
    """Les statuts OK restent presents : un rapport doit pouvoir attester du controle."""
    regle = ReglePourTest([resultat(status=RuleStatus.OK)])

    evaluation = evaluate_rules(contexte, registry=RuleRegistry((regle,)))

    assert len(evaluation.results) == 1
    assert evaluation.reportable == ()


def test_une_regle_non_evaluable_n_alarme_pas_l_utilisateur(
    contexte: RuleContext,
) -> None:
    """Donnees insuffisantes : le resultat est conserve, mais n'est pas une alerte."""
    regle = ReglePourTest([resultat(status=RuleStatus.NOT_APPLICABLE)])

    evaluation = evaluate_rules(contexte, registry=RuleRegistry((regle,)))

    assert len(evaluation.results) == 1
    assert evaluation.reportable == ()
    assert evaluation.results[0].status.label == "Non evaluable"


@pytest.mark.parametrize(
    ("nombre", "attendu"),
    [
        (0, "Aucune situation a verifier sur la periode analysee."),
        (1, "1 situation necessite une verification"),
        (3, "3 situations necessitent une verification"),
    ],
)
def test_le_message_de_synthese_reste_prudent(
    contexte: RuleContext, nombre: int, attendu: str
) -> None:
    regle = ReglePourTest(
        [resultat(status=RuleStatus.VIOLATION) for _ in range(nombre)]
        or [resultat(status=RuleStatus.OK)]
    )

    evaluation = evaluate_rules(contexte, registry=RuleRegistry((regle,)))

    assert evaluation.user_message() == attendu


def test_le_message_de_synthese_n_emploie_aucun_terme_juridique(
    contexte: RuleContext,
) -> None:
    regle = ReglePourTest([resultat(status=RuleStatus.VIOLATION)])

    message = evaluate_rules(contexte, registry=RuleRegistry((regle,))).user_message().lower()

    for terme in ("infraction", "delit", "sanction", "amende", "illegal"):
        assert terme not in message


# --------------------------------------------------------------------------- #
# Conversion en alertes enregistrables
# --------------------------------------------------------------------------- #
def test_les_alertes_reprennent_la_source_du_seuil(contexte: RuleContext) -> None:
    regle = ReglePourTest([resultat(occurred_on=date(2026, 9, 15))])

    evaluation = evaluate_rules(contexte, registry=RuleRegistry((regle,)))
    candidats = evaluation.to_candidates(driver_id=7, source_file_id=42)

    assert len(candidats) == 1
    candidat = candidats[0]
    assert candidat.driver_id == 7
    assert candidat.source_file_id == 42
    assert candidat.regulation_reference == SOURCE_FICTIVE
    assert candidat.occurred_on == date(2026, 9, 15)


def test_le_jour_est_deduit_de_la_periode_si_besoin(contexte: RuleContext) -> None:
    regle = ReglePourTest([resultat(occurred_on=None, period_start=JOUR)])

    candidats = evaluate_rules(contexte, registry=RuleRegistry((regle,))).to_candidates(driver_id=1)

    assert candidats[0].occurred_on == JOUR.date()


def test_un_resultat_sans_date_identifiable_est_ecarte(contexte: RuleContext) -> None:
    """Mieux vaut ne pas enregistrer une alerte que de lui inventer une date."""
    regle = ReglePourTest([resultat(occurred_on=None, period_start=None)])

    candidats = evaluate_rules(contexte, registry=RuleRegistry((regle,))).to_candidates(driver_id=1)

    assert candidats == ()


def test_seuls_les_resultats_a_signaler_deviennent_des_alertes(
    contexte: RuleContext,
) -> None:
    regle = ReglePourTest(
        [
            resultat(status=RuleStatus.OK, occurred_on=date(2026, 9, 15)),
            resultat(status=RuleStatus.VIOLATION, occurred_on=date(2026, 9, 15)),
        ]
    )

    candidats = evaluate_rules(contexte, registry=RuleRegistry((regle,))).to_candidates(driver_id=1)

    assert len(candidats) == 1
    assert candidats[0].status is RuleStatus.VIOLATION


def test_une_alerte_n_est_jamais_consideree_comme_verifiee(contexte: RuleContext) -> None:
    """Le moteur produit des candidats : il ne valide ni ne classe aucune situation."""
    regle = ReglePourTest([resultat(occurred_on=date(2026, 9, 15))])

    candidat = evaluate_rules(contexte, registry=RuleRegistry((regle,))).to_candidates(driver_id=1)[
        0
    ]

    assert candidat.status is RuleStatus.VIOLATION
    assert candidat.status.label == "Depassement apparent"


# --------------------------------------------------------------------------- #
# Garde-fous
# --------------------------------------------------------------------------- #
def test_un_jeu_de_regles_invalide_est_refuse(contexte: RuleContext) -> None:
    with pytest.raises(TypeError):
        evaluate_rules(contexte, registry=RuleRegistry(), ruleset="pas un jeu de regles")  # type: ignore[arg-type]


def test_l_evaluation_vide_par_defaut_est_exploitable() -> None:
    evaluation = RuleEvaluation(results=())

    assert evaluation.reportable == ()
    assert evaluation.warnings_count == 0
    assert evaluation.to_candidates(driver_id=1) == ()
