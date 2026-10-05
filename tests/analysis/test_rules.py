"""Tests du cadre du moteur de regles.

Trois exigences du cahier des charges sont verifiees ici :

* **aucune regle sans source** : une regle depourvue de reference reglementaire doit
  etre impossible a declarer et impossible a enregistrer ;
* **aucun seuil non verifie applique** : un parametre dont la valeur n'a pas ete
  confirmee face a sa source ne doit jamais servir a une evaluation ;
* **aucun seuil livre par defaut** : le jeu de regles distribue est vide.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.analysis.rules.base import Rule, RuleContext, RuleResult
from app.analysis.rules.catalogue import REGULATION_SOURCES, RULE_CATALOGUE, planned_rule
from app.analysis.rules.config import (
    RuleParameter,
    RuleSet,
    empty_ruleset,
    load_ruleset,
    save_ruleset,
)
from app.analysis.rules.registry import RuleRegistry, default_registry
from app.core.enums import RuleStatus, Severity
from app.core.exceptions import RuleConfigurationError
from app.parser.specification import ConfirmationStatus

SOURCE_VALIDE = "Reglement (CE) no 561/2006, article 6, paragraphe 1 - verifie le 15/09/2026"


# --------------------------------------------------------------------------- #
# Jeu de regles livre
# --------------------------------------------------------------------------- #
def test_le_jeu_de_regles_livre_est_vide() -> None:
    """Aucun seuil reglementaire n'est distribue sans verification prealable."""
    ruleset = empty_ruleset()

    assert ruleset.parameters == {}
    assert ruleset.is_empty is True
    assert ruleset.version == "0.0.0-empty"


def test_le_registre_livre_est_vide() -> None:
    registre = default_registry()

    assert registre.is_empty is True
    assert len(registre) == 0


# --------------------------------------------------------------------------- #
# Parametres
# --------------------------------------------------------------------------- #
def test_un_parametre_sans_source_est_refuse() -> None:
    with pytest.raises(ValueError):
        RuleParameter(code="X", label="Seuil sans source", value=1, source="")


def test_une_source_trop_courte_est_refusee() -> None:
    with pytest.raises(ValueError):
        RuleParameter(code="X", label="Seuil", value=1, source="561/2006")


def test_un_parametre_non_confirme_n_est_pas_utilisable() -> None:
    parametre = RuleParameter(code="X", label="Seuil", value=1, source=SOURCE_VALIDE)

    assert parametre.status is ConfirmationStatus.OPEN
    assert parametre.is_usable is False


def test_le_code_est_normalise_en_majuscules() -> None:
    assert RuleParameter(code="seuil_x", label="Seuil", value=1, source=SOURCE_VALIDE).code == (
        "SEUIL_X"
    )


def test_require_refuse_un_parametre_absent() -> None:
    with pytest.raises(RuleConfigurationError) as exc_info:
        empty_ruleset().require("DAILY_DRIVING_MAX_SECONDS")

    message, cause, action = exc_info.value.user_report()
    assert "DAILY_DRIVING_MAX_SECONDS" in cause
    assert "reference" in action
    assert message


def test_require_refuse_un_parametre_non_confirme() -> None:
    ruleset = RuleSet(
        version="1.0.0-essai",
        parameters={
            "SEUIL": RuleParameter(
                code="SEUIL", label="Seuil d'essai", value=3600, source=SOURCE_VALIDE
            )
        },
    )

    with pytest.raises(RuleConfigurationError) as exc_info:
        ruleset.require("SEUIL")

    assert "confirmee" in exc_info.value.cause


def test_require_accepte_un_parametre_confirme() -> None:
    ruleset = RuleSet(
        parameters={
            "SEUIL": RuleParameter(
                code="SEUIL",
                label="Seuil d'essai",
                value=3600,
                source=SOURCE_VALIDE,
                status=ConfirmationStatus.CONFIRMED,
            )
        }
    )

    assert ruleset.require("SEUIL").value == 3600
    assert ruleset.seconds("SEUIL") == 3600
    assert ruleset.is_empty is False


def test_une_unite_incoherente_est_refusee() -> None:
    ruleset = RuleSet(
        parameters={
            "SEUIL": RuleParameter(
                code="SEUIL",
                label="Seuil en kilometres",
                value=90,
                unit="km",
                source=SOURCE_VALIDE,
                status=ConfirmationStatus.CONFIRMED,
            )
        }
    )

    with pytest.raises(RuleConfigurationError) as exc_info:
        ruleset.seconds("SEUIL")

    assert "duree" in exc_info.value.message.lower()


