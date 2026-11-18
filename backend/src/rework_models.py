"""Rework ledger: a quarantined pellet check can split part of its weight into a new
traceable bale. Every split is an immutable event carrying generation and full lineage."""
from decimal import Decimal
from sqlalchemy import String,Numeric,ForeignKey,JSON,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base
class ReworkOrder(Base):
    __tablename__='rework_orders'
    __table_args__=(CheckConstraint('kg > 0'),CheckConstraint('generation >= 1'))
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(60),unique=True)
    # The quarantined pellet inspection this material is diverted from.
    source_check_id:Mapped[int]=mapped_column(ForeignKey('pellet_checks.id'))
    # The new bale created from the diverted weight; one bale per rework order.
    new_bale_id:Mapped[int]=mapped_column(ForeignKey('bales.id'),unique=True)
    kg:Mapped[Decimal]=mapped_column(Numeric(12,3))
    reason:Mapped[str]=mapped_column(String(600))
    # 1 = split straight from a first-generation quarantined check, then increments.
    generation:Mapped[int]
    # The first quarantined check this whole chain descends from.
    root_check_id:Mapped[int]=mapped_column(ForeignKey('pellet_checks.id'))
    # Self-contained chain: every ancestor rework event plus this one, oldest first.
    lineage:Mapped[list]=mapped_column(JSON)
    # Original inspection values, measurement history and投料 snapshot, frozen at split.
    source_snapshot:Mapped[dict]=mapped_column(JSON)
    created_by:Mapped[str]=mapped_column(String(120))
