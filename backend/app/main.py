"""应用入口。中间件（请求ID、限流）随对应里程碑补充。"""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    # /healthz：基础设施健康检查（compose healthcheck 直连）
    # /api/healthz：经 nginx 反代的前端探活端点；业务路由自 M2 起统一挂 /api 前缀
    app.include_router(health_router)
    app.include_router(health_router, prefix="/api")
    return app


app = create_app()
