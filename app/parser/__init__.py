"""Decodage des fichiers tachygraphiques (DONNEE BRUTE -> DONNEE DECODEE).

Le paquet expose une fabrique, :func:`get_parser_for`, afin que le service d'import
n'ait jamais a connaitre les classes concretes : ajouter la prise en charge d'un
nouveau format se limitera a etendre :data:`PARSERS`.
"""

from app.core.enums import FileType
from app.core.exceptions import UnsupportedFileTypeError
from app.parser.base import TachographFileParser
from app.parser.binary_reader import BinaryReader, BinaryReaderError, InsufficientDataError
from app.parser.c1b_parser import C1BParser
from app.parser.models import ParseResult
from app.parser.v1b_parser import V1BParser

__all__ = [
    "BinaryReader",
    "BinaryReaderError",
    "C1BParser",
    "InsufficientDataError",
    "PARSERS",
    "ParseResult",
    "TachographFileParser",
    "V1BParser",
    "detect_file_type",
    "get_parser_for",
]

PARSERS: dict[FileType, type[TachographFileParser]] = {
    FileType.C1B: C1BParser,
    FileType.V1B: V1BParser,
}
"""Table de correspondance entre type de fichier et parser."""


def detect_file_type(filename: str) -> FileType:
    """Determine le type de fichier a partir de son extension.

    La detection repose sur l'extension du nom de fichier, seule information fiable
    disponible avant decodage : aucune signature de contenu n'a ete confirmee a ce
    stade (voir ``C1B_CONTAINER_LAYOUT`` dans :mod:`app.parser.specification`).

    Args:
        filename: Nom du fichier, avec son extension.

    Returns:
        Le type de fichier correspondant.

    Raises:
        UnsupportedFileTypeError: L'extension n'est ni ``.C1B`` ni ``.V1B``.
    """
    suffix = filename.rsplit(".", 1)[-1].upper() if "." in filename else ""
    for file_type in FileType:
        if suffix == file_type.value:
            return file_type
    raise UnsupportedFileTypeError(
        f"Le fichier « {filename} » n'est pas un fichier tachygraphique reconnu.",
        technical_detail=f"extension detectee : '{suffix or 'aucune'}'",
    )


def get_parser_for(file_type: FileType) -> type[TachographFileParser]:
    """Retourne la classe de parser associee a un type de fichier.

    Args:
        file_type: Type de fichier a decoder.

    Returns:
        La classe de parser correspondante.

    Raises:
        UnsupportedFileTypeError: Aucun parser n'est enregistre pour ce type.
    """
    try:
        return PARSERS[file_type]
    except KeyError as exc:  # pragma: no cover - garde-fou
        raise UnsupportedFileTypeError(
            f"Aucun decodeur n'est disponible pour le type {file_type.value}.",
            technical_detail=f"types pris en charge : {sorted(item.value for item in PARSERS)}",
        ) from exc
