"""Lecture bas niveau de donnees binaires (DONNEE BRUTE).

Cette couche est **totalement agnostique** du format tachygraphique : elle ne
connait que des octets, des entiers et des chaines. Elle ne contient aucun offset
ni aucune structure propre au C1B ou au V1B, ce qui permet de la tester
exhaustivement sans disposer d'un fichier reel.

Convention d'ordre des octets : les entiers du dictionnaire de donnees
tachygraphique sont documentes en gros-boutiste (``big endian``, ordre reseau).
L'ordre reste neanmoins un parametre explicite de chaque lecture, afin qu'un champ
dont l'ordre n'aurait pas ete confirme ne soit jamais lu par defaut de maniere
implicite.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from app.core.exceptions import ParsingError

__all__ = [
    "BinaryReader",
    "BinaryReaderError",
    "InsufficientDataError",
    "ByteOrder",
]

ByteOrder = Literal["big", "little"]


class BinaryReaderError(ParsingError):
    """Erreur de lecture binaire, avec position dans le flux.

    Args:
        message: Description du probleme.
        position: Position du curseur au moment de l'erreur.
        **kwargs: Arguments transmis a :class:`~app.core.exceptions.ParsingError`.
    """

    def __init__(self, message: str, *, position: int | None = None, **kwargs: object) -> None:
        detail = kwargs.pop("technical_detail", None)
        super().__init__(
            message,
            cause=kwargs.pop("cause", None),  # type: ignore[arg-type]
            action=kwargs.pop("action", None),  # type: ignore[arg-type]
            technical_detail=detail,  # type: ignore[arg-type]
        )
        self.position = position


class InsufficientDataError(BinaryReaderError):
    """Le flux ne contient pas assez d'octets pour satisfaire la lecture."""

    default_message = "Le fichier est incomplet."
    default_cause = "La lecture a atteint la fin du fichier avant la fin d'une structure."
    default_action = (
        "Le fichier original est conserve. Verifiez que le telechargement "
        "s'est termine normalement, puis relancez l'import."
    )


