"""Album associations for polymorphic ticket references."""
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint, Index
from app.db.base import Base
from app.db.types import UUID


class AlbumTicket(Base):
    __tablename__ = "album_tickets"
    __table_args__ = (
        UniqueConstraint("album_id", "ticket_type", "ticket_id", name="uq_album_ticket"),
        Index("ix_album_tickets_reference", "ticket_type", "ticket_id"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    album_id = Column(UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    ticket_type = Column(String(16), nullable=False)
    ticket_id = Column(String(36), nullable=False)


class TicketDismissal(Base):
    """Remember explicit exclusions when an inferred memory link is removed."""
    __tablename__ = "ticket_dismissals"
    __table_args__ = (UniqueConstraint("memory_id", "ticket_type", "ticket_id", name="uq_ticket_dismissal"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False)
    ticket_type = Column(String(16), nullable=False)
    ticket_id = Column(String(36), nullable=False)