def test_cle_incoherente_avec_le_code_refusee() -> None:
    with pytest.raises(ValueError):
        RuleSet(
            parameters={
                "AUTRE": RuleParameter(code="SEUIL", label="Seuil", value=1, source=SOURCE_VALIDE)
            }
        )


# --------------------------------------------------------------------------- #
# Chargement / enregistrement
# --------------------------------------------------------------------------- #
def test_fichier_absent_donne_un_jeu_vide(tmp_path: Path) -> None:
    assert load_ruleset(tmp_path / "rules.json").is_empty


def test_aller_retour_sur_disque(tmp_path: Path) -> None:
    chemin = tmp_path / "rules.json"
    ruleset = RuleSet(
        version="1.0.0-essai",
        parameters={
            "SEUIL": RuleParameter(
                code="SEUIL",
                label="Seuil d'essai",
                value=32_400,
                source=SOURCE_VALIDE,
                status=ConfirmationStatus.CONFIRMED,
            )
        },
    )

    save_ruleset(ruleset, chemin)

    recharge = load_ruleset(chemin)
    assert recharge.version == "1.0.0-essai"
    assert recharge.seconds("SEUIL") == 32_400


def test_fichier_invalide_explique_le_probleme(tmp_path: Path) -> None:
    chemin = tmp_path / "rules.json"
    chemin.write_text("{ ceci n'est pas du JSON", encoding="utf-8")

    with pytest.raises(RuleConfigurationError) as exc_info:
        load_ruleset(chemin)

    assert "JSON" in exc_info.value.cause


def test_parametre_sans_source_dans_le_fichier_refuse(tmp_path: Path) -> None:
    chemin = tmp_path / "rules.json"
    chemin.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "parameters": {
                    "SEUIL": {"code": "SEUIL", "label": "Seuil", "value": 1, "source": ""}
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuleConfigurationError) as exc_info:
        load_ruleset(chemin)

    assert "source" in exc_info.value.cause


# --------------------------------------------------------------------------- #
# Declaration des regles
# --------------------------------------------------------------------------- #
def test_une_regle_sans_source_est_impossible_a_declarer() -> None:
    with pytest.raises(RuleConfigurationError) as exc_info:

        class RegleSansSource(Rule):
            code = "SANS_SOURCE"
            title = "Regle sans source"

            def evaluate(self, context: RuleContext) -> list[RuleResult]:
                return []

    assert "source" in exc_info.value.message.lower()
    assert "verifiable" in exc_info.value.action


def test_une_regle_sans_code_est_refusee() -> None:
    with pytest.raises(RuleConfigurationError):

        class RegleSansCode(Rule):
            title = "Regle sans code"
            regulation_reference = SOURCE_VALIDE

            def evaluate(self, context: RuleContext) -> list[RuleResult]:
                return []


def test_une_regle_sans_libelle_est_refusee() -> None:
    with pytest.raises(RuleConfigurationError):

        class RegleSansLibelle(Rule):
            code = "SANS_LIBELLE"
            regulation_reference = SOURCE_VALIDE

            def evaluate(self, context: RuleContext) -> list[RuleResult]:
                return []


def test_une_regle_complete_est_acceptee() -> None:
    class RegleComplete(Rule):
        code = "COMPLETE"
        title = "Regle complete"
        regulation_reference = SOURCE_VALIDE

        def evaluate(self, context: RuleContext) -> list[RuleResult]:
            return []

    assert RegleComplete().code == "COMPLETE"
    assert "COMPLETE" in repr(RegleComplete())


# --------------------------------------------------------------------------- #
# Registre
# --------------------------------------------------------------------------- #
class _RegleEssai(Rule):
    code = "ESSAI"
    title = "Regle d'essai"
    regulation_reference = SOURCE_VALIDE
    parameter_codes = ("SEUIL",)

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        return [
            RuleResult(
                rule_code=self.code,
                status=RuleStatus.OK,
                description="Controle effectue.",
                regulation_reference=self.regulation_reference,
                period_start=context.period_start,
                period_end=context.period_end,
            )
        ]


def test_enregistrement_et_lecture() -> None:
    registre = RuleRegistry((_RegleEssai(),))

    assert registre.codes == ("ESSAI",)
    assert "ESSAI" in registre
    assert registre.get("ESSAI") is not None
    assert len(registre.all()) == 1


