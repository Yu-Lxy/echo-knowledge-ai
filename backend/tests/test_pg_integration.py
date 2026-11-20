"""PG 集成测试（标记 pg）：迁移可重放 + T5 判重 + 活跃任务唯一。

运行方式：先起一次性 PG（scripts/dev_pg.sh），再
    pytest -m pg
连接串取 TEST_DATABASE_URL 环境变量。
"""

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.models import Document, ProcessingJob, User
from app.models.enums import DocumentStatus, JobStatus, JobType, UserRole

pytestmark = pytest.mark.pg

TEST_DB_URL = None  # 由 fixture 设置


@pytest.fixture(scope="session")
def engine_url(tmp_path_factory):
    import os

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL 未设置（用 scripts/dev_pg.sh 启动后运行）")
    return url


@pytest.fixture(scope="session")
def migrated(engine_url):
    """迁移可重放验证：空库 upgrade → downgrade 到底 → 再 upgrade（ Alembic x-args 直连测试库）。"""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.attributes["db_url"] = engine_url

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield engine_url
    command.downgrade(cfg, "base")


@pytest.fixture
def session(migrated):
    engine = create_engine(migrated, poolclass=NullPool)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.rollback()
        s.close()
        engine.dispose()


def _user(s) -> User:
    u = User(email=f"{uuid.uuid4().hex}@t.local", password_hash="x", role=UserRole.USER)
    s.add(u)
    s.flush()
    return u


def _doc(s, user, sha=None, status=DocumentStatus.PROCESSING, name="a.pdf") -> Document:
    d = Document(
        display_name=name,
        storage_key=sha or uuid.uuid4().hex,
        content_sha256=sha or uuid.uuid4().hex,
        ext="pdf",
        size_bytes=10,
        status=status,
        uploaded_by=user.id,
    )
    s.add(d)
    s.flush()
    return d


def test_migration_replayable(migrated):
    """验收：迁移可重放（upgrade→downgrade→upgrade 无错误即通过）。"""
    engine = create_engine(migrated, poolclass=NullPool)
    with engine.connect() as c:
        tables = {
            r[0]
            for r in c.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        assert {
            "users",
            "auth_sessions",
            "documents",
            "chunks",
            "processing_jobs",
            "admin_audit_logs",
            "qa_logs",
            "token_usage_daily",
        } <= tables
        # pgvector 扩展与 HNSW 索引
        assert c.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'")).scalar()
        assert c.execute(
            text("SELECT indexname FROM pg_indexes WHERE indexname='ix_chunks_hnsw_cosine'")
        ).scalar()
    engine.dispose()


def test_t5_dedup_scopes(session):
    """T5：processing/available 内 sha 唯一；failed/deleted 豁免可重传。"""
    u = _user(session)
    sha = uuid.uuid4().hex
    _doc(session, u, sha=sha, status=DocumentStatus.AVAILABLE)

    dup = Document(
        display_name="dup.pdf",
        storage_key=uuid.uuid4().hex,
        content_sha256=sha,
        ext="pdf",
        size_bytes=10,
        status=DocumentStatus.PROCESSING,
        uploaded_by=u.id,
    )
    session.add(dup)
    with pytest.raises(Exception):  # 部分唯一索引拒绝
        session.flush()
    session.rollback()

    # failed 后同 sha 可再入库
    u2 = _user(session)
    _doc(session, u2, sha=sha, status=DocumentStatus.FAILED)
    _doc(session, u2, sha=sha, status=DocumentStatus.PROCESSING)
    session.flush()  # 不抛即通过


def test_active_job_uniqueness(session):
    """活跃 (job_type, document_id) 唯一；终态任务不阻塞新任务。"""
    u = _user(session)
    d = _doc(session, u)

    j1 = ProcessingJob(
        document_id=d.id,
        job_type=JobType.INGEST,
        idempotency_key=f"ingest:{d.id}",
        status=JobStatus.QUEUED,
    )
    session.add(j1)
    session.commit()  # 必须提交：否则另一会话插入同键会阻塞等待本事务（唯一索引 speculative wait）

    # 期望失败的重复插入用独立 session（提交后的 j1 让冲突立即暴露而非锁等待）
    dup_engine = session.get_bind()
    from sqlalchemy.orm import sessionmaker as _sm

    DupSession = _sm(bind=dup_engine, expire_on_commit=False)
    with DupSession() as dup:
        dup.add(
            ProcessingJob(
                document_id=d.id,
                job_type=JobType.INGEST,
                idempotency_key=f"ingest:{d.id}:retry",
                status=JobStatus.QUEUED,
            )
        )
        with pytest.raises(Exception):
            dup.flush()
        dup.rollback()

    # j1 终态后，同文档可入队新任务（不同类型）
    j1.status = JobStatus.SUCCEEDED
    session.flush()
    session.add(
        ProcessingJob(
            document_id=j1.document_id,
            job_type=JobType.REINDEX,
            idempotency_key=f"reindex:{j1.document_id}",
            status=JobStatus.QUEUED,
        )
    )
    session.flush()
