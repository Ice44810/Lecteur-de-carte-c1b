"""Modele ``Driver`` : conducteur identifie par sa carte."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - imports de typage uniquement
    from app.database.models.activity import Activity
    from app.database.models.analysis import Analysis
    from app.database.models.infringement import Infringement
    from app.database.models.tachograph_file import TachographFile

__all__ = ["Driver"]


class Driver(TimestampMixin, Base):
    """Conducteur, identifie de maniere unique par son numero de carte.

    Le numero de carte est la seule donnee obligatoire : les autres champs ne sont
    renseignes que lorsqu'ils ont effectivement ete decodes depuis un fichier
    tachygraphique. Aucune valeur n'est inventee ni deduite.
    """

    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(primary_key=True)

    card_number: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
        doc="Numero de la carte conducteur, identifiant metier du conducteur.",
    )
    first_name: Mapped[str | None] = mapped_column(String(64), doc="Prenom, si decode.")
    last_name: Mapped[str | None] = mapped_column(String(64), doc="Nom de famille, si decode.")
    birth_date: Mapped[date | None] = mapped_column(Date, doc="Date de naissance, si decodee.")

    card_issuing_country: Mapped[str | None] = mapped_column(
        String(3), doc="Code pays emetteur de la carte (alpha-2 ou alpha-3), si decode."
    )
    card_issue_date: Mapped[date | None] = mapped_column(Date, doc="Date de delivrance de la carte.")
    card_expiry_date: Mapped[date | None] = mapped_column(Date, doc="Date d'expiration de la carte.")

    notes: Mapped[str | None] = mapped_column(String(500), doc="Commentaire libre de l'exploitant.")

    activities: Mapped[list[Activity]] = relationship(
        back_populates="driver",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    files: Mapped[list[TachographFile]] = relationship(back_populates="driver")
    analyses: Mapped[list[Analysis]] = relationship(
        back_populates="driver",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    infringements: Mapped[list[Infringement]] = relationship(
        back_populates="driver",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def display_name(self) -> str:
        """Nom lisible du conducteur, avec repli sur le numero de carte.

        Returns:
            ``"NOM Prenom"`` si connu, sinon ``"Carte <numero>"``.
        """
        parts = [part for part in ((self.last_name or "").upper(), self.first_name or "") if part]
        if parts:
            return " ".join(parts)
        return f"Carte {self.card_number}"

    def is_card_expired(self, reference: date) -> bool | None:
        """Indique si la carte est expiree a la date de reference.

        Args:
            reference: Date d'evaluation.

        Returns:
            ``True``/``False``, ou ``None`` si la date d'expiration est inconnue.
        """
        if self.card_expiry_date is None:
            return None
        return self.card_expiry_date < reference
