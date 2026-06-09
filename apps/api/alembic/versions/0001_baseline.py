"""baseline: app_info with seed row"""
import sqlalchemy as sa

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_info",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String, nullable=False, unique=True),
        sa.Column("value", sa.String, nullable=False),
    )
    op.bulk_insert(
        sa.table("app_info", sa.column("key", sa.String), sa.column("value", sa.String)),
        [{"key": "scaffold", "value": "continuum"}],
    )


def downgrade() -> None:
    op.drop_table("app_info")
