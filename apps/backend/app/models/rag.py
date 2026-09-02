"""RAG and memory models (spec §14: documents, document_chunks,
knowledge_bases, memories, feedback)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pk_column, utcnow


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = pk_column()
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = pk_column()
    kb_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="text/plain")
    doc_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = pk_column()
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kb_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = pk_column()
    # scope: user / project / global
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    mem_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = pk_column()
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)  # message/task/chunk...
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # -1 / 0 / +1
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
