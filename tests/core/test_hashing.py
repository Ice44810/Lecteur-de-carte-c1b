"""Tests du calcul d'empreinte SHA-256.

L'empreinte est la cle de deduplication des imports (section 22 du cahier des
charges) : elle doit etre stable, minuscule, et ne jamais modifier le fichier lu.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.core.exceptions import StorageError
from app.core.hashing import sha256_bytes, sha256_file


def test_sha256_bytes_correspond_a_la_reference() -> None:
    payload = b"contenu de test"
    assert sha256_bytes(payload) == hashlib.sha256(payload).hexdigest()


def test_sha256_file_correspond_au_contenu(tmp_path: Path) -> None:
    path = tmp_path / "donnees.C1B"
    payload = bytes(range(256)) * 10
    path.write_bytes(payload)

    assert sha256_file(path) == hashlib.sha256(payload).hexdigest()


def test_sha256_file_est_en_minuscules_sur_64_caracteres(opaque_c1b_file: Path) -> None:
    digest = sha256_file(opaque_c1b_file)
    assert len(digest) == 64
    assert digest == digest.lower()


def test_sha256_file_ne_modifie_pas_le_fichier(opaque_c1b_file: Path) -> None:
    """Exigence absolue : un fichier original n'est jamais modifie."""
    before = opaque_c1b_file.read_bytes()
    stat_before = opaque_c1b_file.stat()

    sha256_file(opaque_c1b_file)

    assert opaque_c1b_file.read_bytes() == before
    assert opaque_c1b_file.stat().st_mtime == stat_before.st_mtime


def test_sha256_file_fichier_vide(empty_c1b_file: Path) -> None:
    assert sha256_file(empty_c1b_file) == hashlib.sha256(b"").hexdigest()


def test_sha256_file_fichier_absent_leve_une_erreur_exploitable(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as exc_info:
        sha256_file(tmp_path / "absent.C1B")

    message, cause, action = exc_info.value.user_report()
    assert message and cause and action


def test_sha256_file_chunks_de_taille_variable(tmp_path: Path) -> None:
    """Le decoupage en blocs ne doit pas influer sur le resultat."""
    path = tmp_path / "gros.C1B"
    payload = bytes(range(256)) * 100
    path.write_bytes(payload)

    assert sha256_file(path, chunk_size=7) == sha256_file(path, chunk_size=4096)
