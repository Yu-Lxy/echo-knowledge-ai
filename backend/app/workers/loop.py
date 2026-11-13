"""worker 任务循环入口。

M0 占位：保持容器存活即可，任务认领（SKIP LOCKED）与处理器在 M1+ 落地
（ARCHITECTURE.md §9）。backend 与 worker 共享本镜像，仅启动命令不同。
"""

import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

POLL_INTERVAL_SECONDS = 60


def main() -> None:
    log.info("worker 启动（M0 占位循环，任务处理自 M1 落地）")
    while True:
        # M1: SELECT … FOR UPDATE SKIP LOCKED 认领 processing_jobs 并分发处理器
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
