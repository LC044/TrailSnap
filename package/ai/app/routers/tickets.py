from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import asyncio
import base64
import logging
import traceback

from app.services.ticket_service import ticket_service
from app.core.admission import tickets_admission

router = APIRouter()

class TicketInfo(BaseModel):
    train_code: Optional[str] = Field(default=None)
    departure_station: Optional[str] = Field(default=None)
    arrival_station: Optional[str] = Field(default=None)
    datetime: Optional[str] = Field(default=None)
    carriage: Optional[str] = Field(default=None)
    seat_num: Optional[str] = Field(default=None)
    berth_type: Optional[str] = Field(default=None)
    price: Optional[str] = Field(default=None)
    seat_type: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    discount_type: Optional[str] = Field(default=None)
    
    # 飞机票特有字段 (兼容)
    flight_code: Optional[str] = Field(default=None)
    departure_city: Optional[str] = Field(default=None)
    arrival_city: Optional[str] = Field(default=None)
    type: Optional[str] = Field(default="train")
    
    detection_id: int = 0

class TicketRecognitionResponse(BaseModel):
    results: List[Dict[str, Any]]

class TicketRecognitionRequest(BaseModel):
    images: List[str]


def _predict_batch(images: List[str]) -> List[Dict[str, Any]]:
    batch_results = []
    for b64 in images:
        if ',' in b64:
            b64 = b64.split(',')[1]
        contents = base64.b64decode(b64)
        results = ticket_service.detect(contents)
        batch_results.append({
            "ticket_count": results["count"],
            "tickets": results["tickets"],
        })
    return batch_results

@router.post("/predict", response_model=TicketRecognitionResponse)
async def predict_ticket(request: TicketRecognitionRequest):
    """
    Upload multiple base64 encoded images to recognize train tickets.
    """
    if not request.images:
        raise HTTPException(status_code=400, detail="No images provided")

    await tickets_admission.acquire()
    try:
        batch_results = await asyncio.to_thread(_predict_batch, request.images)
        return {"results": batch_results}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
    finally:
        tickets_admission.release()
