#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/12/19 13:45
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : ai-logger.py
@Description : 
"""

from fileinput import filename
import logging
import logging.handlers
import os
import sys
import json
import queue
from datetime import datetime
from pathlib import Path
from typing import Any

# Configuration Defaults
# In a real app, these should probably come from env vars or a config file
LOG_DIR = os.environ.get("TS_AI_LOG_DIR", "./data/logs")
MAX_BYTES = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 30
LOG_LEVEL = "INFO"

class JSONFormatter(logging.Formatter):
    """
    Formatter to output logs in JSON format.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            "level": record.levelname,
            "message": record.getMessage(),
            "operation": getattr(record, "operation", "N/A"),
            "params": getattr(record, "params", {}),
            "result": getattr(record, "result", "N/A"),
        }
        
        if record.exc_info:
            log_record["stack_trace"] = self.formatException(record.exc_info)
        
        # Add extra fields if available in record.__dict__ that are not standard
        # (This allows logging.info("msg", extra={'key': 'val'}) to work if mapped)
        # Standard python logging 'extra' dict is merged into record.__dict__
        
        return json.dumps(log_record, ensure_ascii=False)

class DailySizeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """
    Handler that rotates files based on size and changes filename based on date.
    Also ensures total number of log files does not exceed limit.
    """
    def __init__(self,filename: str, log_dir: str, maxBytes: int, backupCount: int):
        self.log_dir_path = Path(log_dir)
        self.filename = filename
        try:
            self.log_dir_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            # Fallback if cannot create directory, though we should probably crash or warn
            print(f"Failed to create log directory {log_dir}: {e}")

        self.limit_backup_count = backupCount
        
        self.current_date = datetime.now().date()
        filename = self._get_filename(self.current_date)
        
        # Initialize parent
        # We set backupCount to a large number for the parent because we handle global cleanup manually
        # But we still want the parent to handle the .1, .2 rotation for the *current* day/filename
        super().__init__(filename, maxBytes=maxBytes, backupCount=100, encoding='utf-8')
        
    def _get_filename(self, date_obj) -> str:
        return str(self.log_dir_path / f"{self.filename}-{date_obj.strftime('%Y-%m-%d')}.log")

    def emit(self, record):
        try:
            # Check if date has changed
            new_date = datetime.now().date()
            if new_date != self.current_date:
                self.current_date = new_date
                new_filename = self._get_filename(self.current_date)
                
                # Close current stream
                if self.stream:
                    self.stream.close()
                    self.stream = None
                
                # Update base filename
                self.baseFilename = new_filename
                
            super().emit(record)
            self._cleanup_logs()
        except Exception:
            self.handleError(record)

    def _cleanup_logs(self):
        """
        Delete oldest files if total count exceeds limit.
        """
        try:
            # Get all log files in the directory
            # glob patterns: *.log and *.log.*
            files = list(self.log_dir_path.glob("*.log*"))
            if len(files) <= self.limit_backup_count:
                return
            
            # Sort by modification time (oldest first)
            files.sort(key=lambda f: f.stat().st_mtime)
            
            # Delete excess files
            files_to_delete = files[:len(files) - self.limit_backup_count]
            for f in files_to_delete:
                try:
                    f.unlink()
                except OSError:
                    pass
        except Exception:
            # Avoid crashing logging if cleanup fails
            pass

def setup_logging(filename="main"):
    """
    Configure the logging system.
    Returns the listener so it can be stopped if needed.
    """
    # Create Queue for non-blocking logging
    log_queue = queue.Queue(-1) # Infinite queue
    
    # JSON Formatter
    formatter = JSONFormatter()
    
    # File Handler
    file_handler = DailySizeRotatingFileHandler(
        filename=filename,
        log_dir=LOG_DIR,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(LOG_LEVEL)
    
    # Queue Listener
    # This listener runs in a separate thread and handles the actual writing
    handlers = [file_handler]
    # PyInstaller's windowed desktop runtime intentionally has no stdout. The
    # Docker/dev service keeps its console logger as before.
    if sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(LOG_LEVEL)
        handlers.append(console_handler)
    listener = logging.handlers.QueueListener(log_queue, *handlers, respect_handler_level=True)
    listener.start()
    
    # Queue Handler (this is what the main thread uses)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    
    # Root Logger Configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers = []
    
    # Add Queue Handler to root logger
    root_logger.addHandler(queue_handler)
    
    # Configure Uvicorn loggers to use our queue handler
    # This ensures uvicorn logs also go through our JSON formatter and file rotation
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"]:
        logger = logging.getLogger(logger_name)
        logger.handlers = [queue_handler]
        logger.propagate = False

    return listener

# Helper to easily log with operation context
def log_operation(level: str, message: str, operation: str = "N/A", params: dict = None, result: Any = "N/A", error: Exception = None):
    logger = logging.getLogger("app")
    extra = {
        "operation": operation,
        "params": params or {},
        "result": str(result)
    }
    
    if error:
        logger.error(message, exc_info=error, extra=extra)
    else:
        if level.lower() == "info":
            logger.info(message, extra=extra)
        elif level.lower() == "warn" or level.lower() == "warning":
            logger.warning(message, extra=extra)
        elif level.lower() == "debug":
            logger.debug(message, extra=extra)
        elif level.lower() == "error":
            logger.error(message, extra=extra)
