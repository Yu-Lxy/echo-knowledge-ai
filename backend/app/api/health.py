"""健康检查端点。M0 仅确认服务存活；数据库连通性检查在 M1 接入。"""

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "app": get_settings().app_name}
