import httpx
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from app.services.llm_manager import llm_manager
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Global async client for connection pooling to the subprocess
client = httpx.AsyncClient(base_url=f"http://127.0.0.1:{settings.LLM_SERVER_PORT}", timeout=None)

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_llm(request: Request, path: str):
    """
    Transparently proxies all /v1/* requests to the llama.cpp subprocess server.
    It will start the server if it's not running, and update its last access time.
    """
    try:
        await llm_manager.ensure_running()
    except ValueError as ve:
        raise HTTPException(status_code=503, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start LLM server: {e}")

    # Update access time to prevent idle shutdown before we start proxying
    llm_manager.last_access_time = __import__('time').time()

    url = httpx.URL(path=f"/v1/{path}", query=request.url.query.encode("utf-8"))
    
    # Read the body from the incoming request
    body = await request.body()
    
    # Forward headers, but drop hop-by-hop headers that httpx should recalculate
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None) 
    
    req = client.build_request(
        request.method,
        url,
        headers=headers,
        content=body
    )
    
    try:
        resp = await client.send(req, stream=True)
        
        async def stream_generator():
            async for chunk in resp.aiter_bytes():
                # Keep updating access time while streaming so it doesn't die mid-stream
                llm_manager.last_access_time = __import__('time').time()
                yield chunk
            await resp.aclose()

        # Remove chunked encoding header to let FastAPI/Starlette handle it correctly
        response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in ['transfer-encoding', 'content-encoding']}
        
        return StreamingResponse(
            stream_generator(),
            status_code=resp.status_code,
            headers=response_headers
        )
        
    except httpx.RequestError as e:
        logger.error(f"Proxy request error: {e}")
        raise HTTPException(status_code=502, detail="Error communicating with the underlying LLM server")
