"""Tests de la hierarchie d'exceptions.

Exigence de la section 19 du cahier des charges : toute erreur applicative porte un
message, une cause et une action. Ces tests verifient que la promesse tient pour
**toutes** les exceptions du domaine, y compris celles construites sans argument.
"""

from __future__ import annotations

import inspect

import pytest

from app.core import exceptions
from app.core.exceptions import (
    DuplicateFileError,
    PCSCUnavailableError,
    TachyError,
    UnconfirmedStructureError,
)


def _exception_classes() -> list[type[TachyError]]:
    """Retourne toutes les classes d'exception exposees par le module."""
    return [
        value
        for name in exceptions.__all__
        if inspect.isclass(value := getattr(exceptions, name)) and issubclass(value, TachyError)
    ]


@pytest.mark.parametrize("exception_class", _exception_classes(), ids=lambda cls: cls.__name__)
def test_toute_exception_fournit_message_cause_action(
    exception_class: type[TachyError],
) -> None:
    message, cause, action = exception_class().user_report()

    assert message.strip()
    assert cause.strip()
    assert action.strip()


@pytest.mark.parametrize("exception_class", _exception_classes(), ids=lambda cls: cls.__name__)
def test_aucune_exception_ne_contient_de_trace_python(
    exception_class: type[TachyError],
) -> None:
    """Le texte affiche a l'utilisateur ne doit pas ressembler a une trace."""
    message, cause, action = exception_class().user_report()

    for text in (message, cause, action):
        assert "Traceback" not in text
        assert '  File "' not in text


def test_message_personnalise_prime_sur_le_defaut() -> None:
    error = UnconfirmedStructureError("Structure C1B a confirmer.")

    assert error.message == "Structure C1B a confirmer."
    assert error.cause == UnconfirmedStructureError.default_cause


def test_detail_technique_est_separe_du_message() -> None:
    error = PCSCUnavailableError(technical_detail="libpcsclite absente")

    assert error.technical_detail == "libpcsclite absente"
    assert "libpcsclite" not in error.message


def test_duplicate_file_error_porte_l_import_existant() -> None:
    error = DuplicateFileError(existing_file_id=42, sha256="a" * 64)

    assert error.existing_file_id == 42
    assert error.sha256 == "a" * 64


def test_unconfirmed_structure_error_est_une_erreur_de_parsing() -> None:
    assert issubclass(UnconfirmedStructureError, exceptions.ParsingError)


def test_str_retourne_le_message_utilisateur() -> None:
    assert str(TachyError("Message court.")) == "Message court."
