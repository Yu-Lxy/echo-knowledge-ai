"""M1 初始 schema：七张表、枚举、pgvector、部分唯一索引与 HNSW。

Revision ID: 0001_m1_schema
Revises:
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.enums import DocumentStatus, JobStatus, JobType, QaOutcome, UserRole

revision = "0001_m1_schema"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024  # 与 app.core.config.Settings.embedding_dim 默认一致，T1 确认后迁移调整


def upgrade() -> None:
    # ---------- pgvector 扩展 ----------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ---------- 枚举类型 ----------
    # 由 op.create_table 内联创建；values_callable 使 DB 存成员 value（小写），
    # 与 server_default 及 SQL 查询一致
    def ve(e):
        return [m.value for m in e]

    user_role = sa.Enum(UserRole, name="user_role", values_callable=ve)
    document_status = sa.Enum(DocumentStatus, name="document_status", values_callable=ve)
    job_type = sa.Enum(JobType, name="job_type", values_callable=ve)
    job_status = sa.Enum(JobStatus, name="job_status", values_callable=ve)
    qa_outcome = sa.Enum(QaOutcome, name="qa_outcome", values_callable=ve)

    # ---------- users ----------
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ---------- auth_sessions ----------
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    # ---------- documents ----------
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.String(512), nullable=False),
        sa.Column("storage_key", sa.String(128), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("ext", sa.String(16), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", document_status, nullable=False, server_default="processing"),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("failure_reason_user", sa.Text()),
        sa.Column("uploaded_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("current_index_version", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_documents_uploaded_by", "documents", ["uploaded_by"])
    # T5：仅 processing/available 判重；failed/deleted 豁免（同内容可重传自救）
    op.create_index(
        "uq_documents_content_sha256_active",
        "documents",
        ["content_sha256"],
        unique=True,
        postgresql_where=sa.text("status IN ('processing', 'available')"),
    )
    op.create_index("ix_documents_status_created", "documents", ["status", "created_at"])

    # ---------- chunks ----------
    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("index_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("heading_path", sa.Text()),
        sa.Column("para_index", sa.Integer()),
        sa.Column("char_start", sa.Integer()),
        sa.Column("char_end", sa.Integer()),
        sa.Column("page_no", sa.Integer()),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "index_version", "seq", name="uq_chunks_doc_version_seq"),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    # HNSW 余弦索引（§6）：检索恒带 index_version 过滤，建 (document_id, index_version, embedding)
    op.execute(
        "CREATE INDEX ix_chunks_hnsw_cosine ON chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    # ---------- processing_jobs ----------
    op.create_table(
        "processing_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE")),
        sa.Column("job_type", job_type, nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("status", job_status, nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("attempts <= max_attempts", name="attempts_within_max"),
    )
    op.create_index("ix_processing_jobs_document_id", "processing_jobs", ["document_id"])
    # 活跃任务对 (job_type, document_id) 唯一：幂等键库级保障（§10）
    op.create_index(
        "uq_processing_jobs_active_type_doc",
        "processing_jobs",
        ["job_type", "document_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    # ---------- admin_audit_logs ----------
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("admin_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("detail", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_admin_audit_logs_admin_user_id", "admin_audit_logs", ["admin_user_id"])
    op.create_index("ix_admin_audit_logs_target_document_id", "admin_audit_logs", ["target_document_id"])

    # ---------- qa_logs ----------
    op.create_table(
        "qa_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("rewritten_query", sa.Text()),
        sa.Column("recalled", JSONB(), nullable=False, server_default="[]"),
        sa.Column("injected", JSONB(), nullable=False, server_default="[]"),
        sa.Column("citations", JSONB(), nullable=False, server_default="[]"),
        sa.Column("outcome", qa_outcome, nullable=False),
        sa.Column("model_latency_ms", sa.Integer()),
        sa.Column("token_usage", JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_qa_logs_user_created", "qa_logs", ["user_id", "created_at"])

    # ---------- token_usage_daily ----------
    op.create_table(
        "token_usage_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("token_usage_daily")
    op.drop_index("ix_qa_logs_user_created", table_name="qa_logs")
    op.drop_table("qa_logs")
    op.drop_index("ix_admin_audit_logs_target_document_id", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_admin_user_id", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
    op.drop_index("uq_processing_jobs_active_type_doc", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_document_id", table_name="processing_jobs")
    op.drop_table("processing_jobs")
    op.drop_index("ix_chunks_hnsw_cosine", table_name="chunks")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_documents_status_created", table_name="documents")
    op.drop_index("uq_documents_content_sha256_active", table_name="documents")
    op.drop_index("ix_documents_uploaded_by", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
    # 枚举类型随表删除后显式 DROP（sa.Enum(name=...) 是列类型不是删除动作）
    bind = op.get_bind()
    for name in ("qa_outcome", "job_status", "job_type", "document_status", "user_role"):
        sa.Enum(name=name).drop(bind, checkfirst=True)
    # vector 扩展保留：可能被库内其他对象依赖
