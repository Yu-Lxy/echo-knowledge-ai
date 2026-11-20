"""集中配置（ARCHITECTURE.md §5）。全部经环境变量/.env 注入，禁止硬编码。

字段名（snake_case）与 .env.example 中的大写变量名一一对应
（pydantic-settings 默认大小写不敏感匹配）。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---------- 应用 ----------
    app_name: str = "Echo Knowledge AI"
    app_debug: bool = False
    database_url: str = "postgresql+psycopg://echo:echo@localhost:5432/echo"

    # ---------- RAG（PRD D5/D6，6.5）----------
    rag_recall_top: int = 10
    rag_inject_top: int = 5
    rag_rerank_threshold: float = 0.60
    chat_history_rounds: int = 3
    question_max_chars: int = 2000

    # ---------- 上传限制（PRD D9）----------
    upload_max_files: int = 10
    upload_max_pdf_mb: int = 50
    upload_max_txt_md_mb: int = 5

    # ---------- 分块（工程默认，非 PRD 锁定）----------
    chunk_size_chars: int = 600
    chunk_overlap_chars: int = 120

    # ---------- 限流与配额（部署决定；0 = 不限）----------
    rate_limit_upload_per_min: int = 0
    rate_limit_chat_per_min: int = 0
    rate_limit_reindex_per_min: int = 0
    token_quota_soft: int = 0
    token_quota_hard: int = 0

    # ---------- 本地存储 ----------
    storage_root: str = "/data/storage"

    # ---------- 模型网关（T1 待确认；M5 前为空 = fake 适配器）----------
    llm_chat_base_url: str = ""
    llm_chat_api_key: str = ""
    llm_chat_model: str = ""
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    # T1 确认后锁定；fake 适配器同样使用该维度
    embedding_dim: int = 1024
    rerank_base_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
