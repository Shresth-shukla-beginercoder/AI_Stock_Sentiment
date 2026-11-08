"""make_published_at_nullable

Revision ID: dbae216b6424
Revises: 4dcf3bc5443b
Create Date: 2026-11-08 16:27:03.456848

Phase 5 correction 1: Publication timestamp integrity.

Make published_at nullable in social_posts and news_articles to preserve
unknown publication times honestly. Collection time is preserved separately
in created_at (already exists, server default now()).

Downstream consumers can distinguish:
- published_at IS NULL → source had no publication timestamp
- published_at IS NOT NULL → actual source publication time

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dbae216b6424'
down_revision: Union[str, None] = '4dcf3bc5443b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make published_at nullable in social_posts
    op.alter_column(
        'social_posts',
        'published_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=True,
    )
    # Make published_at nullable in news_articles
    op.alter_column(
        'news_articles',
        'published_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=True,
    )


def downgrade() -> None:
    # Restore NOT NULL constraint (will fail if NULL rows exist)
    op.alter_column(
        'news_articles',
        'published_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=False,
    )
    op.alter_column(
        'social_posts',
        'published_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=False,
    )
