"""Registre des regles actives.

Le registre decouple le moteur d'analyse des regles concretes : ajouter une regle en
phase 7 consistera a l'enregistrer ici, sans modifier ni le moteur, ni les services,
ni l'interface.

Le registre livre par defaut est **vide** : aucune regle n'est active tant que son
seuil n'a pas ete verifie contre son texte de reference (voir
:mod:`app.analysis.rules.catalogue`).
"""

from __future__ import annotations

from collections.abc import Iterator

from app.analysis.rules.base import Rule
from app.config.logging_config import get_logger
from app.core.exceptions import RuleConfigurationError

__all__ = ["RuleRegistry", "default_registry"]

logger = get_logger(__name__)


class RuleRegistry:
    """Collection de regles indexees par code.

    Args:
        rules: Regles a enregistrer immediatement.
    """

    def __init__(self, rules: tuple[Rule, ...] = ()) -> None:
        self._rules: dict[str, Rule] = {}
        for rule in rules:
            self.register(rule)

    def register(self, rule: Rule) -> Rule:
        """Enregistre une regle.

        Args:
            rule: Instance de regle a activer.

        Returns:
            La regle enregistree.

        Raises:
            RuleConfigurationError: Une regle porte deja ce code, ou la regle ne cite
                pas de source reglementaire.
        """
        if not rule.regulation_reference:
            raise RuleConfigurationError(
                "Cette regle ne peut pas etre activee sans source.",
                cause=f"La regle « {rule.code or type(rule).__name__} » ne cite aucun texte.",
                action="Renseignez la reference reglementaire de la regle.",
            )
        if rule.code in self._rules:
            raise RuleConfigurationError(
                "Deux regles portent le meme code.",
                cause=f"Le code « {rule.code} » est deja enregistre.",
                action="Attribuez un code distinct a chaque regle.",
            )
        self._rules[rule.code] = rule
        logger.debug("Regle enregistree : %s", rule.code)
        return rule

    def unregister(self, code: str) -> None:
        """Retire une regle du registre.

        Args:
            code: Code de la regle a retirer.

        Raises:
            KeyError: Aucune regle ne porte ce code.
        """
        del self._rules[code]

    def get(self, code: str) -> Rule | None:
        """Retourne la regle portant ce code, ou ``None``."""
        return self._rules.get(code)

    @property
    def codes(self) -> tuple[str, ...]:
        """Codes des regles enregistrees, tries."""
        return tuple(sorted(self._rules))

    def all(self) -> tuple[Rule, ...]:
        """Retourne les regles enregistrees, triees par code."""
        return tuple(self._rules[code] for code in self.codes)

    @property
    def is_empty(self) -> bool:
        """Indique qu'aucune regle n'est active."""
        return not self._rules

    def __len__(self) -> int:
        """Nombre de regles enregistrees."""
        return len(self._rules)

    def __iter__(self) -> Iterator[Rule]:
        """Itere sur les regles, triees par code."""
        return iter(self.all())

    def __contains__(self, code: object) -> bool:
        """Indique si un code est enregistre."""
        return isinstance(code, str) and code in self._rules


def default_registry() -> RuleRegistry:
    """Retourne le registre livre par defaut.

    Returns:
        Un registre vide : aucune regle reglementaire n'est distribuee avant
        verification de sa source (voir :mod:`app.analysis.rules.catalogue`).
    """
    return RuleRegistry()
