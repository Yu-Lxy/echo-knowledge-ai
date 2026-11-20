"""集中配置测试：默认值与 PRD 锁定值一致，环境变量可覆盖。"""

import pytest

from app.core.config import Settings


def test_rag_defaults_match_prd():
    s = Settings(_env_file=None)  # 忽略 .env，验证代码内默认
    assert s.rag_recall_top == 10  # D5
    assert s.rag_inject_top == 5  # D5
    assert s.rag_rerank_threshold == 0.60  # D5
    assert s.chat_history_rounds == 3  # D6
    assert s.question_max_chars == 2000  # PRD 6.5


def test_upload_limits_match_prd():
    s = Settings(_env_file=None)
    assert s.upload_max_files == 10  # D9
    assert s.upload_max_pdf_mb == 50
    assert s.upload_max_txt_md_mb == 5


def test_env_override(monkeypatch):
    monkeypatch.setenv("RAG_RERANK_THRESHOLD", "0.55")
    monkeypatch.setenv("UPLOAD_MAX_FILES", "5")
    s = Settings(_env_file=None)
    assert s.rag_rerank_threshold == 0.55
    assert s.upload_max_files == 5
