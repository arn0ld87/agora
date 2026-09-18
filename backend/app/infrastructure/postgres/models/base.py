"""Gemeinsame SQLAlchemy-Metadaten für das Agora-Fachschema."""
from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

AGORA_SCHEMA = 'agora'

NAMING_CONVENTION = {
    'ix': 'ix_%(table_name)s_%(column_0_name)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
}


class Base(DeclarativeBase):
    """Basisklasse aller von Alembic verwalteten Agora-Modelle."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
