import logging
import traceback
import aiohttp
import requests
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Form, BackgroundTasks

from app.core.config_manager import config_manager
from app.db.session import SessionLocal

async def async_get_embedding(text: str, user_id: int, db: SessionLocal) -> list[float]:
    """
    Get the embedding of a text.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=30, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f"{config_manager.get_user_config(user_id, db).ai.ai_api_url}/embedding/text"
            payload = {'texts': [text]}
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data[0]
                else:
                    logging.info(resp.status, await resp.text())
                    raise HTTPException(status_code=500, detail=f"AI Service error: {resp.status}")
    except Exception as e:
        logging.info(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to connect to AI service: {e}")

def get_embedding(text: str, user_id: int, db: SessionLocal) -> list[float]:
    """
    Get the embedding of a text.
    """
    try:
        url = f"{config_manager.get_user_config(user_id, db).ai.ai_api_url}/embedding/text"
        payload = {'texts': [text]}
        # 连接 5s、读取 30s 超时，避免 AI 服务假死时请求无限挂起导致对话卡死
        response = requests.post(url, json=payload, timeout=(5, 30))
        if response.status_code == 200:
            data = response.json()
            return data[0]
        else:
            logging.info(response.status_code, response.text)
            raise HTTPException(status_code=500, detail=f"AI Service error: {response.status_code}")
    except Exception as e:
        logging.info(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to connect to AI service: {e}")