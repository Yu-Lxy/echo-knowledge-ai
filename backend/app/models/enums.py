"""文档与任务状态枚举（与 PRD 6.4 / ARCHITECTURE.md §6 一致，禁止悄然修改）。"""

import enum


class DocumentStatus(str, enum.Enum):
    PROCESSING = "processing"
    AVAILABLE = "available"
    FAILED = "failed"
    DELETED = "deleted"


class JobType(str, enum.Enum):
    INGEST = "ingest"
    REINDEX = "reindex"
    REINDEX_ALL = "reindex_all"
    PURGE = "purge"
    STATUS_RECHECK = "status_recheck"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class QaOutcome(str, enum.Enum):
    ANSWERED = "answered"
    REFUSED = "refused"
    INJECTED_BLOCKED = "injected_blocked"
    VALIDATION_FAILED = "validation_failed"
    MODEL_ERROR = "model_error"
    QUOTA_EXCEEDED = "quota_exceeded"
