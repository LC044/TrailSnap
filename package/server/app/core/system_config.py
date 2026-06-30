import json
import os
import threading
import logging
from typing import List, Optional
from pydantic import BaseModel, Field

def get_default_concurrency_level() -> str:
    try:
        import psutil
        cpu_cores = os.cpu_count() or 1
        memory_gb = psutil.virtual_memory().total / (1024 ** 3)
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

class SecuritySettings(BaseModel):
    secret_key: str = Field(default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7", description="Secret key for JWT")
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(default=60*24*3, description="Access token expiration in minutes")
    allow_registration: bool = Field(default=False, description="Allow new user self-registration")

class TaskSettings(BaseModel):
    concurrency_level: str = Field(default_factory=get_default_concurrency_level, description="Task concurrency level: low, medium, high")

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

class RecycleBinSettings(BaseModel):
    retention_days: int = Field(default=7, description="Number of days to keep photos in recycle bin before permanent deletion")
    cleanup_time: str = Field(default="00:00", description="Time of day to run the cleanup task, format HH:mm")

class SystemSettings(BaseModel):
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    task: TaskSettings = Field(default_factory=TaskSettings)
    scan_schedule: ScanScheduleSettings = Field(default_factory=ScanScheduleSettings)
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
