import asyncio
import logging
import sys
import os
import signal

from dotenv import load_dotenv

from app.core.logger import setup_logging
from app.core.paths import DATA_DIR, ensure_rg_seed
from app.service.task_worker import TaskWorker

async def _run(event_queue=None):
    worker = TaskWorker.get_instance()
    worker.set_event_queue(event_queue)
    worker.start()

    # Keep the loop alive
    while True:
        await asyncio.sleep(1)

def run_worker(event_queue=None):
    load_dotenv(os.path.join(DATA_DIR, '.env'))
    """Entry point for the worker process"""
    # Setup logging for this process
    setup_logging('task')
    logging.info(f"Starting Worker Process (PID: {os.getpid()})...")
    # 确保反向编码数据目录就绪并播种（worker 进程独立于 API 进程，需自行初始化）
    ensure_rg_seed()

    # Windows compatibility for asyncio loop
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        if sys.platform != 'win32':
            # Signal handling for graceful shutdown (Linux/Mac)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Register signal handlers
            pass

        asyncio.run(_run(event_queue))
    except (KeyboardInterrupt, SystemExit):
        logging.info("Worker process received stop signal")
    except Exception as e:
        logging.error(f"Worker process crashed: {e}", exc_info=True)
    finally:
        logging.info("Stopping TaskWorker in worker process...")
        try:
            TaskWorker.get_instance().stop()
        except:
            pass
        logging.info("Worker process stopped")

if __name__ == "__main__":
    run_worker()
