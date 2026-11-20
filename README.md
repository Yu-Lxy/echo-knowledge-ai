# Echo Knowledge AI

内部 AI 知识库：上传文档 → 异步解析/切分/索引 → 基于共享知识库的检索问答（带可验证引用）。

- 产品范围与验收：`docs/PRD.md`（V1.0 开发定稿）
- 技术架构与决策状态：`docs/ARCHITECTURE.md`
- AI Agent 项目规则：`AGENTS.md`

## 技术栈

| 端 | 技术 |
|---|---|
| frontend | React 19 + TypeScript + Vite + Tailwind CSS v4（shadcn/ui 按需引入） |
| backend | Python 3.12 + FastAPI + SQLAlchemy + Alembic |
| db | PostgreSQL 16 + pgvector |
| worker | 与 backend 同镜像，独立启动命令（PG 队列表 + SKIP LOCKED） |
| 部署 | Docker Compose（db / backend / worker / frontend-nginx） |

## 本地开发

```bash
# backend（uv 管理）
cd backend && uv sync && uv run pytest        # 单元测试（不依赖 PG）

# PG 集成测试（一次性容器，独立于 compose 数据卷）
cd backend && ./scripts/dev_pg.sh start
TEST_DATABASE_URL=postgresql+psycopg://echo:echo@127.0.0.1:5433/echo_test uv run pytest -m pg
./scripts/dev_pg.sh stop

# frontend（pnpm）
cd frontend && pnpm install && pnpm dev   # http://localhost:5173，/api 代理到 :8000
```

数据库迁移（backend 目录内，Alembic 连接串取 `DATABASE_URL` 环境变量）：

```bash
uv run alembic upgrade head      # 升到最新
uv run alembic downgrade base    # 回滚（可重放，已在 CI 测试中验证）
```

## Docker Compose 启动

```bash
cp .env.example .env   # 填写数据库密码等
docker compose up -d --build
```

- 前端：http://localhost:3000
- 后端健康检查：http://localhost:3000/api/healthz（nginx 反代）
- 模型服务 Key（T1 待确认）：M5 前不需要，M0–M4 全程 fake 适配器

## 目录结构

```text
├── AGENTS.md            # AI Agent 项目规则（严格模式）
├── docs/                # PRD、ARCHITECTURE
├── backend/             # FastAPI 应用 + worker（同一镜像）
├── frontend/            # React SPA
└── docker-compose.yml   # 四服务编排
```

当前进度：**M0 工程初始化已完成**（里程碑定义见 ARCHITECTURE.md §15）。