class BinaryReader:
    """Curseur de lecture sequentielle sur un tampon d'octets.

    Le lecteur ne modifie jamais les donnees fournies : il ne fait que se
    deplacer et retourner des copies de tranches.

    Args:
        data: Contenu binaire a lire.
        offset: Position initiale du curseur.

    Raises:
        ValueError: ``offset`` est hors des bornes du tampon.
    """

    __slots__ = ("_data", "_position")

    def __init__(self, data: bytes, *, offset: int = 0) -> None:
        if not isinstance(data, bytes | bytearray | memoryview):
            raise TypeError("BinaryReader attend un objet d'octets")
        self._data = bytes(data)
        if not 0 <= offset <= len(self._data):
            raise ValueError(f"offset {offset} hors des bornes (taille {len(self._data)})")
        self._position = offset

    # ------------------------------------------------------------------ #
    # Etat du curseur
    # ------------------------------------------------------------------ #
    @property
    def size(self) -> int:
        """Taille totale du tampon, en octets."""
        return len(self._data)

    @property
    def position(self) -> int:
        """Position courante du curseur."""
        return self._position

    @property
    def remaining(self) -> int:
        """Nombre d'octets restant a lire."""
        return len(self._data) - self._position

    @property
    def at_end(self) -> bool:
        """Indique que le curseur a atteint la fin du tampon."""
        return self._position >= len(self._data)

    def tell(self) -> int:
        """Retourne la position courante (interface familiere de type fichier)."""
        return self._position

    def seek(self, position: int) -> None:
        """Positionne le curseur a une position absolue.

        Args:
            position: Position visee, comprise entre 0 et la taille du tampon.

        Raises:
            BinaryReaderError: La position est hors des bornes.
        """
        if not 0 <= position <= len(self._data):
            raise BinaryReaderError(
                "Position de lecture invalide.",
                position=self._position,
                technical_detail=f"seek({position}) hors des bornes (taille {len(self._data)})",
            )
        self._position = position

    def skip(self, count: int) -> None:
        """Avance le curseur de ``count`` octets.

        Args:
            count: Nombre d'octets a ignorer (doit etre positif ou nul).

        Raises:
            ValueError: ``count`` est negatif.
            InsufficientDataError: Il ne reste pas assez d'octets.
        """
        if count < 0:
            raise ValueError("skip() n'accepte pas de valeur negative ; utilisez seek()")
        self._require(count)
        self._position += count

    @contextmanager
    def at(self, position: int) -> Iterator[BinaryReader]:
        """Lit temporairement a une autre position, puis restaure le curseur.

        Args:
            position: Position de lecture temporaire.

        Yields:
            Le lecteur lui-meme, positionne sur ``position``.
        """
        previous = self._position
        self.seek(position)
        try:
            yield self
        finally:
            self._position = previous

    # ------------------------------------------------------------------ #
    # Lecture d'octets
    # ------------------------------------------------------------------ #
    def read_bytes(self, count: int) -> bytes:
        """Lit ``count`` octets et avance le curseur.

        Args:
            count: Nombre d'octets a lire.

        Returns:
            Les octets lus.

        Raises:
            ValueError: ``count`` est negatif.
            InsufficientDataError: Il ne reste pas assez d'octets.
        """
        if count < 0:
            raise ValueError("read_bytes() attend un nombre d'octets positif")
        self._require(count)
        start = self._position
        self._position += count
        return self._data[start : self._position]

    def peek(self, count: int) -> bytes:
        """Lit ``count`` octets **sans** deplacer le curseur.

        Retourne moins d'octets que demande si la fin du tampon est atteinte, afin
        de pouvoir inspecter une fin de fichier sans declencher d'erreur.
        """
        if count < 0:
            raise ValueError("peek() attend un nombre d'octets positif")
        return self._data[self._position : self._position + count]

    def read_remaining(self) -> bytes:
        """Lit tous les octets restants et place le curseur en fin de tampon."""
        return self.read_bytes(self.remaining)

    # ------------------------------------------------------------------ #
    # Entiers
    # ------------------------------------------------------------------ #
    def read_uint(self, length: int, *, byte_order: ByteOrder = "big") -> int:
        """Lit un entier non signe de ``length`` octets.

        Args:
            length: Nombre d'octets (1 a 8).
            byte_order: Ordre des octets.

        Returns:
            La valeur entiere.

        Raises:
            ValueError: ``length`` n'est pas compris entre 1 et 8.
            InsufficientDataError: Il ne reste pas assez d'octets.
        """
        if not 1 <= length <= 8:
            raise ValueError("read_uint() accepte de 1 a 8 octets")
        return int.from_bytes(self.read_bytes(length), byteorder=byte_order, signed=False)

    def read_int(self, length: int, *, byte_order: ByteOrder = "big") -> int:
        """Lit un entier signe (complement a deux) de ``length`` octets."""
        if not 1 <= length <= 8:
            raise ValueError("read_int() accepte de 1 a 8 octets")
        return int.from_bytes(self.read_bytes(length), byteorder=byte_order, signed=True)

    def read_uint8(self) -> int:
        """Lit un entier non signe sur 1 octet."""
        return self.read_uint(1)

    def read_uint16(self, *, byte_order: ByteOrder = "big") -> int:
        """Lit un entier non signe sur 2 octets."""
        return self.read_uint(2, byte_order=byte_order)

    def read_uint24(self, *, byte_order: ByteOrder = "big") -> int:
        """Lit un entier non signe sur 3 octets."""
        return self.read_uint(3, byte_order=byte_order)

    def read_uint32(self, *, byte_order: ByteOrder = "big") -> int:
        """Lit un entier non signe sur 4 octets."""
        return self.read_uint(4, byte_order=byte_order)

    # ------------------------------------------------------------------ #
    # Chaines
    # ------------------------------------------------------------------ #
    def read_string(
        self,
        length: int,
        *,
        encoding: str = "latin-1",
        strip_padding: bool = True,
    ) -> str:
        """Lit une chaine de longueur fixe.

        Args:
            length: Nombre d'octets occupes par le champ.
            encoding: Encodage utilise pour le decodage.
            strip_padding: Supprime les octets nuls, ``0xFF`` et les espaces de
                remplissage en debut et fin de champ.

        Returns:
            La chaine decodee. Les octets non decodables sont remplaces plutot que
            de faire echouer la lecture : un champ texte abime ne doit pas empecher
            l'exploitation du reste du fichier.
        """
        raw = self.read_bytes(length)
        if strip_padding:
            raw = raw.strip(b"\x00\xff").strip()
        return raw.decode(encoding, errors="replace")

    def read_hex(self, length: int) -> str:
        """Lit ``length`` octets et les retourne en hexadecimal minuscule."""
        return self.read_bytes(length).hex()

    def read_bcd(self, length: int) -> str:
        """Lit un nombre code en BCD (``Binary Coded Decimal``) compact.

        Chaque octet contient deux chiffres decimaux (quartet de poids fort puis
        quartet de poids faible). Ce codage est utilise par de nombreux champs de
        date et d'identifiant.

        Args:
            length: Nombre d'octets a lire.

        Returns:
            La chaine de chiffres correspondante, par exemple ``"20260923"``.

        Raises:
            BinaryReaderError: Un quartet ne represente pas un chiffre decimal.
        """
        start = self._position
        raw = self.read_bytes(length)
        digits: list[str] = []
        for index, byte in enumerate(raw):
            high, low = byte >> 4, byte & 0x0F
            if high > 9 or low > 9:
                raise BinaryReaderError(
                    "Une valeur numerique du fichier est invalide.",
                    position=start + index,
                    technical_detail=(
                        f"octet BCD invalide 0x{byte:02X} a la position {start + index}"
                    ),
                )
            digits.append(f"{high}{low}")
        return "".join(digits)

    # ------------------------------------------------------------------ #
    # Interne
    # ------------------------------------------------------------------ #
    def _require(self, count: int) -> None:
        """Verifie qu'il reste au moins ``count`` octets a lire."""
        if count > self.remaining:
            raise InsufficientDataError(
                position=self._position,
                technical_detail=(
                    f"{count} octets demandes a la position {self._position}, "
                    f"{self.remaining} disponibles (taille totale {len(self._data)})"
                ),
            )

    def __len__(self) -> int:
        """Taille totale du tampon."""
        return len(self._data)

    def __repr__(self) -> str:
        """Representation technique, sans contenu (donnees potentiellement personnelles)."""
        return f"<BinaryReader position={self._position} size={len(self._data)}>"
