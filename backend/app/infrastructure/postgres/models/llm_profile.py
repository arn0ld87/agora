"""Persistenzmodell für LLM-Profil-Metadaten."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import AGORA_SCHEMA, Base


class LlmProfileModel(Base):
    """Single-User-Modell ohne Provider-Secrets oder Auth-Abhängigkeiten."""

    __tablename__ = 'llm_profiles'
    __table_args__ = (
        CheckConstraint(
            'char_length(name) BETWEEN 1 AND 80',
            name='name_length',
        ),
        CheckConstraint(
            'char_length(provider) > 0',
            name='provider_not_empty',
        ),
        CheckConstraint(
            'char_length(base_url) > 0',
            name='base_url_not_empty',
        ),
        CheckConstraint(
            'char_length(model_name) > 0',
            name='model_name_not_empty',
        ),
        Index(
            'uq_llm_profiles_single_default',
            'is_default',
            unique=True,
            postgresql_where=text('is_default'),
        ),
        {'schema': AGORA_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text('false'),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
