"""Tokens de invitación, reseteo y refresco: se guardan como hash SHA-256.

Convierte los tokens que estuvieran en claro. Los enlaces ya enviados siguen funcionando,
porque el servidor ahora compara el hash del token recibido con el hash guardado.

Revision ID: 0002
Revises: 0001
"""
import hashlib

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _hash_column(bind, table: str, column: str) -> None:
    rows = bind.execute(sa.text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")).fetchall()
    for row_id, token in rows:
        bind.execute(sa.text(f"UPDATE {table} SET {column} = :h WHERE id = :id"),
                     {"h": _hash(token), "id": row_id})


def upgrade() -> None:
    bind = op.get_bind()
    _hash_column(bind, "users", "invitation_token")
    _hash_column(bind, "users", "reset_token")
    _hash_column(bind, "refresh_tokens", "token")


def downgrade() -> None:
    # un hash no se puede revertir: se invalidan los tokens pendientes (hay que reenviar invitaciones)
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE users SET invitation_token = NULL, reset_token = NULL"))
    bind.execute(sa.text("DELETE FROM refresh_tokens"))
