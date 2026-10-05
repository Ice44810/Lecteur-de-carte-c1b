"""Tests de la journalisation.

Exigence de la section 21 du cahier des charges : ne jamais journaliser inutilement
des donnees personnelles sensibles. Le numero de carte doit toujours etre masque.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.config.logging_config import configure_logging, get_logger, mask_card_number
from app.config.settings import Settings


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        ("F1234567890123456", "*************3456"),
        ("1234", "1234"),
        ("", "<absent>"),
        (None, "<absent>"),
    ],
)
def test_mask_card_number(valeur: str | None, attendu: str) -> None:
    assert mask_card_number(valeur) == attendu


def test_le_numero_de_carte_masque_ne_revele_que_la_fin() -> None:
    numero = "F9876543210001234"
    masque = mask_card_number(numero)

    assert numero not in masque
    assert masque.endswith(numero[-4:])
    assert len(masque) == len(numero)


def test_configure_logging_ecrit_dans_le_fichier_attendu(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", log_dir=tmp_path / "logs", log_level="DEBUG")
    settings.ensure_directories()

    configure_logging(settings, force=True)
    get_logger("app.tests").info("message de controle")
    logging.getLogger("app").handlers[0].flush()

    contenu = settings.log_path.read_text(encoding="utf-8")
    assert "message de controle" in contenu


def test_configure_logging_tolere_un_repertoire_inaccessible(tmp_path: Path) -> None:
    """Une journalisation fichier impossible ne doit pas empecher l'application."""
    obstacle = tmp_path / "fichier"
    obstacle.write_text("occupe", encoding="utf-8")
    settings = Settings(data_dir=tmp_path / "data", log_dir=obstacle / "logs")

    logger = configure_logging(settings, force=True)

    assert logger.handlers


def test_get_logger_rattache_a_la_hierarchie_applicative() -> None:
    assert get_logger("app.services.import_service").name == "app.services.import_service"
    assert get_logger("mon_module").name == "app.mon_module"


def test_les_journaux_ne_remontent_pas_au_logger_racine(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", log_dir=tmp_path / "logs")

    logger = configure_logging(settings, force=True)

    assert logger.propagate is False
