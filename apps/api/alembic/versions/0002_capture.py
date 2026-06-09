"""capture: role, successor, knowledge_source, document, ingestion_job"""
import sqlalchemy as sa

from alembic import op  # noqa: I001

revision = "0002_capture"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("org_id", sa.String, nullable=False, index=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "successor",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("role_id", sa.String, nullable=False, unique=True, index=True),
        sa.Column("knowledge_base_name", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="provisioning"),
        sa.Column("summary", sa.String, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "knowledge_source",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("successor_id", sa.String, nullable=False, index=True),
        sa.Column("type", sa.String, nullable=False, server_default="blob"),
        sa.Column("container", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "document",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source_id", sa.String, nullable=False, index=True),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("content_type", sa.String, nullable=False),
        sa.Column("blob_path", sa.String, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="uploaded"),
        sa.Column("error", sa.String, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "ingestion_job",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("successor_id", sa.String, nullable=False, index=True),
        sa.Column("status", sa.String, nullable=False, server_default="queued"),
        sa.Column("run_ref", sa.String, nullable=False, server_default=""),
        sa.Column("doc_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("doc_indexed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("doc_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.String, nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ingestion_job")
    op.drop_table("document")
    op.drop_table("knowledge_source")
    op.drop_table("successor")
    op.drop_table("role")
