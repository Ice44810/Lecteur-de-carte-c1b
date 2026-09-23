"""Contrat du moteur de regles.

Separation stricte exigee par le cahier des charges : les **calculs** sont dans
``app.analysis`` (mesure), les **regles reglementaires** sont ici (jugement). Une
regle ne recalcule rien elle-meme : elle consomme les fonctions de mesure et compare
le resultat a un seuil configure.

Garde-fou structurel : :class:`Rule` refuse toute sous-classe qui ne declare pas de
reference reglementaire. Il est donc techniquement impossible d'ajouter une regle
sans citer sa source, conformement a la consigne « ne jamais hardcoder des regles
sans source ».
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.analysis.models import ActivityInterval
from app.core.enums import RuleStatus, Severity
from app.core.exceptions import RuleConfigurationError
from app.core.timeutils import format_duration

__all__ = ["RuleContext", "RuleResult", "Rule"]


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Donnees fournies a une regle pour son evaluation.

    Attributes:
        driver_id: Conducteur analyse.
        intervals: Intervalles d'activite normalises couvrant la periode.
        period_start: Debut de la periode analysee (UTC, inclus).
        period_end: Fin de la periode analysee (UTC, exclu).
        ruleset: Jeu de parametres a appliquer.
        metadata: Informations complementaires (identifiant de fichier source...).
    """

    driver_id: int
    intervals: tuple[ActivityInterval, ...]
    period_start: datetime
    period_end: datetime
    ruleset: Any
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def source_file_id(self) -> int | None:
        """Identifiant du fichier source, s'il a ete transmis."""
        value = self.metadata.get("source_file_id")
        return int(value) if isinstance(value, int) else None


@dataclass(frozen=True, slots=True)
class RuleResult:
    """Resultat structure de l'evaluation d'une regle.

    Correspond au contrat decrit en section 12 du cahier des charges, enrichi des
    informations necessaires a la tracabilite : unite des valeurs, criticite interne
    et reference reglementaire.

    Attributes:
        rule_code: Code stable de la regle.
        status: Resultat de l'evaluation.
        description: Formulation prudente destinee a l'utilisateur.
        measured_value: Valeur mesuree.
        allowed_value: Seuil configure applique.
        unit: Unite des deux valeurs ci-dessus.
        period_start: Debut de la periode concernee.
        period_end: Fin de la periode concernee.
        occurred_on: Jour de service concerne.
        severity: Criticite interne, pour le tri.
        regulation_reference: Source du seuil applique.
        activity_id: Activite precise concernee, si identifiable.
    """

    rule_code: str
    status: RuleStatus
    description: str
    measured_value: float | None = None
    allowed_value: float | None = None
    unit: str = "seconds"
    period_start: datetime | None = None
    period_end: datetime | None = None
    occurred_on: date | None = None
    severity: Severity = Severity.MEDIUM
    regulation_reference: str | None = None
    activity_id: int | None = None

    @property
    def is_reportable(self) -> bool:
        """Indique que ce resultat doit etre remonte a l'utilisateur."""
        return self.status.is_reportable

    @property
    def measured_label(self) -> str:
        """Valeur mesuree formatee selon son unite."""
        return self._format(self.measured_value)

    @property
    def allowed_label(self) -> str:
        """Seuil formate selon son unite."""
        return self._format(self.allowed_value)

    def _format(self, value: float | None) -> str:
        """Formate une valeur en tenant compte de l'unite."""
        if value is None:
            return "-"
        if self.unit == "seconds":
            return format_duration(int(value))
        return f"{value:g} {self.unit}"

    def as_dict(self) -> dict[str, Any]:
        """Retourne le resultat sous la forme documentee en section 12.

        Returns:
            Un dictionnaire serialisable, exploitable par les rapports et la future
            API REST.
        """
        return {
            "rule_code": self.rule_code,
            "status": self.status.value,
            "measured_value": self.measured_value,
            "allowed_value": self.allowed_value,
            "unit": self.unit,
            "description": self.description,
            "period": {
                "start": self.period_start.isoformat() if self.period_start else None,
                "end": self.period_end.isoformat() if self.period_end else None,
            },
            "occurred_on": self.occurred_on.isoformat() if self.occurred_on else None,
            "severity": self.severity.value,
            "regulation_reference": self.regulation_reference,
        }


class Rule(ABC):
    """Regle evaluable sur une periode d'activite.

    Toute sous-classe concrete doit declarer :

    * ``code`` : identifiant stable, utilise en base et dans les rapports ;
    * ``title`` : libelle affichable ;
    * ``regulation_reference`` : source du seuil applique (obligatoire) ;
    * ``parameter_codes`` : parametres du jeu de regles necessaires a l'evaluation.

    Raises:
        RuleConfigurationError: Une sous-classe concrete omet l'un de ces attributs.
    """

    code: str = ""
    title: str = ""
    regulation_reference: str = ""
    parameter_codes: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Verifie qu'une regle concrete est correctement declaree et sourcee."""
        super().__init_subclass__(**kwargs)
        if getattr(cls, "__abstractmethods__", None):
            return
        if not cls.code:
            raise RuleConfigurationError(
                "Une regle doit declarer un code.",
                cause=f"La classe {cls.__name__} ne definit pas d'attribut 'code'.",
                action="Ajoutez un code stable a cette regle.",
            )
        if not cls.title:
            raise RuleConfigurationError(
                "Une regle doit declarer un libelle.",
                cause=f"La classe {cls.__name__} ne definit pas d'attribut 'title'.",
                action="Ajoutez un libelle affichable a cette regle.",
            )
        if not cls.regulation_reference:
            raise RuleConfigurationError(
                "Une regle doit citer sa source reglementaire.",
                cause=(
                    f"La classe {cls.__name__} ne definit pas d'attribut "
                    "'regulation_reference'."
                ),
                action=(
                    "Renseignez la reference precise (texte, article) du seuil applique. "
                    "Aucune regle ne peut etre activee sans source verifiable."
                ),
            )

    @abstractmethod
    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        """Evalue la regle sur la periode fournie.

        Une regle retourne une liste : elle peut produire un resultat par journee,
        par semaine ou par bloc de conduite selon sa nature.

        Args:
            context: Donnees et parametres de l'evaluation.

        Returns:
            Les resultats produits, y compris ceux de statut ``OK``, afin que le
            rapport puisse attester des controles effectues.
        """

    def __repr__(self) -> str:
        """Representation technique courte."""
        return f"<{type(self).__name__} code={self.code!r}>"
