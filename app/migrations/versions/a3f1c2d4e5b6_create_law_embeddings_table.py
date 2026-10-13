"""create law_embeddings table

Revision ID: a3f1c2d4e5b6
Revises: 9b2d5e7f1031
Create Date: 2026-10-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
import sqlmodel


revision: str = "a3f1c2d4e5b6"
down_revision: Union[str, Sequence[str], None] = "9b2d5e7f1031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector 확장은 PostgreSQL에만 존재한다. SQLite(테스트)는 VECTOR를 일반 타입명으로 받는다.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "law_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("article", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("law_embeddings")
