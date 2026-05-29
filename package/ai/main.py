import uvicorn
import logging
import time
import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import system, face, ocr, object_detection, tickets, image_classification, ai_config, embedding, llm
from app.core.logger import setup_logging
from app.services.model_downloader import model_downloader
from app.services.llm_manager import llm_manager

# Memory management globals
active_requests = 0
last_request_time = time.time()

async def check_idle_and_restart():
    """Check if the service has been idle for too long and restart if necessary."""
    while True:
        try:
            await asyncio.sleep(settings.CHECK_INTERVAL)

            # If there are active requests, we are not idle
            if active_requests > 0:
                continue

            current_time = time.time()
            idle_duration = current_time - last_request_time

            if idle_duration > settings.IDLE_TIMEOUT:
                logging.getLogger("app.main").warning(
                    f"Service idle for {idle_duration:.0f} seconds (Threshold: {settings.IDLE_TIMEOUT}s). "
                    f"Restarting to release memory..."
                )
                # Exit the process. The container orchestrator or process manager should restart it.
                sys.exit(0)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.getLogger("app.main").error(f"Error in idle check task: {e}")
            # Don't stop the loop on error, just wait and retry
            await asyncio.sleep(settings.CHECK_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global log_listener
    log_listener = setup_logging('ai')

    # Start model downloads in background
    model_downloader.start_downloads()
    
    # Start LLM idle checker task
    llm_idle_task = asyncio.create_task(llm_manager.idle_checker())

    # 判断当前平台是否为Windows，Windows平台下不启动空闲检查任务
    if sys.platform != 'win32':
        # Start idle check task
        idle_check_task = asyncio.create_task(check_idle_and_restart())

    yield

    # Cleanup
    if sys.platform != 'win32':
        idle_check_task.cancel()
        try:
            await idle_check_task
        except asyncio.CancelledError:
            pass
            
    llm_idle_task.cancel()
    try:
        await llm_idle_task
    except asyncio.CancelledError:
        pass
        
    # Stop LLM server subprocess
    await llm_manager.stop()

    if log_listener:
        log_listener.stop()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Microservice for AI capabilities including Face Recognition, OCR, etc.",
    lifespan=lifespan
)

# Initialize logging listener
log_listener = None

@app.middleware("http")
async def log_requests(request: Request, call_next):
    global active_requests, last_request_time
    active_requests += 1

    start_time = time.time()
    operation = f"{request.method} {request.url.path}"
    params = dict(request.query_params)

    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000

        extra = {
            "operation": operation,
            "params": params,
            "result": response.status_code,
            "duration_ms": f"{process_time:.2f}"
        }
        # logging.getLogger("app.middleware").info("Request processed", extra=extra)

        return response

    except Exception as e:
        process_time = (time.time() - start_time) * 1000
        extra = {
            "operation": operation,
            "params": params,
            "result": "Error",
            "duration_ms": f"{process_time:.2f}"
        }
        logging.getLogger("app.middleware").error(f"Request failed: {str(e)}", exc_info=e, extra=extra)
        raise e
    finally:
        active_requests -= 1
        last_request_time = time.time()


# Include Routers
app.include_router(system.router, tags=["System"])
app.include_router(face.router, prefix="/face", tags=["Face Recognition"])
app.include_router(ocr.router, prefix="/ocr", tags=["OCR"])
app.include_router(object_detection.router, prefix="/object-detection", tags=["Object Detection"])
app.include_router(tickets.router, prefix="/tickets", tags=["Ticket Recognition"])
app.include_router(image_classification.router, prefix="/classification", tags=["Image Classification"])
app.include_router(embedding.router, prefix="/embedding", tags=["Embedding"])
app.include_router(llm.router, prefix="/v1", tags=["OpenAI LLM"])
app.include_router(ai_config.router, prefix="/ai", tags=["AI Configuration"])

if __name__ == "__main__":
    # docs：http://localhost:8001/docs
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
