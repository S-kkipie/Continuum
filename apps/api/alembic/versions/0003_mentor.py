"""mentor: conversation, message"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op  # noqa: I001

revision = "0003_mentor"
down_revision = "0002_capture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("successor_id", sa.String, nullable=False, index=True),
        sa.Column("user_id", sa.String, nullable=False, index=True),
        sa.Column("title", sa.String, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "message",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("conversation_id", sa.String, nullable=False, index=True),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("content", sa.String, nullable=False),
        sa.Column("citations", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("message")
    op.drop_table("conversation")
