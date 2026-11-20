#!/bin/sh
# PG 集成测试专用一次性数据库（与生产镜像一致：pgvector/pgvector:pg16）。
# 用法：./scripts/dev_pg.sh start | stop
# 测试库独立于 compose 的 db 卷，不触碰任何持久数据。

set -eu
cd "$(dirname "$0")/.."

CONTAINER=echo-test-pg
PORT=5433
URL="postgresql+psycopg://echo:echo@127.0.0.1:5433/echo_test"

case "${1:-}" in
  start)
    docker run -d --name "$CONTAINER" -e POSTGRES_USER=echo -e POSTGRES_PASSWORD=echo \
      -e POSTGRES_DB=echo_test -p "$PORT":5432 pgvector/pgvector:pg16 >/dev/null
    echo "等待 PG 就绪..."
    until docker exec "$CONTAINER" pg_isready -U echo -d echo_test >/dev/null 2>&1; do sleep 0.5; done
    echo "就绪: $URL"
    echo "TEST_DATABASE_URL=$URL"
    ;;
  stop)
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    echo "已清理 $CONTAINER"
    ;;
  *)
    echo "用法: $0 start|stop" >&2
    exit 1
    ;;
esac
