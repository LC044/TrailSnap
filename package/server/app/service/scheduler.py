"""统一后台任务调度器（基于 APScheduler）。

替代原先散落在各处的自管 daemon 线程：
- ``TaskManager._scheduler_loop``（扫描 + 回收站清理）
- ``UpdateCheckScheduler._loop``（版本更新检查）

所有 job 在同一个 ``BackgroundScheduler`` 里按 cron / interval 触发，
共用 ``coalesce=True, max_instances=1`` 避免重入与重叠。
"""
import logging
from typing import Callable, Optional, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("app.service.scheduler")


class JobScheduler:
    """APScheduler ``BackgroundScheduler`` 的薄包装，集中管理调度生命周期。"""

    def __init__(self):
        self._scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,         # 错过的触发合并成一次
                "max_instances": 1,       # 同一 job 不并发
                "misfire_grace_time": 300,  # 5 分钟内的延迟触发仍然执行
            }
        )
        self._started = False

    def register_cron_job(self, name: str, cron_expr: Optional[str], fn: Callable) -> bool:
        """按 cron 表达式注册 job。``cron_expr`` 为空（None/''）时跳过注册，
        用于支持 ``scan_schedule.mode='off'`` 这类配置关闭的场景。"""
        if not cron_expr:
            logger.info(f"JobScheduler: skip cron job '{name}' (no cron expression).")
            return False
        try:
            trigger = CronTrigger.from_crontab(cron_expr)
        except Exception as e:
            logger.error(f"JobScheduler: invalid cron '{cron_expr}' for '{name}': {e}")
            return False
        try:
            self._scheduler.add_job(fn, trigger, id=name, replace_existing=True)
            logger.info(f"JobScheduler: registered cron job '{name}' = '{cron_expr}'.")
            return True
        except Exception as e:
            logger.error(f"JobScheduler: failed to register job '{name}': {e}")
            return False

    def register_interval_job(
        self,
        name: str,
        seconds: int,
        fn: Callable,
        next_run_time: Optional[Any] = None,
    ) -> bool:
        """注册 interval 触发的 job。``next_run_time`` 非空时，scheduler 启动
        后立刻先跑一次（之后按 ``seconds`` 间隔继续）。"""
        kwargs = {}
        if next_run_time is not None:
            kwargs["next_run_time"] = next_run_time
        try:
            self._scheduler.add_job(
                fn, "interval", seconds=seconds, id=name, replace_existing=True, **kwargs
            )
            logger.info(
                f"JobScheduler: registered interval job '{name}' every {seconds}s"
                + (" (next_run_time=" + str(next_run_time) + ")" if next_run_time else "")
                + "."
            )
            return True
        except Exception as e:
            logger.error(f"JobScheduler: failed to register job '{name}': {e}")
            return False

    def start(self):
        if self._started:
            return
        self._scheduler.start()
        self._started = True
        logger.info("JobScheduler started.")

    def stop(self):
        if not self._started:
            return
        try:
            self._scheduler.shutdown(wait=False)
        except Exception as e:
            logger.warning(f"JobScheduler shutdown: {e}")
        self._started = False
        logger.info("JobScheduler stopped.")