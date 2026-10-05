"""Calcul d'empreintes SHA-256 (integrite des fichiers tachygraphiques).

L'empreinte sert a deux usages distincts :

* garantir l'integrite du fichier original archive (section 17 du cahier des charges) ;
* detecter les doublons a l'import (section 22).

La lecture se fait par blocs afin de supporter des fichiers volumineux sans les
charger entierement en memoire.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.exceptions import StorageError

__all__ = ["DEFAULT_CHUNK_SIZE", "sha256_bytes", "sha256_file"]

DEFAULT_CHUNK_SIZE = 1024 * 1024
"""Taille de bloc de lecture, en octets."""


def sha256_bytes(payload: bytes) -> str:
    """Retourne l'empreinte SHA-256 hexadecimale (minuscules) d'un bloc d'octets."""
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path | str, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """Retourne l'empreinte SHA-256 hexadecimale d'un fichier.

    Args:
        path: Chemin du fichier a hacher.
        chunk_size: Taille des blocs de lecture, en octets.

    Returns:
        L'empreinte hexadecimale en minuscules (64 caracteres).

    Raises:
        StorageError: Le fichier est absent ou illisible.
        ValueError: ``chunk_size`` n'est pas strictement positif.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size doit etre strictement positif")

    file_path = Path(path)
    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
    except FileNotFoundError as exc:
        raise StorageError(
            f"Le fichier {file_path.name} est introuvable.",
            cause="Le fichier a peut-etre ete deplace ou supprime depuis sa selection.",
            action="Selectionnez a nouveau le fichier.",
            technical_detail=str(exc),
        ) from exc
    except IsADirectoryError as exc:
        raise StorageError(
            f"{file_path.name} est un repertoire, pas un fichier.",
            cause="Un repertoire a ete selectionne au lieu d'un fichier.",
            action="Selectionnez un fichier .C1B ou .V1B.",
            technical_detail=str(exc),
        ) from exc
    except OSError as exc:
        raise StorageError(
            f"Le fichier {file_path.name} n'a pas pu etre lu.",
            cause="Les droits d'acces sont insuffisants ou le support est indisponible.",
            action="Verifiez les permissions du fichier puis reessayez.",
            technical_detail=str(exc),
        ) from exc
    return digest.hexdigest()
