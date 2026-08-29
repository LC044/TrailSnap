import json
import os
import threading
import logging
import math
from pathlib import Path
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

def _available_cpu_cores() -> int:
    detected = os.cpu_count() or 1
    try:
        affinity = os.sched_getaffinity(0)
        detected = min(detected, len(affinity))
    except (AttributeError, OSError):
        pass
    for path in (Path("/sys/fs/cgroup/cpu.max"), Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")):
        try:
            parts = path.read_text(encoding="utf-8").strip().split()
            quota = parts[0]
            if quota == "max" or int(quota) <= 0:
                continue
            if path.name == "cpu.max":
                period = int(parts[1])
            else:
                period = int(path.with_name("cpu.cfs_period_us").read_text(encoding="utf-8").strip())
            detected = min(detected, max(1, math.ceil(int(quota) / period)))
        except (OSError, ValueError, IndexError, ZeroDivisionError):
            continue
    return max(1, detected)


def _available_memory_gb() -> float:
    import psutil

    detected = float(psutil.virtual_memory().total)
    for path in (Path("/sys/fs/cgroup/memory.max"), Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")):
        try:
            raw = path.read_text(encoding="utf-8").strip()
            if raw == "max":
                continue
            limit = int(raw)
            if 0 < limit < (1 << 60):
                detected = min(detected, float(limit))
        except (OSError, ValueError):
            continue
    return detected / (1024 ** 3)


def get_default_concurrency_level() -> str:
    try:
        cpu_cores = _available_cpu_cores()
        memory_gb = _available_memory_gb()
        # 实际可用内存通常略小于标称值，因此允许一定误差
        if cpu_cores >= 8 and memory_gb >= 15:
            return "high"
        elif cpu_cores >= 4 and memory_gb >= 7:
            return "medium"
        else:
            return "low"
    except Exception as e:
        logging.warning(f"Failed to calculate system concurrency level: {e}")
        return "medium"


def resolve_concurrency_level(level: str) -> str:
    """Resolve the user-facing automatic mode to a concrete worker profile."""
    return get_default_concurrency_level() if level == "auto" else level

class SecuritySettings(BaseModel):
    secret_key: str = Field(default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7", description="Secret key for JWT")
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(default=60*24*3, description="Access token expiration in minutes")
    allow_registration: bool = Field(default=False, description="Allow new user self-registration")

class TaskSettings(BaseModel):
    concurrency_level: Literal["auto", "low", "medium", "high"] = Field(
        default="auto",
        description="Task performance mode: auto, low, medium, high",
    )
    adaptive_concurrency: bool = Field(default=True, description="Dynamically tune each resource pool with AIMD")
    aimd_success_threshold: int = Field(default=4, ge=1, le=100, description="Successful batches before concurrency increases by one")
    aimd_cooldown_seconds: float = Field(default=5.0, ge=0, le=300, description="Minimum seconds between AIMD increases")
    cpu_high_watermark: float = Field(default=90.0, ge=50, le=100, description="CPU percentage that triggers multiplicative decrease")
    memory_high_watermark: float = Field(default=90.0, ge=50, le=100, description="Memory percentage that blocks concurrency increases")

class ScanScheduleSettings(BaseModel):
    mode: str = Field(default='off', description="Options: 'off', 'interval', 'weekly'")
    interval: int = Field(default=60, description="Options: 5, 10, 15, 30, 60")
    weekdays: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6], description="0=Monday")
    time: str = Field(default="02:00", description="Format HH:mm")

    def to_cron_expression(self) -> Optional[str]:
        if self.mode == 'off':
            return None
        elif self.mode == 'interval':
            return f"*/{self.interval} * * * *"
        elif self.mode == 'weekly':
            try:
                hour, minute = self.time.split(":")
                hour_int = int(hour)
                minute_int = int(minute)
                weekdays_str = ",".join(map(str, self.weekdays))
                return f"{minute_int} {hour_int} * * {weekdays_str}"
            except ValueError:
                return None
        return None


class MomentCaptionScheduleSettings(BaseModel):
    """朋友圈日文案定时生成调度。与 ``ScanScheduleSettings`` 保持相同调度字段。"""

    mode: str = Field(default='off', description="Options: 'off', 'interval', 'weekly'")
    interval: int = Field(default=60, description="分钟；interval 模式生效")
    weekdays: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6], description="0=Monday")
    time: str = Field(default="03:00", description="Format HH:mm；建议凌晨错开扫描任务")
    per_caption_delay_sec: int = Field(default=2, description="每次生成之间的间隔秒数，保护 LLM")
    max_run_seconds: int = Field(default=300, description="单次 job 最长运行秒数；软超时后剩余天数留待下次")
    max_consecutive_failures_per_user: int = Field(default=5, description="单个用户连续失败多少次后跳过")

    def to_cron_expression(self) -> Optional[str]:
        if self.mode == 'off':
            return None
        elif self.mode == 'interval':
            return f"*/{self.interval} * * * *"
        elif self.mode == 'weekly':
            try:
                hour, minute = self.time.split(":")
                hour_int = int(hour)
                minute_int = int(minute)
                weekdays_str = ",".join(map(str, self.weekdays))
                return f"{minute_int} {hour_int} * * {weekdays_str}"
            except ValueError:
                return None
        return None


