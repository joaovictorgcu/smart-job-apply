"""An account's own AI provider and key.

Every free tier this app supports is rate-limited per key. One shared
`AI_API_KEY` across every account is one shared 429, so an account may bring its
own — provider name plus a Fernet-encrypted key, alongside the `ai_model`
override that was already there.

Both columns are nullable with no default and no backfill: NULL means "use the
deployment's credentials", which is exactly what every existing row was doing
before this migration and keeps doing after it.

The key column is `Text`, not `String(n)`: a Fernet token is base64 over an
AES-CBC payload and grows with the secret it wraps, and a truncated ciphertext
is an undecryptable one.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("ai_provider", sa.String(length=30), nullable=True))
    op.add_column("user_settings", sa.Column("ai_api_key_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_settings", "ai_api_key_encrypted")
    op.drop_column("user_settings", "ai_provider")
