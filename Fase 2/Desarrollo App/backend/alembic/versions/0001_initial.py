"""Esquema inicial: extensión pgvector + todas las tablas.

Revision ID: 0001
Revises:
Create Date: 2026-08-08
"""
from alembic import op

from app.db.base import Base
import app.models  # noqa: F401

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind)
    if bind.dialect.name == "postgresql":
        op.execute("CREATE INDEX IF NOT EXISTS ix_chunks_embedding ON chunks "
                   "USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