class RecycleBinSettings(BaseModel):
    retention_days: int = Field(default=7, description="Number of days to keep photos in recycle bin before permanent deletion")
    cleanup_time: str = Field(default="00:00", description="Time of day to run the cleanup task, format HH:mm")

class ProactiveMemoryScheduleSettings(BaseModel):
    """主动式记忆（那年今日主动关怀）定时调度。默认每天 09:00 触发，可关闭。"""

    mode: str = Field(default='weekly', description="Options: 'off', 'interval', 'weekly'")
    interval: int = Field(default=1440, description="分钟；interval 模式生效")
    weekdays: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6], description="0=Monday")
    time: str = Field(default="09:00", description="Format HH:mm")
    max_run_seconds: int = Field(default=300, description="单次 job 最长运行秒数")
    max_consecutive_failures_per_user: int = Field(default=5, description="单个用户连续失败多少次后跳过")
    top_photos: int = Field(default=9, description="每条主动消息展示的高分照片数量")

    def to_cron_expression(self) -> Optional[str]:
        if self.mode == 'off':
            return None
        elif self.mode == 'interval':
            return f"*/{self.interval} * * * *"
        elif self.mode == 'weekly':
            try:
                hour, minute = self.time.split(":")
                weekdays_str = ",".join(map(str, self.weekdays))
                return f"{int(minute)} {int(hour)} * * {weekdays_str}"
            except ValueError:
                return None
        return None

class SystemSettings(BaseModel):
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    task: TaskSettings = Field(default_factory=TaskSettings)
    scan_schedule: ScanScheduleSettings = Field(default_factory=ScanScheduleSettings)
    moment_caption_schedule: MomentCaptionScheduleSettings = Field(default_factory=MomentCaptionScheduleSettings)
    proactive_memory_schedule: ProactiveMemoryScheduleSettings = Field(default_factory=ProactiveMemoryScheduleSettings)
    recycle_bin: RecycleBinSettings = Field(default_factory=RecycleBinSettings)

class SystemConfigManager:
    _instance = None
    _lock = threading.RLock()
    _config_path = './data/system_config.json'

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(SystemConfigManager, cls).__new__(cls)
                    cls._instance._load()
        return cls._instance

    def _load(self):
        self.config = SystemSettings()
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config = SystemSettings(**data)
            except Exception as e:
                logging.error(f"Failed to load system config: {e}")
        else:
            self.save()

    def save(self):
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
                with open(self._config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config.model_dump(), f, indent=4, ensure_ascii=False)
            except Exception as e:
                logging.error(f"Failed to save system config: {e}")

system_config = SystemConfigManager()
