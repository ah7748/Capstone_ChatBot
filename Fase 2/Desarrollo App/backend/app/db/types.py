"""Tipo de columna para embeddings: pgvector en PostgreSQL, JSON en otros motores (tests)."""
import json

from sqlalchemy import Text, TypeDecorator

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover
    Vector = None

from app.core.config import settings


class EmbeddingVector(TypeDecorator):
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and Vector is not None:
            return dialect.type_descriptor(Vector(settings.EMBEDDING_DIM))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql" and Vector is not None:
            return value
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql" and Vector is not None:
            return list(value)
        return json.loads(value)