def test_code_en_doublon_refuse() -> None:
    registre = RuleRegistry((_RegleEssai(),))

    with pytest.raises(RuleConfigurationError) as exc_info:
        registre.register(_RegleEssai())

    assert "meme code" in exc_info.value.message.lower()


def test_une_regle_privee_de_source_ne_peut_pas_etre_activee() -> None:
    regle = _RegleEssai()
    regle.regulation_reference = ""  # contournement volontaire

    with pytest.raises(RuleConfigurationError) as exc_info:
        RuleRegistry().register(regle)

    assert "sans source" in exc_info.value.message.lower()


def test_retrait_d_une_regle() -> None:
    registre = RuleRegistry((_RegleEssai(),))

    registre.unregister("ESSAI")

    assert registre.is_empty


# --------------------------------------------------------------------------- #
# Resultats
# --------------------------------------------------------------------------- #
def test_le_resultat_expose_le_contrat_documente() -> None:
    resultat = RuleResult(
        rule_code="DAILY_DRIVING_MAX",
        status=RuleStatus.VIOLATION,
        description="Depassement apparent du temps de conduite journalier.",
        measured_value=36_000,
        allowed_value=32_400,
        period_start=datetime(2026, 9, 15, tzinfo=UTC),
        period_end=datetime(2026, 9, 16, tzinfo=UTC),
        severity=Severity.MEDIUM,
        regulation_reference=SOURCE_VALIDE,
    )

    donnees = resultat.as_dict()

    assert donnees["rule_code"] == "DAILY_DRIVING_MAX"
    assert donnees["status"] == "VIOLATION"
    assert donnees["measured_value"] == 36_000
    assert donnees["allowed_value"] == 32_400
    assert donnees["regulation_reference"] == SOURCE_VALIDE
    assert donnees["period"]["start"].startswith("2026-09-15")


def test_les_durees_sont_formatees_selon_l_unite() -> None:
    resultat = RuleResult(
        rule_code="X",
        status=RuleStatus.WARNING,
        description="Situation a verifier.",
        measured_value=36_000,
        allowed_value=32_400,
    )

    assert resultat.measured_label == "10h00"
    assert resultat.allowed_label == "09h00"


def test_une_valeur_non_horaire_conserve_son_unite() -> None:
    resultat = RuleResult(
        rule_code="X",
        status=RuleStatus.OK,
        description="Controle.",
        measured_value=3,
        unit="count",
    )

    assert resultat.measured_label == "3 count"
    assert resultat.allowed_label == "-"


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #
def test_le_catalogue_documente_les_regles_prevues() -> None:
    assert RULE_CATALOGUE
    codes = [regle.code for regle in RULE_CATALOGUE]
    assert len(codes) == len(set(codes))


@pytest.mark.parametrize("regle", RULE_CATALOGUE, ids=lambda item: item.code)
def test_chaque_regle_prevue_cite_un_texte_a_verifier(regle) -> None:
    assert regle.reference_to_verify.strip()
    assert regle.description.strip()
    assert regle.status is not ConfirmationStatus.CONFIRMED


def test_les_regles_essentielles_sont_prevues() -> None:
    codes = {regle.code for regle in RULE_CATALOGUE}

    assert {
        "DAILY_DRIVING_MAX",
        "WEEKLY_DRIVING_MAX",
        "CONTINUOUS_DRIVING_BREAK",
        "DAILY_REST_MINIMUM",
        "WEEKLY_REST_MINIMUM",
    } <= codes


def test_les_textes_de_reference_sont_cites() -> None:
    texte = " ".join(REGULATION_SOURCES)

    assert "561/2006" in texte
    assert "2020/1054" in texte
    assert "2002/15/CE" in texte
    assert "165/2014" in texte


def test_recherche_dans_le_catalogue() -> None:
    assert planned_rule("daily_driving_max") is not None
    assert planned_rule("REGLE_INEXISTANTE") is None


def test_le_contexte_expose_le_fichier_source() -> None:
    contexte = RuleContext(
        driver_id=1,
        intervals=(),
        period_start=datetime(2026, 9, 15, tzinfo=UTC),
        period_end=datetime(2026, 9, 16, tzinfo=UTC),
        ruleset=empty_ruleset(),
        metadata={"source_file_id": 7},
    )

    assert contexte.source_file_id == 7
