"""Tests du registre des incertitudes de specification.

Ce registre est la traduction en code de la consigne « ne jamais inventer une
structure binaire ». Les tests ci-dessous en verifient l'integrite : chaque question
cite une reference, et une question confirmee doit l'etre en connaissance de cause.
"""

from __future__ import annotations

import pytest

from app.parser.specification import (
    OPEN_QUESTIONS,
    REFERENCE_DOCUMENTS,
    ConfirmationStatus,
    OpenQuestion,
    is_confirmed,
    questions_for,
    unconfirmed_topics,
)


def test_le_registre_n_est_pas_vide() -> None:
    assert OPEN_QUESTIONS


@pytest.mark.parametrize("question", OPEN_QUESTIONS, ids=lambda item: item.code)
def test_chaque_question_est_exploitable(question: OpenQuestion) -> None:
    assert question.code == question.code.upper()
    assert question.topic in {"c1b", "v1b", "card"}
    assert len(question.question) > 30
    assert question.reference.strip()


def test_les_codes_sont_uniques() -> None:
    codes = [question.code for question in OPEN_QUESTIONS]

    assert len(codes) == len(set(codes))


def test_chaque_domaine_est_couvert() -> None:
    for topic in ("c1b", "v1b", "card"):
        assert questions_for(topic)


def test_filtre_des_questions_bloquantes() -> None:
    bloquantes = questions_for("c1b", blocking_only=True)

    assert bloquantes
    assert all(question.blocking for question in bloquantes)
    assert len(bloquantes) < len(questions_for("c1b"))


def test_aucun_domaine_n_est_declare_confirme_sans_fichier_de_test() -> None:
    """Tant qu'aucun fichier reel n'a valide un decodage, rien ne peut etre confirme."""
    assert set(unconfirmed_topics()) == {"c1b", "v1b", "card"}
    assert is_confirmed("c1b") is False
    assert is_confirmed("v1b") is False
    assert is_confirmed("card") is False


def test_un_domaine_inconnu_est_considere_confirme_par_vacuite() -> None:
    """Aucune question ouverte sur un domaine inconnu : rien ne bloque, rien n'est promis."""
    assert is_confirmed("format-inexistant") is True


def test_les_documents_de_reference_sont_cites() -> None:
    assert REFERENCE_DOCUMENTS
    texte = " ".join(REFERENCE_DOCUMENTS)
    assert "2016/799" in texte
    assert "3821/85" in texte


def test_les_libelles_de_statut_sont_traduits() -> None:
    assert ConfirmationStatus.OPEN.label == "A confirmer"
    assert ConfirmationStatus.CONFIRMED.label == "Confirme"
