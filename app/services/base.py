"""Classe de base des services.

Role d'un service : orchestrer une intention metier de bout en bout, en ouvrant
**une** transaction et en la confiant aux depots. C'est le service, et lui seul, qui
decide du perimetre transactionnel.

Regle de frontiere : un service ne retourne jamais d'objet SQLAlchemy a l'interface.
Il retourne des objets de transfert (``dataclass`` figees) construits pendant que la
session est ouverte. Deux benefices : l'interface ne peut pas declencher de requete
implicite, et la substitution ulterieure d'une source REST ne changera pas le contrat.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.config.logging_config import get_logger
from app.database.database import Database, get_database

__all__ = ["BaseService"]

logger = get_logger(__name__)


class BaseService:
    """Base commune des services applicatifs.

    Args:
        database: Base a utiliser. Par defaut, la base partagee du processus, ce qui
            permet aux tests d'injecter une base temporaire.
    """

    def __init__(self, database: Database | None = None) -> None:
        self._database = database or get_database()

    @property
    def database(self) -> Database:
        """Base utilisee par ce service."""
        return self._database

    @contextmanager
    def _session(self) -> Iterator[Session]:
        """Ouvre une session transactionnelle.

        Yields:
            La session ouverte ; elle est validee a la sortie normale du bloc et
            annulee en cas d'exception.
        """
        with self._database.session() as session:
            yield session
