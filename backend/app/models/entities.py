"""SQLAlchemy ORM 实体（ARCHITECTURE.md §6 七张表）。

chunk 定位元数据（heading_path/para_index/char_start/char_end/page_no）
满足 PRD 6.4 片段可追溯要求；文档展示名经 documents join 组装（#7 决策）。
"""

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.core.db import Base
from app.models.enums import DocumentStatus, JobStatus, JobType, QaOutcome, UserRole

# EMBEDDING_DIM 随 T1 选型确定；fake 适配器同样使用（ARCHITECTURE.md §6）
EMBEDDING_DIM = get_settings().embedding_dim

# DB 枚举存成员 value（小写字符串），与 server_default / SQL 查询一致
def pg_enum(py_enum, name: str):
    return Enum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # argon2id
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), nullable=False, default=UserRole.USER
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    # token 服务端存哈希（sha256），Cookie 明文仅留在浏览器
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        # T5：仅 processing/available 参与判重；failed/deleted 豁免（可重传自救）
        Index(
            "uq_documents_content_sha256_active",
            "content_sha256",
            unique=True,
            postgresql_where=text("status IN ('processing', 'available')"),
        ),
        Index(
            "ix_documents_status_created",
            "status",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)  # 仅展示，渲染转义
    storage_key: Mapped[str] = mapped_column(String(128), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ext: Mapped[str] = mapped_column(String(16), nullable=False)  # pdf / txt / md
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        pg_enum(DocumentStatus, "document_status"),
        nullable=False,
        default=DocumentStatus.PROCESSING,
    )
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_reason_user: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    current_index_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        # 同版本内片段序号唯一；检索恒带 index_version = documents.current_index_version
        UniqueConstraint("document_id", "index_version", "seq", name="uq_chunks_doc_version_seq"),
        # HNSW 余弦索引在 Alembic 迁移中创建（pgvector 操作符类），此处不重复定义
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    index_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    heading_path: Mapped[str | None] = mapped_column(Text)  # Markdown 标题层级
    para_index: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    page_no: Mapped[int | None] = mapped_column(Integer)  # PDF 页码
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship()


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        # 活跃任务对 (job_type, document_id) 唯一：幂等键的库级保障（§10）。
        # reindex_all 无 document_id（NULL 不参与唯一冲突）。
        Index(
            "uq_processing_jobs_active_type_doc",
            "job_type",
            "document_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        CheckConstraint("attempts <= max_attempts", name="attempts_within_max"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[JobType] = mapped_column(
        pg_enum(JobType, "job_type"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"),
        nullable=False,
        default=JobStatus.QUEUED,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QaLog(Base):
    __tablename__ = "qa_logs"
    __table_args__ = (
        Index("ix_qa_logs_user_created", "user_id", "created_at"),
    )

    # request_id 即主键（§12：按 request_id 复现完整检索路径）
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_query: Mapped[str | None] = mapped_column(Text)
    # Top10 召回（片段 id + 分数）/ 实际注入集合 / 最终引用集合
    recalled: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    injected: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    outcome: Mapped[QaOutcome] = mapped_column(
        pg_enum(QaOutcome, "qa_outcome"), nullable=False
    )
    model_latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_usage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TokenUsageDaily(Base):
    __tablename__ = "token_usage_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
