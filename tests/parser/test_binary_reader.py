"""Tests du lecteur binaire bas niveau.

Ce module ne contient aucun offset tachygraphique : il peut donc etre teste
exhaustivement sans fichier reel.
"""

from __future__ import annotations

import pytest

from app.parser.binary_reader import BinaryReader, BinaryReaderError, InsufficientDataError


def test_position_et_restant() -> None:
    reader = BinaryReader(b"\x01\x02\x03\x04")

    assert reader.size == 4
    assert reader.position == 0
    assert reader.remaining == 4

    reader.read_bytes(3)

    assert reader.position == 3
    assert reader.remaining == 1
    assert reader.at_end is False

    reader.read_bytes(1)

    assert reader.at_end is True


def test_lecture_au_dela_de_la_fin_signale_un_fichier_incomplet() -> None:
    reader = BinaryReader(b"\x01\x02")

    with pytest.raises(InsufficientDataError) as exc_info:
        reader.read_bytes(3)

    message, cause, action = exc_info.value.user_report()
    assert "incomplet" in message.lower()
    assert "conserve" in action
    assert cause
    assert exc_info.value.position == 0


def test_peek_ne_deplace_pas_le_curseur() -> None:
    reader = BinaryReader(b"\x01\x02\x03")

    assert reader.peek(2) == b"\x01\x02"
    assert reader.position == 0


def test_peek_tolere_la_fin_du_tampon() -> None:
    reader = BinaryReader(b"\x01")

    assert reader.peek(10) == b"\x01"


def test_at_restaure_la_position() -> None:
    reader = BinaryReader(b"\x00\x11\x22\x33")
    reader.seek(1)

    with reader.at(3) as temporaire:
        assert temporaire.read_bytes(1) == b"\x33"

    assert reader.position == 1


def test_seek_hors_bornes_refuse() -> None:
    reader = BinaryReader(b"\x01")

    with pytest.raises(BinaryReaderError):
        reader.seek(5)


def test_skip_negatif_refuse() -> None:
    reader = BinaryReader(b"\x01\x02")

    with pytest.raises(ValueError, match="seek"):
        reader.skip(-1)


@pytest.mark.parametrize(
    ("octets", "ordre", "attendu"),
    [
        (b"\x01\x00", "big", 256),
        (b"\x01\x00", "little", 1),
        (b"\xff\xff", "big", 65535),
    ],
)
def test_lecture_entiers_non_signes(octets: bytes, ordre: str, attendu: int) -> None:
    reader = BinaryReader(octets)

    assert reader.read_uint(len(octets), byte_order=ordre) == attendu  # type: ignore[arg-type]


def test_lecture_entier_signe() -> None:
    assert BinaryReader(b"\xff").read_int(1) == -1


def test_lecture_entiers_de_largeur_fixe() -> None:
    reader = BinaryReader(b"\x01\x00\x02\x00\x00\x03\x00\x00\x00\x04")

    assert reader.read_uint8() == 1
    assert reader.read_uint16() == 2
    assert reader.read_uint24() == 3
    assert reader.read_uint32() == 4


def test_largeur_d_entier_invalide_refusee() -> None:
    reader = BinaryReader(b"\x00" * 16)

    with pytest.raises(ValueError):
        reader.read_uint(0)
    with pytest.raises(ValueError):
        reader.read_uint(9)


def test_lecture_de_chaine_supprime_le_remplissage() -> None:
    reader = BinaryReader(b"DURAND\x00\x00\xff")

    assert reader.read_string(9) == "DURAND"


def test_lecture_de_chaine_conserve_le_remplissage_si_demande() -> None:
    reader = BinaryReader(b"AB\x00")

    assert reader.read_string(3, strip_padding=False) == "AB\x00"


def test_un_octet_indecodable_ne_fait_pas_echouer_la_lecture() -> None:
    """Un champ texte abime ne doit pas empecher l'exploitation du reste du fichier."""
    reader = BinaryReader(b"\x81\x82AB")

    assert reader.read_string(4, encoding="utf-8")


def test_lecture_hexadecimale() -> None:
    assert BinaryReader(b"\xab\xcd").read_hex(2) == "abcd"


def test_lecture_bcd() -> None:
    assert BinaryReader(b"\x20\x26\x09\x23").read_bcd(4) == "20260923"


def test_bcd_invalide_signale_la_position() -> None:
    reader = BinaryReader(b"\x20\x2f")

    with pytest.raises(BinaryReaderError) as exc_info:
        reader.read_bcd(2)

    assert exc_info.value.position == 1
    assert "invalide" in exc_info.value.message.lower()


def test_le_lecteur_ne_modifie_pas_les_donnees_fournies() -> None:
    source = bytearray(b"\x01\x02\x03")
    reader = BinaryReader(bytes(source))
    reader.read_remaining()

    assert source == bytearray(b"\x01\x02\x03")


def test_offset_initial_hors_bornes_refuse() -> None:
    with pytest.raises(ValueError):
        BinaryReader(b"\x01", offset=2)


def test_type_non_binaire_refuse() -> None:
    with pytest.raises(TypeError):
        BinaryReader("texte")  # type: ignore[arg-type]


def test_repr_ne_contient_pas_le_contenu() -> None:
    representation = repr(BinaryReader(b"DURAND"))

    assert "DURAND" not in representation
    assert "size=6" in representation
